from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ui_testing import (
    UITestError,
    WebdriverUITestRunner,
    _EXECUTABLE_FIXTURE_MODES,
    _SENSITIVE_FIELD_RE,
    _host_from_value,
    _is_target_field,
    _normalize_host,
)


class AutonomousUISessionManager:
    """Own one persistent, loopback-only WebdriverIO session for Foundry UI tools.

    Foundry never supplies selectors, XPath, JavaScript, shell commands or URLs.
    It receives short-lived element IDs from a fresh UI observation and can use
    only the fixed actions implemented by the WebdriverIO bridge.
    """

    _MAX_ACTIONS = 80
    _MAX_VALUE_LENGTH = 2000
    _FILE_FIELD_LABEL_RE = re.compile(
        r"(?:file|path|wordlist|pcap|capture|image|document|archive|directory|folder)",
        re.IGNORECASE,
    )
    _EXECUTION_LABELS = (
        "run", "execute", "start", "launch", "scan", "capture", "submit", "go", "exploit",
        "attack", "crack", "flood", "spoof", "inject", "brute", "enumerate",
        "discover", "ping", "resolve", "connect", "lookup", "fetch", "search",
        "crawl", "download", "generate", "process", "analyze", "convert",
        "extract", "check", "verify", "upload", "send",
    )
    _PROHIBITED_LABELS = (
        "exploit", "attack", "crack", "flood", "spoof", "inject", "brute force",
        "bruteforce", "denial of service", "dos",
    )

    def __init__(
        self,
        repo: Any,
        enabled: bool = False,
        ui_runner: WebdriverUITestRunner | None = None,
        input_fn: Callable[[str], str] | None = None,
    ):
        self.repo = repo
        self.enabled = enabled
        self.ui_runner = ui_runner or WebdriverUITestRunner(repo, enabled=enabled)
        self.input_fn = input_fn or input
        self.qa_dir = repo.root_path / "qa-agent"
        self.runtime_dir = self.qa_dir / "runtime"
        self.report_dir = self.qa_dir / "reports"
        self.config_file = self.qa_dir / "wdio" / "wdio.interactive.conf.cjs"
        self.spec_file = self.qa_dir / "wdio" / "interactive-session.spec.cjs"
        self.allowed_targets = {
            _normalize_host(item)
            for item in os.getenv("DDT_QA_ALLOWED_TARGETS", "127.0.0.1,localhost,::1").split(",")
            if item.strip()
        }

        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle: Any | None = None
        self.log_path: Path | None = None
        self.result_path: Path | None = None
        self.local_web_process: subprocess.Popen[str] | None = None
        self.base_url: str | None = None
        self.token: str | None = None
        self.tool: Any | None = None
        self.fixture: dict[str, Any] | None = None
        self.execution_mode = "ui_only"
        self.declared_targets: set[str] = set()
        self.fixture_files: set[str] = set()
        self.action_count = 0
        self.last_observation: dict[str, Any] | None = None
        # Preserve configured targets as wizard pages unmount/remount their
        # inputs. This lets the execution guard validate the target at Run time.
        self.target_values_by_label: dict[str, str] = {}
        self.active = False
        self.run_id: str | None = None

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _read_tail(path: Path | None, limit: int = 10000) -> str:
        if path is None or not path.is_file():
            return ""
        try:
            with path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - limit), os.SEEK_SET)
                return handle.read().decode("utf-8", errors="replace")
        except OSError:
            return ""

    def _validate_scope(self, args: dict[str, Any]) -> tuple[Any, dict[str, Any], list[str], tuple[dict[str, Any], list[str], list[str]]]:
        if not isinstance(args, dict):
            raise UITestError("UI session arguments must be an object")
        tool_id = args.get("tool_id")
        if not isinstance(tool_id, str) or not tool_id.strip():
            raise UITestError("tool_id is required")
        tool = self.repo.find_tool(tool_id)

        description = args.get("description", "")
        if not isinstance(description, str) or not description.strip() or len(description) > 1000:
            raise UITestError("description must contain 1-1000 characters")

        execution_mode = args.get("execution_mode")
        if execution_mode not in {"ui_only", "validation_only", "fixture_execution"}:
            raise UITestError("execution_mode must be ui_only, validation_only or fixture_execution")

        fixture_services = args.get("fixture_services")
        if not isinstance(fixture_services, list) or len(fixture_services) > 1:
            raise UITestError("fixture_services must be an array containing at most one supported service")
        if any(item != "local_web" for item in fixture_services):
            raise UITestError("Only the reviewed local_web fixture service is supported")

        raw_targets = args.get("execution_targets")
        raw_files = args.get("fixture_files")
        if not isinstance(raw_targets, list) or not isinstance(raw_files, list):
            raise UITestError("execution_targets and fixture_files must be arrays")
        if len(raw_targets) > 5 or len(raw_files) > 5:
            raise UITestError("A session can declare at most five targets and five fixture files")
        if not all(isinstance(item, str) for item in raw_targets + raw_files):
            raise UITestError("execution_targets and fixture_files must contain strings")

        declared_targets: set[str] = set()
        for raw_target in raw_targets:
            host = _host_from_value(raw_target)
            if not host or host not in self.allowed_targets:
                raise UITestError(f"Target '{raw_target}' is not in DDT_QA_ALLOWED_TARGETS")
            declared_targets.add(host)

        resolved_files: list[str] = []
        for raw_file in raw_files:
            resolved_files.append(str(self.ui_runner._resolve_fixture_file(raw_file)))

        fixture = self.ui_runner._fixture_metadata(tool.id) or {}
        fixture_mode = str(fixture.get("fixture_mode", "manual_only"))
        loopback = {"127.0.0.1", "localhost", "::1"}
        if "local_web" in fixture_services:
            if fixture_mode not in {
                "local_web_only", "single_lab_host", "single_lab_port_only", "loopback_service", "local_or_help_only"
            }:
                raise UITestError(
                    f"local_web is not approved for fixture_mode '{fixture_mode}'"
                )
            if not declared_targets or not declared_targets.issubset(loopback):
                raise UITestError("local_web may only be used with explicitly declared loopback targets")

        if execution_mode == "validation_only":
            if not declared_targets or not declared_targets.issubset(loopback):
                raise UITestError("validation_only requires explicitly declared loopback targets only")
        elif execution_mode == "fixture_execution":
            if fixture_mode not in _EXECUTABLE_FIXTURE_MODES:
                raise UITestError(
                    f"Execution is blocked for {tool.name}: fixture_mode '{fixture_mode}' is not approved"
                )
            if not declared_targets and not resolved_files:
                raise UITestError("fixture_execution requires an approved target or fixture file")
        elif declared_targets or resolved_files:
            # UI-only sessions may inspect and populate approved inputs, but must
            # not submit any process-running action.
            pass

        if not description.strip():
            raise UITestError("A test objective is required")

        normalized = {
            "description": description.strip(),
            "execution_mode": execution_mode,
            "fixture_mode": fixture_mode,
            "fixture_services": fixture_services,
            "execution_targets": sorted(declared_targets),
            "fixture_files": resolved_files,
        }
        return tool, fixture, fixture_services, (normalized, sorted(declared_targets), resolved_files)

    def _approval_summary(self, tool: Any, scope: dict[str, Any]) -> None:
        print("\nDDT AUTONOMOUS UI SESSION")
        print(f"Tool: {tool.name} ({tool.path})")
        print(f"Objective: {scope['description']}")
        print(f"Execution mode: {scope['execution_mode']}")
        print(f"Fixture mode: {scope['fixture_mode']}")
        print(f"Targets: {', '.join(scope['execution_targets']) if scope['execution_targets'] else 'none'}")
        print(f"Fixtures: {', '.join(Path(p).name for p in scope['fixture_files']) if scope['fixture_files'] else 'none'}")
        print("The AI will interact with the real DDT UI using a restricted set of observed-element actions.")
        print("Process-running buttons are blocked unless the approved execution mode and target/file scope permit them.")

    def _command(self, payload: dict[str, Any], timeout: int = 25) -> dict[str, Any]:
        if not self.active or not self.base_url or not self.token:
            raise UITestError("There is no active autonomous UI session")
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/command",
            data=body,
            headers={"Content-Type": "application/json", "X-DDT-QA-Token": self.token},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read(2_000_000).decode("utf-8"))
        except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            tail = self._read_tail(self.log_path, 3000)
            raise UITestError(f"WebdriverIO UI bridge request failed: {exc}. Runner log tail: {tail}") from exc
        if not isinstance(result, dict):
            raise UITestError("WebdriverIO UI bridge returned an invalid response")
        if result.get("status") == "error":
            raise UITestError(str(result.get("error", "Unknown UI bridge error")))
        observation = result.get("observation")
        if isinstance(observation, dict):
            self.last_observation = observation
            self._remember_observed_targets(observation)
        return result

    def _remember_observed_targets(self, observation: dict[str, Any]) -> None:
        for item in observation.get("controls", []):
            label_text = " ".join(
                str(item.get(key, ""))
                for key in ("label", "name", "id", "placeholder", "nearby_text")
            )
            if not _is_target_field(label_text):
                continue
            value = item.get("value")
            if isinstance(value, str) and value != "[REDACTED]":
                key = str(item.get("label") or item.get("name") or item.get("id") or label_text).strip().lower()
                self.target_values_by_label[key] = value.strip()

    def start(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise UITestError("Autonomous UI testing is disabled; start with --enable-ui-testing")
        if self.active:
            raise UITestError("An autonomous UI session is already active; finish it before starting another")
        if not self.config_file.is_file() or not self.spec_file.is_file():
            raise UITestError("Interactive WebdriverIO configuration/spec files are missing")

        tool, fixture, fixture_services, validated = self._validate_scope(args)
        scope, declared_targets, resolved_files = validated
        self._approval_summary(tool, scope)
        approval = self.input_fn("\nType RUN DDT AUTONOMOUS UI SESSION to start: ").strip()
        if approval != "RUN DDT AUTONOMOUS UI SESSION":
            return {"status": "cancelled", "reason": "Operator approval was not provided; no UI session was started."}

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        result_path = self.report_dir / f"ui-autonomous-{run_id}.json"
        log_path = self.report_dir / f"ui-autonomous-{run_id}.log"
        port = self._free_port()
        token = secrets.token_urlsafe(32)

        env = os.environ.copy()
        env["DDT_QA_UI_SESSION_PORT"] = str(port)
        env["DDT_QA_UI_SESSION_TOKEN"] = token
        env["DDT_QA_UI_TOOL_JSON"] = json.dumps({"id": tool.id, "name": tool.name, "path": tool.path})
        env["DDT_QA_UI_SCOPE_JSON"] = json.dumps(scope)
        env["DDT_QA_UI_RESULT_PATH"] = str(result_path)
        env["DDT_QA_UI_SCREENSHOT_DIR"] = str(self.report_dir / "ui-screenshots" / f"session-{run_id}")
        env.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
        env.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")

        app_binary = env.get("DDT_APP_BINARY", "").strip()
        if app_binary:
            env["DDT_APP_BINARY"] = str(Path(app_binary).expanduser().resolve())

        local_wdio = self.repo.root_path / "node_modules" / ".bin" / "wdio"
        if local_wdio.exists():
            command = [str(local_wdio), "run", str(self.config_file)]
        elif shutil.which("corepack"):
            command = [shutil.which("corepack") or "corepack", "yarn", "wdio", "run", str(self.config_file)]
        elif shutil.which("yarn"):
            command = [shutil.which("yarn") or "yarn", "wdio", "run", str(self.config_file)]
        else:
            raise UITestError("Could not find WebdriverIO, Corepack or Yarn")

        self.tool = tool
        self.fixture = fixture
        self.execution_mode = scope["execution_mode"]
        self.declared_targets = set(declared_targets)
        self.fixture_files = set(resolved_files)
        self.run_id = run_id
        self.result_path = result_path
        self.log_path = log_path
        self.token = token
        self.base_url = f"http://127.0.0.1:{port}"
        self.action_count = 0
        self.last_observation = None
        self.target_values_by_label = {}

        if "local_web" in fixture_services:
            self.local_web_process = self.ui_runner._start_local_web()

        self.log_handle = log_path.open("wb")
        try:
            self.process = subprocess.Popen(
                command,
                cwd=self.repo.root_path,
                env=env,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
        except Exception:
            self.log_handle.close()
            self.log_handle = None
            self.ui_runner._stop_local_web(self.local_web_process)
            self.local_web_process = None
            raise

        self.active = True
        deadline = time.monotonic() + 120
        last_error = ""
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                last_error = self._read_tail(self.log_path, 7000)
                self._cleanup_process()
                raise UITestError(f"WebdriverIO exited during session startup. Log: {last_error}")
            try:
                health = self._request_health()
                if health.get("ready") is True:
                    observation = self.observe()
                    return {
                        "status": "started",
                        "tool": tool.name,
                        "session_id": run_id,
                        "execution_mode": self.execution_mode,
                        "observation": observation.get("observation", observation),
                        "report": str(result_path.relative_to(self.repo.root_path)),
                    }
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.35)

        self.abort_if_active()
        raise UITestError(f"Timed out waiting for DDT/WebdriverIO interactive session. Last error: {last_error}")

    def _request_health(self) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}/health",
            headers={"X-DDT-QA-Token": self.token or ""},
            method="GET",
        )
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read(10000).decode("utf-8"))

    def _current_control(self, element_id: str) -> dict[str, Any]:
        if not isinstance(element_id, str) or len(element_id) > 80:
            raise UITestError("element_id must be a short ID from the most recent observe_ui result")
        controls = (self.last_observation or {}).get("controls", [])
        for item in controls:
            if item.get("id") == element_id:
                return item
        raise UITestError("The element ID is not part of the most recent UI observation; call observe_ui again")

    def _guard_input(self, control: dict[str, Any], value: str) -> None:
        label = " ".join(str(control.get(key, "")) for key in ("label", "name", "id", "placeholder", "nearby_text"))
        if _SENSITIVE_FIELD_RE.search(label) or str(control.get("type", "")).lower() == "password":
            raise UITestError("Automated interaction with password, secret or credential fields is not permitted")
        if re.search(r"\b(command|shell|script|raw arguments|raw args)\b", label, re.IGNORECASE):
            raise UITestError("Arbitrary command, shell or script input fields are not permitted in autonomous UI sessions")
        if _is_target_field(label) and self.execution_mode != "ui_only":
            host = _host_from_value(value)
            if not host or host not in self.allowed_targets or host not in self.declared_targets:
                raise UITestError(f"Target value '{value}' is not explicitly approved for this UI session")
        if str(control.get("type", "")).lower() == "file" or self._FILE_FIELD_LABEL_RE.search(label):
            resolved = str(self.ui_runner._resolve_fixture_file(value))
            if resolved not in self.fixture_files:
                raise UITestError("File inputs must use a fixture file declared and approved when the session started")

    def _guard_execution(self, control: dict[str, Any]) -> None:
        label = str(control.get("label") or control.get("text") or "").strip().lower()
        if not label and control.get("kind") in {"button", "action"}:
            raise UITestError("Unlabelled action controls cannot be clicked autonomously; use an accessible, named control")
        if any(term in label for term in self._PROHIBITED_LABELS):
            raise UITestError(f"The requested UI action '{label}' is prohibited by the QA safety policy")
        if not any(term == label or label.startswith(term + " ") for term in self._EXECUTION_LABELS):
            return
        if self.execution_mode == "ui_only":
            raise UITestError("Process-running UI actions are blocked in ui_only mode")
        if not self.declared_targets and not self.fixture_files:
            raise UITestError("Process-running actions require an explicitly approved target or fixture file")
        observed_targets: set[str] = set()
        for value in self.target_values_by_label.values():
            if not value:
                continue
            host = _host_from_value(value)
            if not host or host not in self.allowed_targets or host not in self.declared_targets:
                raise UITestError(f"A configured target field contains an unapproved value: {value}")
            observed_targets.add(host)
        if self.declared_targets and not observed_targets.intersection(self.declared_targets):
            # Offline file-based tools may not expose any target field.
            if not self.fixture_files:
                raise UITestError("No approved target value is currently visible in the UI; observe and configure the target before execution")
        if self.execution_mode == "validation_only":
            loopback = {"127.0.0.1", "localhost", "::1"}
            if not self.declared_targets.issubset(loopback):
                raise UITestError("validation_only can submit only against explicitly approved loopback targets")

    def _count_action(self) -> None:
        self.action_count += 1
        if self.action_count > self._MAX_ACTIONS:
            raise UITestError(f"Autonomous UI session exceeded the {_MAX_ACTIONS}-action limit")

    def observe(self) -> dict[str, Any]:
        result = self._command({"type": "observe"})
        self._count_action()
        return result

    def wait(self, seconds: int) -> dict[str, Any]:
        if not isinstance(seconds, int) or isinstance(seconds, bool) or not 1 <= seconds <= 30:
            raise UITestError("wait seconds must be an integer between 1 and 30")
        self._count_action()
        return self._command({"type": "wait", "seconds": seconds}, timeout=seconds + 10)

    def click(self, element_id: str) -> dict[str, Any]:
        control = self._current_control(element_id)
        if control.get("disabled"):
            raise UITestError("The selected UI element is disabled")
        if control.get("kind") in {"button", "action", "step", "link"}:
            self._guard_execution(control)
        self._count_action()
        return self._command({"type": "click", "element_id": element_id})

    def fill(self, element_id: str, value: str) -> dict[str, Any]:
        control = self._current_control(element_id)
        if not isinstance(value, str) or len(value) > self._MAX_VALUE_LENGTH:
            raise UITestError(f"value must be a string of at most {self._MAX_VALUE_LENGTH} characters")
        self._guard_input(control, value)
        self._count_action()
        return self._command({"type": "fill", "element_id": element_id, "value": value})

    def select(self, element_id: str, value: str) -> dict[str, Any]:
        control = self._current_control(element_id)
        if not isinstance(value, str) or not value.strip() or len(value) > 300:
            raise UITestError("select value must contain 1-300 characters")
        self._guard_input(control, value)
        self._count_action()
        return self._command({"type": "select", "element_id": element_id, "value": value})

    def toggle(self, element_id: str, value: bool) -> dict[str, Any]:
        control = self._current_control(element_id)
        if not isinstance(value, bool):
            raise UITestError("toggle value must be a boolean")
        if control.get("kind") not in {"toggle", "checkbox", "switch"}:
            raise UITestError("The selected element was not identified as a checkbox or switch")
        label = " ".join(str(control.get(key, "")) for key in ("label", "name", "id", "nearby_text"))
        if _SENSITIVE_FIELD_RE.search(label):
            raise UITestError("Sensitive controls cannot be manipulated by autonomous UI testing")
        self._count_action()
        return self._command({"type": "toggle", "element_id": element_id, "value": value})

    def scroll(self, element_id: str) -> dict[str, Any]:
        self._current_control(element_id)
        self._count_action()
        return self._command({"type": "scroll", "element_id": element_id})

    def screenshot(self) -> dict[str, Any]:
        self._count_action()
        return self._command({"type": "screenshot"})

    def finish(self, summary: str = "") -> dict[str, Any]:
        if not self.active:
            raise UITestError("There is no active autonomous UI session to finish")
        if not isinstance(summary, str) or len(summary) > 1000:
            raise UITestError("summary must be a string of at most 1000 characters")
        try:
            bridge_result = self._command({"type": "finish", "summary": summary}, timeout=10)
        finally:
            self._wait_and_cleanup()
        result: dict[str, Any] = {}
        if self.result_path and self.result_path.is_file():
            try:
                loaded = json.loads(self.result_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    result = loaded
            except (OSError, json.JSONDecodeError):
                result = {"status": "report_error", "error": "The UI session report could not be parsed"}
        result.setdefault("status", "completed")
        result["bridge_finish"] = bridge_result
        result["runner_log"] = str(self.log_path.relative_to(self.repo.root_path)) if self.log_path else None
        result["report"] = str(self.result_path.relative_to(self.repo.root_path)) if self.result_path else None
        return result

    def _wait_and_cleanup(self) -> None:
        process = self.process
        if process is not None:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        self._cleanup_process()

    def _cleanup_process(self) -> None:
        self.active = False
        self.base_url = None
        self.token = None
        self.last_observation = None
        self.ui_runner._stop_local_web(self.local_web_process)
        self.local_web_process = None
        if self.log_handle is not None:
            try:
                self.log_handle.close()
            except Exception:
                pass
        self.log_handle = None
        self.process = None

    def abort_if_active(self) -> None:
        if not self.active:
            self._cleanup_process()
            return
        try:
            try:
                self._command({"type": "finish", "summary": "Session closed because the Foundry run ended before finish_ui_session."}, timeout=5)
            except Exception:
                pass
            self._wait_and_cleanup()
        except Exception:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            self._cleanup_process()
