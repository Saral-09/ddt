from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import Server, serve


class DDTBridgeError(RuntimeError):
    """Raised when the running DDT application cannot service a QA request."""


@dataclass
class _PendingExecution:
    event: threading.Event = field(default_factory=threading.Event)
    stdout: str = ""
    stderr: str = ""
    pid: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class DDTIntegrationBridge:
    """Loopback WebSocket bridge between the Python QA agent and the DDT WebView.

    The Python side owns the server and the one-time token. The DDT frontend
    connects outbound, authenticates, and runs approved requests through the
    production CommandHelper (Tauri Shell plugin). This class never starts a
    process itself.
    """

    ALLOWED_ORIGINS = {
        "tauri://localhost",
        "https://tauri.localhost",
        "http://tauri.localhost",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, token: str | None = None):
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("The DDT QA bridge must bind to loopback only.")
        if not 1 <= int(port) <= 65535:
            raise ValueError("Bridge port must be between 1 and 65535.")

        self.host = host
        self.port = int(port)
        self.token = token or secrets.token_urlsafe(32)
        self._server: Server | None = None
        self._server_thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._state_lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._connection: Any = None
        self._pending: dict[str, _PendingExecution] = {}
        self._startup_error: Exception | None = None

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> None:
        if self._server_thread and self._server_thread.is_alive():
            return
        self._server_thread = threading.Thread(target=self._serve, name="ddt-qa-bridge", daemon=True)
        self._server_thread.start()
        if not self._ready.wait(5):
            raise DDTBridgeError("Timed out while starting the local DDT QA bridge.")
        if self._startup_error:
            raise DDTBridgeError(f"Could not start DDT QA bridge: {self._startup_error}") from self._startup_error

    def _serve(self) -> None:
        try:
            server = serve(
                self._handle_connection,
                self.host,
                self.port,
                max_size=1_048_576,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=3,
            )
            self._server = server
            self._ready.set()
            server.serve_forever()
        except Exception as exc:  # surfaced to CLI on start
            self._startup_error = exc
            self._ready.set()

    @staticmethod
    def _get_origin(websocket: Any) -> str | None:
        request = getattr(websocket, "request", None)
        headers = getattr(request, "headers", None)
        if headers is not None:
            return headers.get("Origin")
        headers = getattr(websocket, "request_headers", None)
        return headers.get("Origin") if headers is not None else None

    def _handle_connection(self, websocket: Any, _path: str | None = None) -> None:
        origin = self._get_origin(websocket)
        if origin and origin not in self.ALLOWED_ORIGINS:
            websocket.close(code=1008, reason="Origin not allowed")
            return

        try:
            raw_auth = websocket.recv(timeout=10)
            auth = json.loads(raw_auth)
        except Exception:
            websocket.close(code=1008, reason="Authentication required")
            return

        supplied = auth.get("token", "") if isinstance(auth, dict) else ""
        auth_type = auth.get("type") if isinstance(auth, dict) else None
        if auth_type != "auth" or not isinstance(supplied, str) or not hmac.compare_digest(supplied, self.token):
            websocket.close(code=1008, reason="Authentication failed")
            return

        with self._state_lock:
            if self._connection is not None:
                websocket.close(code=1008, reason="A DDT client is already connected")
                return
            self._connection = websocket
            self._connected.set()

        try:
            websocket.send(json.dumps({"type": "authenticated", "message": "DDT QA bridge connected."}))
            while not self._stop.is_set():
                try:
                    raw_message = websocket.recv(timeout=1)
                except TimeoutError:
                    continue
                message = json.loads(raw_message)
                if isinstance(message, dict):
                    self._handle_client_message(message)
        except ConnectionClosed:
            pass
        except Exception:
            # A malformed client message must not crash the whole QA process.
            pass
        finally:
            with self._state_lock:
                if self._connection is websocket:
                    self._connection = None
                    self._connected.clear()
                    for pending in self._pending.values():
                        pending.error = "DDT application disconnected during execution."
                        pending.event.set()

    def _handle_client_message(self, message: dict[str, Any]) -> None:
        request_id = message.get("request_id")
        if not isinstance(request_id, str):
            return
        with self._state_lock:
            pending = self._pending.get(request_id)
            if pending is None:
                return

            message_type = message.get("type")
            if message_type == "started":
                pending.pid = str(message.get("pid", "")) or None
            elif message_type == "output":
                stream = message.get("stream")
                data = message.get("data")
                if isinstance(data, str):
                    if stream == "stderr":
                        pending.stderr = (pending.stderr + data)[-500_000:]
                    else:
                        pending.stdout = (pending.stdout + data)[-500_000:]
            elif message_type == "completed":
                pending.result = {
                    "status": "timeout" if message.get("timed_out") else "completed",
                    "exit_code": message.get("code"),
                    "signal": message.get("signal"),
                    "timed_out": bool(message.get("timed_out")),
                    "pid": pending.pid,
                    "stdout": pending.stdout,
                    "stderr": pending.stderr,
                    "duration_ms": message.get("duration_ms"),
                }
                pending.event.set()
            elif message_type == "execution_error":
                pending.error = str(message.get("error", "DDT command execution failed."))[:2000]
                pending.event.set()

    def wait_for_client(self, timeout: float = 120) -> bool:
        return self._connected.wait(timeout=max(0.0, timeout))

    def _send(self, message: dict[str, Any]) -> None:
        with self._state_lock:
            connection = self._connection
        if connection is None:
            raise DDTBridgeError("DDT application is not connected. Open the DDT QA Bridge panel and connect it first.")
        try:
            with self._send_lock:
                connection.send(json.dumps(message, ensure_ascii=False))
        except Exception as exc:
            raise DDTBridgeError(f"Could not send request to DDT: {exc}") from exc

    def execute(
        self,
        command: str,
        args: list[str],
        timeout_seconds: int,
        tool_id: str,
    ) -> dict[str, Any]:
        """Execute a validated argv request through the DDT frontend CommandHelper."""
        if not self.connected:
            raise DDTBridgeError("DDT is not connected. Connect the QA Bridge panel in the running DDT app.")
        if not isinstance(command, str) or not command or any(ch.isspace() for ch in command):
            raise DDTBridgeError("Bridge command must be a single executable name, not a shell command string.")
        if not isinstance(args, list) or len(args) > 40 or not all(isinstance(item, str) and len(item) <= 512 for item in args):
            raise DDTBridgeError("Bridge arguments must be an array of at most 40 strings (512 characters each).")
        if any("\x00" in item or "\n" in item or "\r" in item for item in args):
            raise DDTBridgeError("Null and newline characters are not allowed in arguments.")
        if not 1 <= int(timeout_seconds) <= 60:
            raise DDTBridgeError("Execution timeout must be between 1 and 60 seconds.")

        request_id = str(uuid.uuid4())
        pending = _PendingExecution()
        with self._state_lock:
            self._pending[request_id] = pending

        started = time.monotonic()
        try:
            self._send(
                {
                    "type": "execute",
                    "request_id": request_id,
                    "tool_id": tool_id,
                    "command": command,
                    "args": args,
                    "timeout_seconds": int(timeout_seconds),
                }
            )
            finished = pending.event.wait(timeout_seconds + 8)
            if not finished:
                try:
                    self._send({"type": "cancel", "request_id": request_id})
                except DDTBridgeError:
                    pass
                pending.event.wait(2)

            if pending.error:
                raise DDTBridgeError(pending.error)
            if pending.result:
                result = dict(pending.result)
                result["duration_seconds"] = round(time.monotonic() - started, 3)
                return result

            return {
                "status": "timeout",
                "timed_out": True,
                "exit_code": None,
                "signal": None,
                "pid": pending.pid,
                "stdout": pending.stdout,
                "stderr": pending.stderr,
                "duration_seconds": round(time.monotonic() - started, 3),
                "reason": "No completion event was received from DDT before the bridge timeout.",
            }
        finally:
            with self._state_lock:
                self._pending.pop(request_id, None)

    def close(self) -> None:
        self._stop.set()
        server = self._server
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
        thread = self._server_thread
        if thread and thread.is_alive():
            thread.join(timeout=3)
