from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlsplit
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

if TYPE_CHECKING:
    from .repo_inspector import DDTRepository


class UITestError(RuntimeError):
    """A UI test plan was invalid, unsafe, or could not be executed."""


# These fixture modes are allowed to execute in the first UI-testing milestone.
# Anything not listed is validation/preview-only until its fixture and risk are reviewed.
_EXECUTABLE_FIXTURE_MODES = {
    "local_web_only",
    "loopback_service",
    "loopback_or_lab_dns",
    "local_tls_only",
    "local_or_help_only",
    "manual_local_dns",
    "offline_file",
    "offline_fixture_only",
    "offline_search_only",
    "offline_small_output",
    "single_lab_host",
    "single_lab_port_only",
    "single_lab_service",
}

_TARGET_FIELD_TOKENS = {
    "target", "host", "hostname", "domain", "ip", "url", "uri",
    "endpoint", "address", "site", "website",
}
_FILE_FIELD_RE = re.compile(
    r"(?:file|path|wordlist|pcap|capture|image|document|archive|input|directory|folder)",
    re.IGNORECASE,
)
_SENSITIVE_FIELD_RE = re.compile(
    r"(?:password|passwd|secret|token|api.?key|private.?key|credential)",
    re.IGNORECASE,
)
_EXECUTE_BUTTON_RE = re.compile(
    r"^(?:run|execute|start|launch|scan|attack|crack|capture|exploit|flood|spoof|inject|brute|enumerate|discover|test|ping|resolve|connect|lookup|fetch|search|crawl|download|generate|process|analyze|convert|extract|check|verify|upload|send)\b",
    re.IGNORECASE,
)
_VALIDATION_EXPECTATION_RE = re.compile(
    r"\b(invalid|must|cannot|can't|required|range|format|valid|error|please|select|enter|missing|unsupported|limit|exceed|fail|not allowed)\b",
    re.IGNORECASE,
)


def _host_from_value(value: str) -> str | None:
    """Return a host for IPs, hostnames and URLs; ignore ordinary form values."""
    raw = value.strip().strip(" ,;()[]{}\"'`")
    if not raw or raw.startswith("-"):
        return None

    candidate = raw
    if re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.IGNORECASE):
        try:
            parsed = urlsplit(raw)
            return parsed.hostname.lower().rstrip(".") if parsed.hostname else None
        except ValueError:
            return None

    candidate = candidate.strip("[]")
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        pass

    if candidate.lower() in {"localhost", "localhost."}:
        return "localhost"

    if re.fullmatch(
        r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}",
        candidate,
    ):
        return candidate.lower().rstrip(".")
    return None


def _normalize_host(value: str) -> str:
    host = _host_from_value(value)
    return host if host else value.strip().lower().rstrip(".")


def _is_target_field(field: str) -> bool:
    # Split camelCase and punctuation so `scriptScan` is not mistaken for `ip`.
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", field).lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", normalized) if token}
    return bool(tokens & _TARGET_FIELD_TOKENS)


