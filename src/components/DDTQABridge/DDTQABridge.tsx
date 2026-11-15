import { useCallback, useEffect, useRef, useState } from "react";
import { CommandHelper } from "../../utils/CommandHelper";

type BridgeStatus = "disconnected" | "connecting" | "connected" | "error";

type ExecuteRequest = {
    type: "execute";
    request_id: string;
    tool_id: string;
    command: string;
    args: string[];
    timeout_seconds: number;
};

type ActiveExecution = {
    requestId: string;
    kill: () => Promise<void>;
    timedOut: boolean;
};

const BRIDGE_URL = "ws://127.0.0.1:8765";
const MAX_ARGS = 40;
const MAX_ARG_LENGTH = 512;

/**
 * Development-only bridge between the local Python QA agent and DDT's real
 * CommandHelper. The Python agent owns the loopback WebSocket server; this
 * frontend connects outbound and executes requests through Tauri Shell.
 */
export default function DDTQABridge() {
    const [token, setToken] = useState("");
    const [status, setStatus] = useState<BridgeStatus>("disconnected");
    const [message, setMessage] = useState("Enter the one-time token printed by the Python QA agent.");
    const [expanded, setExpanded] = useState(true);
    const socketRef = useRef<WebSocket | null>(null);
    const activeExecutionRef = useRef<ActiveExecution | null>(null);

    const send = useCallback((socket: WebSocket, payload: Record<string, unknown>) => {
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(payload));
        }
    }, []);

    const executeRequest = useCallback(
        async (socket: WebSocket, request: ExecuteRequest) => {
            if (activeExecutionRef.current) {
                send(socket, {
                    type: "execution_error",
                    request_id: request.request_id,
                    error: "DDT is already running a QA command. Wait for it to finish.",
                });
                return;
            }

            if (
                !request.request_id ||
                typeof request.command !== "string" ||
                !/^[A-Za-z0-9_.+-]+$/.test(request.command) ||
                !Array.isArray(request.args) ||
                request.args.length > MAX_ARGS ||
                !request.args.every((arg) => typeof arg === "string" && arg.length <= MAX_ARG_LENGTH) ||
                !Number.isInteger(request.timeout_seconds) ||
                request.timeout_seconds < 1 ||
                request.timeout_seconds > 60
            ) {
                send(socket, {
                    type: "execution_error",
                    request_id: request.request_id,
                    error: "Invalid QA execution request. Check executable, arguments and timeout.",
                });
                return;
            }

            let timeoutHandle: number | undefined;
            try {
                const process = await CommandHelper.runCommandForQA(
                    request.command,
                    request.args,
                    (stream, data) => {
                        send(socket, {
                            type: "output",
                            request_id: request.request_id,
                            stream,
                            data,
                        });
                    },
                );

                const active: ActiveExecution = {
                    requestId: request.request_id,
                    kill: process.kill,
                    timedOut: false,
                };
                activeExecutionRef.current = active;

                send(socket, {
                    type: "started",
                    request_id: request.request_id,
                    pid: process.pid,
                    tool_id: request.tool_id,
                });

                timeoutHandle = window.setTimeout(() => {
                    const current = activeExecutionRef.current;
                    if (current?.requestId === request.request_id) {
                        current.timedOut = true;
                        void current.kill().catch((error) => {
                            send(socket, {
                                type: "execution_error",
                                request_id: request.request_id,
                                error: `Could not terminate timed-out process: ${String(error)}`,
                            });
                        });
                    }
                }, request.timeout_seconds * 1000);

                const completion = await process.completed;
                if (timeoutHandle !== undefined) {
                    window.clearTimeout(timeoutHandle);
                }
                if (completion.error) {
                    send(socket, {
                        type: "execution_error",
                        request_id: request.request_id,
                        error: completion.error,
                    });
                    return;
                }

                const timedOut = activeExecutionRef.current?.requestId === request.request_id
                    ? activeExecutionRef.current.timedOut
                    : false;

                send(socket, {
                    type: "completed",
                    request_id: request.request_id,
                    code: completion.code,
                    signal: completion.signal,
                    timed_out: timedOut,
                    stdout: completion.stdout,
                    stderr: completion.stderr,
                });
            } catch (error) {
                if (timeoutHandle !== undefined) {
                    window.clearTimeout(timeoutHandle);
                }
                send(socket, {
                    type: "execution_error",
                    request_id: request.request_id,
                    error: error instanceof Error ? error.message : String(error),
                });
            } finally {
                if (activeExecutionRef.current?.requestId === request.request_id) {
                    activeExecutionRef.current = null;
                }
            }
        },
        [send],
    );

    const connect = useCallback(() => {
        if (!token.trim()) {
            setStatus("error");
            setMessage("Enter the token printed by the Python QA agent first.");
            return;
        }

        socketRef.current?.close();
        setStatus("connecting");
        setMessage("Connecting to the local Python QA agent...");

        const socket = new WebSocket(BRIDGE_URL);
        socketRef.current = socket;

        socket.onopen = () => {
            send(socket, { type: "auth", token: token.trim() });
        };

        socket.onmessage = (event) => {
            let payload: Record<string, unknown>;
            try {
                payload = JSON.parse(String(event.data));
            } catch {
                setMessage("Received an invalid message from the QA agent.");
                return;
            }

            if (payload.type === "authenticated") {
                setStatus("connected");
                setMessage("Connected. Approved QA requests will execute through DDT CommandHelper.");
                return;
            }

            if (payload.type === "execute") {
                void executeRequest(socket, payload as unknown as ExecuteRequest);
                return;
            }

            if (payload.type === "cancel") {
                const active = activeExecutionRef.current;
                if (active && active.requestId === payload.request_id) {
                    void active.kill().catch((error) => {
                        send(socket, {
                            type: "execution_error",
                            request_id: active.requestId,
                            error: `Cancellation failed: ${String(error)}`,
                        });
                    });
                }
            }
        };

        socket.onerror = () => {
            setStatus("error");
            setMessage("Could not connect. Check that the Python QA agent is running and the port is 8765.");
        };

        socket.onclose = () => {
            setStatus("disconnected");
            setMessage("Disconnected from the Python QA agent.");
            const active = activeExecutionRef.current;
            if (active) {
                void active.kill().catch(() => undefined);
                activeExecutionRef.current = null;
            }
        };
    }, [executeRequest, send, token]);

    const disconnect = useCallback(() => {
        const active = activeExecutionRef.current;
        if (active) {
            void active.kill().catch(() => undefined);
            activeExecutionRef.current = null;
        }
        socketRef.current?.close();
        socketRef.current = null;
        setStatus("disconnected");
        setMessage("Disconnected.");
    }, []);

    useEffect(() => {
        return () => {
            const active = activeExecutionRef.current;
            if (active) {
                void active.kill().catch(() => undefined);
            }
            socketRef.current?.close();
        };
    }, []);

    const statusColour = status === "connected" ? "#2f9e44" : status === "error" ? "#e03131" : "#868e96";

    return (
        <div
            style={{
                position: "fixed",
                right: 16,
                bottom: 16,
                zIndex: 99999,
                width: expanded ? 330 : "auto",
                padding: 12,
                color: "#f8f9fa",
                background: "#20242b",
                border: "1px solid #495057",
                borderRadius: 10,
                boxShadow: "0 4px 18px rgba(0,0,0,.35)",
                fontFamily: "Arial, sans-serif",
                fontSize: 13,
            }}
        >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                <strong>DDT QA Bridge</strong>
                <span style={{ color: statusColour, fontWeight: 700 }}>{status.toUpperCase()}</span>
                <button type="button" onClick={() => setExpanded((value) => !value)}>
                    {expanded ? "−" : "+"}
                </button>
            </div>

            {expanded && (
                <div style={{ marginTop: 10 }}>
                    <p style={{ margin: "0 0 8px", lineHeight: 1.4 }}>{message}</p>
                    <label htmlFor="ddt-qa-bridge-token" style={{ display: "block", marginBottom: 4 }}>
                        One-time connection token
                    </label>
                    <input
                        id="ddt-qa-bridge-token"
                        type="password"
                        value={token}
                        onChange={(event) => setToken(event.currentTarget.value)}
                        placeholder="Paste token from Python terminal"
                        autoComplete="off"
                        style={{ boxSizing: "border-box", width: "100%", padding: 8, marginBottom: 8 }}
                        disabled={status === "connected"}
                    />
                    {status === "connected" ? (
                        <button type="button" onClick={disconnect} style={{ width: "100%", padding: 8 }}>
                            Disconnect
                        </button>
                    ) : (
                        <button type="button" onClick={connect} style={{ width: "100%", padding: 8 }}>
                            Connect to QA Agent
                        </button>
                    )}
                    <small style={{ display: "block", marginTop: 8, color: "#adb5bd" }}>
                        Development mode only. QA commands run through DDT's Tauri Shell and CommandHelper.
                    </small>
                </div>
            )}
        </div>
    );
}