class WebdriverUITestRunner:
    """Runs one agent-generated, data-only test plan in one WebdriverIO session.

    The model never supplies JavaScript, CSS selectors, XPath, shell commands, or
    executable paths. The runner converts a small allowlisted action vocabulary to
    WebdriverIO operations and enforces fixture/target restrictions before launch.
    """

    def __init__(
        self,
        repo: DDTRepository,
        enabled: bool = False,
        input_fn: Callable[[str], str] | None = None,
    ):
        self.repo = repo
        self.enabled = enabled
        self.input_fn = input_fn or input
        self.qa_dir = repo.root_path / "qa-agent"
        self.fixture_root = self.qa_dir / "fixtures" / "ddt-qa-fixtures"
        self.runtime_dir = self.qa_dir / "runtime"
        self.report_dir = self.qa_dir / "reports"
        self.config_file = self.qa_dir / "wdio" / "wdio.agent.conf.cjs"
        self.spec_file = self.qa_dir / "wdio" / "agent-plan.spec.cjs"
        self.allowed_targets = {
            _normalize_host(item)
            for item in os.getenv("DDT_QA_ALLOWED_TARGETS", "127.0.0.1,localhost,::1").split(",")
            if item.strip()
        }

    def _fixture_metadata(self, tool_id: str) -> dict[str, Any] | None:
        candidates = [
            self.fixture_root / "tools" / tool_id / "fixture.json",
            self.qa_dir / "fixtures" / "tools" / tool_id / "fixture.json",
        ]
        for path in candidates:
            if path.is_file():
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise UITestError(f"Could not read fixture metadata at {path}: {exc}") from exc
                if not isinstance(value, dict):
                    raise UITestError(f"Fixture metadata must be a JSON object: {path}")
                return value
        return None

    def _resolve_fixture_file(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.fixture_root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.fixture_root.resolve())
        except ValueError as exc:
            raise UITestError(
                f"Fixture path must stay inside {self.fixture_root}: {raw_path}"
            ) from exc
        if not (resolved.is_file() or resolved.is_dir()):
            raise UITestError(f"Fixture path does not exist or is not a file/directory: {resolved}")
        return resolved

    def _validate_plan(self, raw_plan: dict[str, Any]) -> tuple[Any, list[dict[str, Any]], dict[str, Any] | None, list[str]]:
        if not isinstance(raw_plan, dict):
            raise UITestError("UI test plan must be a JSON object")
        tool_id = raw_plan.get("tool_id")
        if not isinstance(tool_id, str) or not tool_id.strip():
            raise UITestError("tool_id is required")
        tool = self.repo.find_tool(tool_id)

        description = raw_plan.get("description", "")
        if not isinstance(description, str) or len(description) > 1000:
            raise UITestError("description must be a string of at most 1000 characters")

        tests = raw_plan.get("tests")
        if not isinstance(tests, list) or not 1 <= len(tests) <= 5:
            raise UITestError("A UI test batch must contain between 1 and 5 test cases")

        fixture_services = raw_plan.get("fixture_services", [])
        if not isinstance(fixture_services, list) or not all(isinstance(item, str) for item in fixture_services):
            raise UITestError("fixture_services must be an array of supported service names")
        if len(fixture_services) > 1 or any(item != "local_web" for item in fixture_services):
            raise UITestError("Only the reviewed 'local_web' fixture service is supported in this increment")

        fixture = self._fixture_metadata(tool.id)
        fixture_mode = str((fixture or {}).get("fixture_mode", "manual_only"))
        if "local_web" in fixture_services and fixture_mode not in {
            "local_web_only", "single_lab_host", "single_lab_port_only", "loopback_service", "local_or_help_only"
        }:
            raise UITestError(
                f"The local_web fixture service is not approved for fixture_mode '{fixture_mode}'"
            )
        normalized_tests: list[dict[str, Any]] = []

        for index, test in enumerate(tests, start=1):
            if not isinstance(test, dict):
                raise UITestError(f"Test {index} must be an object")
            name = test.get("name")
            purpose = test.get("purpose")
            if not isinstance(name, str) or not name.strip() or len(name) > 120:
                raise UITestError(f"Test {index}: name must be 1-120 characters")
            if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 500:
                raise UITestError(f"Test {index}: purpose must be 1-500 characters")

            execute = test.get("execution")
            if not isinstance(execute, bool):
                raise UITestError(f"Test {name}: execution must be true or false")

            actions = test.get("actions")
            if not isinstance(actions, list) or not 1 <= len(actions) <= 25:
                raise UITestError(f"Test {name}: provide between 1 and 25 actions")

            normalized_actions: list[dict[str, Any]] = []
            discovered_targets: set[str] = set()
            target_input_values: list[tuple[str, str]] = []
            referenced_file_values: list[str] = []
            has_run_button = False

            for action_index, action in enumerate(actions, start=1):
                if not isinstance(action, dict):
                    raise UITestError(f"Test {name}, action {action_index}: action must be an object")
                kind = action.get("type")
                field = action.get("field", "")
                value = action.get("value", "")
                text = action.get("text", "")
                if kind not in {"fill", "select", "toggle", "click", "step"}:
                    raise UITestError(
                        f"Test {name}, action {action_index}: unsupported action type {kind!r}"
                    )
                if not all(isinstance(item, str) for item in (field, value, text)):
                    raise UITestError(f"Test {name}, action {action_index}: field/value/text must be strings")
                if len(field) > 80 or len(value) > 1000 or len(text) > 120:
                    raise UITestError(f"Test {name}, action {action_index}: action value is too long")
                if _SENSITIVE_FIELD_RE.search(field):
                    raise UITestError(f"Sensitive field '{field}' is not permitted in automated UI plans")
                if kind in {"fill", "select", "toggle"} and (
                    not field.strip()
                    or len(field) > 80
                    or any(ord(char) < 32 for char in field)
                ):
                    raise UITestError(
                        f"Test {name}: field must be a non-empty HTML name or accessible label of at most 80 characters"
                    )
                if kind == "toggle" and value.lower() not in {"true", "false"}:
                    raise UITestError(f"Test {name}: toggle value must be 'true' or 'false'")
                if kind in {"click", "step"} and (not text.strip() or field or value):
                    raise UITestError(f"Test {name}: {kind} requires text and empty field/value")
                if kind in {"fill", "select"} and text:
                    raise UITestError(f"Test {name}: text must be empty for {kind} actions")
                if kind == "toggle" and len(text) > 120:
                    raise UITestError(f"Test {name}: toggle label text is too long")

                if kind == "click" and _EXECUTE_BUTTON_RE.match(text.strip()):
                    has_run_button = True

                if kind in {"fill", "select"} and _FILE_FIELD_RE.search(field) and value.strip():
                    referenced_file_values.append(value.strip())

                if kind in {"fill", "select"} and _is_target_field(field):
                    target_input_values.append((field, value))

                normalized_actions.append(
                    {"type": kind, "field": field, "value": value, "text": text}
                )

            # Validate every target field when a process button is clicked, even
            # for validation-only tests. This allows safe negative tests (e.g. an
            # invalid port) without permitting a process to run against an
            # unapproved host if frontend validation is broken.
            if execute or has_run_button:
                for field, value in target_input_values:
                    host = _host_from_value(value)
                    if not host:
                        raise UITestError(
                            f"Test {name}: could not validate target value for field '{field}'; use an IP, hostname, or URL"
                        )
                    if host not in self.allowed_targets:
                        raise UITestError(
                            f"Test {name}: target '{host}' is not in DDT_QA_ALLOWED_TARGETS"
                        )
                    discovered_targets.add(host)

            expected_contains = test.get("expected_contains", [])
            expected_not_contains = test.get("expected_not_contains", [])
            if not isinstance(expected_contains, list) or not isinstance(expected_not_contains, list):
                raise UITestError(f"Test {name}: expected_contains and expected_not_contains must be arrays")
            if len(expected_contains) > 12 or len(expected_not_contains) > 12:
                raise UITestError(f"Test {name}: no more than 12 assertions of each kind are allowed")
            if not all(isinstance(item, str) and 0 < len(item) <= 300 for item in expected_contains + expected_not_contains):
                raise UITestError(f"Test {name}: assertions must be non-empty strings up to 300 characters")
            if not expected_contains and not expected_not_contains:
                raise UITestError(f"Test {name}: at least one observable assertion is required")

            timeout = test.get("timeout_seconds", 30)
            if not isinstance(timeout, int) or isinstance(timeout, bool) or not 5 <= timeout <= 120:
                raise UITestError(f"Test {name}: timeout_seconds must be between 5 and 120")

            targets = test.get("execution_targets", [])
            files = test.get("fixture_files", [])
            if not isinstance(targets, list) or not isinstance(files, list):
                raise UITestError(f"Test {name}: execution_targets and fixture_files must be arrays")
            if len(targets) > 5 or len(files) > 5:
                raise UITestError(f"Test {name}: no more than five execution targets or fixture paths are allowed")
            if not all(isinstance(item, str) for item in targets + files):
                raise UITestError(f"Test {name}: execution_targets and fixture_files must contain strings")

            normalized_declared_targets: set[str] = set()
            for target in targets:
                host = _host_from_value(target)
                if not host or host not in self.allowed_targets:
                    raise UITestError(f"Test {name}: declared target '{target}' is not allowlisted")
                normalized_declared_targets.add(host)
            if discovered_targets - normalized_declared_targets:
                missing = ", ".join(sorted(discovered_targets - normalized_declared_targets))
                raise UITestError(f"Test {name}: execution_targets must explicitly include: {missing}")

            resolved_files = [str(self._resolve_fixture_file(path)) for path in files]
            for raw_file_value in referenced_file_values:
                resolved_input = str(self._resolve_fixture_file(raw_file_value))
                if resolved_input not in resolved_files:
                    raise UITestError(
                        f"Test {name}: file field values must be listed in fixture_files: {raw_file_value}"
                    )

            if execute:
                if fixture_mode not in _EXECUTABLE_FIXTURE_MODES:
                    raise UITestError(
                        f"Execution blocked for {tool.name}: fixture_mode '{fixture_mode}' is not approved for automated execution."
                    )
                if not has_run_button:
                    raise UITestError(f"Test {name}: execution=true requires an explicit Run/Execute button click")
                if not normalized_declared_targets and not resolved_files:
                    raise UITestError(
                        f"Test {name}: execution requires an allowlisted target or a verified local fixture file"
                    )
            elif has_run_button:
                if not (discovered_targets & normalized_declared_targets) and not resolved_files:
                    raise UITestError(
                        f"Test {name}: a Run/Execute button can start a process; set execution=true or provide an explicitly allowlisted target/fixture for a validation-only click"
                    )
                if not any(_VALIDATION_EXPECTATION_RE.search(item) for item in expected_contains):
                    raise UITestError(
                        f"Test {name}: a validation-only Run-button click must assert an expected validation/error message"
                    )

            if "local_web" in fixture_services and (execute or has_run_button):
                if not (normalized_declared_targets & {"127.0.0.1", "localhost", "::1"}):
                    raise UITestError(
                        f"Test {name}: local_web service can only be used with an explicitly declared loopback target"
                    )

            normalized_tests.append(
                {
                    "name": name.strip(),
                    "purpose": purpose.strip(),
                    "execution": execute,
                    "actions": normalized_actions,
                    "expected_contains": expected_contains,
                    "expected_not_contains": expected_not_contains,
                    "execution_targets": sorted(normalized_declared_targets),
                    "fixture_files": resolved_files,
                    "timeout_seconds": timeout,
                }
            )

        if not self.config_file.is_file() or not self.spec_file.is_file():
            raise UITestError(
                "WebdriverIO agent runner files are missing. Install qa-agent/wdio from the UI-testing patch first."
            )
        return tool, normalized_tests, fixture, fixture_services

    def _local_web_is_ready(self) -> bool:
        try:
            with urlopen("http://127.0.0.1:18080/health", timeout=1) as response:
                body = response.read(2048).decode("utf-8", errors="replace")
                return response.status == 200 and '"fixture":"ddt-qa"' in body
        except (OSError, URLError, HTTPError, TimeoutError):
            return False

    def _start_local_web(self) -> subprocess.Popen[str] | None:
        """Start the repository's fixed loopback-only HTTP fixture if needed."""
        server = self.fixture_root / "common" / "local-web" / "server.py"
        if not server.is_file():
            raise UITestError(f"The local web fixture server is missing: {server}")
        source = server.read_text(encoding="utf-8", errors="replace")
        if "ThreadingHTTPServer(('127.0.0.1',18080)" not in source.replace(" ", ""):
            raise UITestError("The local web fixture server no longer matches the reviewed loopback-only binding")
        if self._local_web_is_ready():
            return None

        process = subprocess.Popen(
            [sys.executable, str(server)],
            cwd=server.parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise UITestError(f"Local web fixture exited during startup (exit code {process.returncode})")
            if self._local_web_is_ready():
                return process
            time.sleep(0.2)
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        raise UITestError("Local web fixture did not become healthy on 127.0.0.1:18080 within 10 seconds")

    @staticmethod
    def _stop_local_web(process: subprocess.Popen[str] | None) -> None:
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    def _approval_summary(self, tool: Any, tests: list[dict[str, Any]], fixture: dict[str, Any] | None, fixture_services: list[str]) -> None:
        print("\nDDT UI TEST PLAN — WebdriverIO")
        print(f"Tool: {tool.name} ({tool.path})")
        print(f"Fixture mode: {(fixture or {}).get('fixture_mode', 'manual_only')}")
        print(f"Fixture services: {', '.join(fixture_services) if fixture_services else 'none'}")
        for index, test in enumerate(tests, start=1):
            print(f"\n{index}. {test['name']}: {test['purpose']}")
            print(f"   Execution: {'YES' if test['execution'] else 'UI only'}")
            if test["execution_targets"]:
                print(f"   Targets: {', '.join(test['execution_targets'])}")
            if test["fixture_files"]:
                print(f"   Fixtures: {', '.join(Path(p).name for p in test['fixture_files'])}")
            for action in test["actions"]:
                if action["type"] == "click":
                    print(f"   - click button: {action['text']}")
                elif action["type"] == "step":
                    print(f"   - navigate step: {action['text']}")
                elif action["type"] == "toggle":
                    print(f"   - set {action['field']} = {action['value']}")
                else:
                    shown = action["value"][:100]
                    print(f"   - {action['type']} {action['field']} = {shown}")
            print(f"   Assertions: {len(test['expected_contains']) + len(test['expected_not_contains'])}")
        print("\nThe test will operate the real DDT desktop UI. Process-running actions are limited by fixture mode and target/file allowlists.")

    def run_plan(self, raw_plan: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {
                "status": "blocked",
                "reason": "WebdriverIO UI testing is disabled. Start the QA agent with --enable-ui-testing.",
            }

        tool, tests, fixture, fixture_services = self._validate_plan(raw_plan)
        self._approval_summary(tool, tests, fixture, fixture_services)
        approval = self.input_fn("\nType RUN DDT UI QA PLAN to execute this batch: ").strip()
        if approval != "RUN DDT UI QA PLAN":
            return {"status": "cancelled", "reason": "Operator approval was not provided; no UI tests were run."}

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        plan_path = self.runtime_dir / f"ui-plan-{run_id}.json"
        result_path = self.report_dir / f"ui-test-{run_id}.json"
        plan_path.write_text(
            json.dumps({"tool": {"id": tool.id, "name": tool.name, "path": tool.path}, "tests": tests}, indent=2),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["DDT_QA_UI_PLAN_PATH"] = str(plan_path)
        env["DDT_QA_UI_RESULT_PATH"] = str(result_path)
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
            raise UITestError("Could not find node_modules/.bin/wdio, Corepack, or Yarn. Install the WDIO dependencies first.")

        total_timeout = min(900, 180 + sum(test["timeout_seconds"] for test in tests))
        started = time.monotonic()
        local_web_process: subprocess.Popen[str] | None = None
        try:
            if "local_web" in fixture_services:
                local_web_process = self._start_local_web()
            completed = subprocess.run(
                command,
                cwd=self.repo.root_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=total_timeout,
                check=False,
            )
            runner_duration = round(time.monotonic() - started, 2)
        except subprocess.TimeoutExpired as exc:
            runner_duration = round(time.monotonic() - started, 2)
            result_path.write_text(
                json.dumps(
                    {
                        "status": "timeout",
                        "tool": tool.name,
                        "duration_seconds": runner_duration,
                        "error": f"WebdriverIO exceeded {total_timeout} seconds",
                        "stdout_tail": (exc.stdout or "")[-12000:],
                        "stderr_tail": (exc.stderr or "")[-12000:],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            return {"status": "timeout", "report": str(result_path.relative_to(self.repo.root_path)), "duration_seconds": runner_duration}
        finally:
            self._stop_local_web(local_web_process)
            plan_path.unlink(missing_ok=True)

        if result_path.is_file():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                result = {"status": "runner_error", "error": "WDIO result file contained invalid JSON"}
        else:
            result = {"status": "runner_error", "error": "WDIO did not write a result file"}

        results = result.get("tests", []) if isinstance(result, dict) else []
        passed = sum(1 for item in results if item.get("status") == "passed")
        failed = sum(1 for item in results if item.get("status") == "failed")
        result.update(
            {
                "tool_id": tool.id,
                "tool_name": tool.name,
                "duration_seconds": runner_duration,
                "tests_per_minute": round(len(results) / max(runner_duration / 60, 0.001), 2) if results else 0.0,
                "wdio_exit_code": completed.returncode,
                "passed": passed,
                "failed": failed,
                "stdout_tail": (completed.stdout or "")[-16000:],
                "stderr_tail": (completed.stderr or "")[-16000:],
            }
        )
        if failed or completed.returncode != 0:
            result["status"] = "failed" if results else "runner_error"
        elif results and passed == len(tests):
            result["status"] = "passed"
        else:
            result["status"] = result.get("status", "incomplete")
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "status": result["status"],
            "tool_id": tool.id,
            "tool_name": tool.name,
            "passed": passed,
            "failed": failed,
            "duration_seconds": runner_duration,
            "tests_per_minute": result.get("tests_per_minute", 0.0),
            "execution_backend": "webdriverio_tauri_ui",
            "fixture_services": fixture_services,
            "report": str(result_path.relative_to(self.repo.root_path)),
            "tests": results,
            "runner_error": result.get("error"),
        }
