from __future__ import annotations

import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .repo_inspector import DDTRepository, RepositoryError


class DynamicTestError(RuntimeError):
    pass


# Only these harmless discovery probes are run automatically. The model cannot
# change this list or add arguments to a probe.
_SAFE_PROBES: tuple[tuple[str, ...], ...] = (
    ("--help",),
    ("-h",),
    ("--version",),
    ("-V",),
)

# Conservative deny-list for obviously dangerous modes. It is not the security
# boundary by itself: every dynamic test is also printed and explicitly approved
# by the operator, restricted to a declared dependency and checked for targets.
_DANGEROUS_EXACT = {
    "--flood", "--dos", "--os-shell", "--os-pwn", "--sql-shell",
    "--dump", "--dump-all", "--passwords", "--brute", "--bruteforce",
    "--file-read", "--file-write", "--reverse-shell", "--bind-shell",
    "--upload", "--download", "--delete", "--remove", "--purge",
}
_DANGEROUS_PREFIXES = (
    "--os-shell=", "--sql-shell=", "--dump=", "--file-write=", "--file-read=",
    "--reverse-shell=", "--bind-shell=", "--flood=", "--dos=",
)
_BLOCKED_SCRIPT_WORDS = {"brute", "bruteforce", "dos", "exploit", "external", "broadcast"}
# Do not expose interpreters, privilege escalation, package managers or system
# administration binaries through the AI-to-DDT bridge.
_BLOCKED_INTEGRATION_EXECUTABLES = {
    "bash", "sh", "dash", "zsh", "fish", "sudo", "pkexec",
    "python", "python2", "python3", "python3.10", "python3.11", "python3.12",
    "pip", "pip2", "pip3", "kill", "rm", "dd", "chmod", "chown",
    "systemctl", "service", "mount", "umount",
}
_FILE_EXTENSIONS = {
    ".txt", ".json", ".xml", ".yaml", ".yml", ".ini", ".conf", ".cfg", ".log",
    ".csv", ".pcap", ".pcapng", ".cap", ".db", ".sqlite", ".hash", ".lst",
    ".wordlist", ".pem", ".key", ".crt", ".cer", ".zip", ".gz", ".tar", ".rar",
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bin", ".img", ".iso", ".html",
    ".htm", ".js", ".py", ".ts", ".tsx", ".sh", ".md",
}


def _host_from_value(value: str) -> str | None:
    """Extract a host-like target from an argument, if it looks like one."""
    raw = value.strip().strip(",;()[]{}\"'`")
    if not raw or raw.startswith("-"):
        return None

    # URLs embedded in --key=value or similar argument values.
    url_match = re.search(r"https?://[^\s,;]+", raw, re.IGNORECASE)
    if url_match:
        try:
            host = urlsplit(url_match.group(0)).hostname
            return host.lower().rstrip(".") if host else None
        except ValueError:
            return None

    # Skip file paths and obvious input filenames.
    if "/" in raw or "\\" in raw or Path(raw).suffix.lower() in _FILE_EXTENSIONS:
        return None

    candidate = raw.strip("[]")
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        pass

    if candidate.lower() in {"localhost", "localhost."}:
        return "localhost"

    # DNS names need at least one dot; don't mistake scan modes/labels for hosts.
    if len(candidate) <= 253 and re.fullmatch(
        r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}",
        candidate,
    ):
        return candidate.lower().rstrip(".")
    return None


def _normalize_allowlist(values: list[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        host = _host_from_value(value)
        if host:
            normalized.add(host)
        else:
            normalized.add(value.strip().lower().rstrip("."))
    return normalized


class DynamicTestRunner:
    """Runs short, AI-designed CLI test batches without per-tool scripts/profiles.

    The model provides argv arrays and assertions. This runner validates the tool
    executable against the component's declared dependencies, constrains network
    targets to DDT_QA_ALLOWED_TARGETS, blocks selected high-risk modes, prints
    every command, requires one operator confirmation for the batch, and invokes
    either through direct subprocess execution or through the running DDT app's
    authenticated CommandHelper bridge. Test plans are logged as JSON, not scripts.
    """

    def __init__(
        self,
        repo: DDTRepository,
        enabled: bool = False,
        input_fn: Callable[[str], str] | None = None,
        integration_bridge: Any | None = None,
    ):
        self.repo = repo
        self.enabled = enabled
        self.input_fn = input_fn or input
        self.integration_bridge = integration_bridge
        self.allowed_targets = [
            item.strip()
            for item in os.getenv("DDT_QA_ALLOWED_TARGETS", "127.0.0.1,localhost,::1").split(",")
            if item.strip()
        ]
        self._allowed_hosts = _normalize_allowlist(self.allowed_targets)
        self.runtime_dir = repo.root_path / "qa-agent" / "runtime"
        self.report_path = repo.root_path / "qa-agent" / "reports" / "dynamic-executions.jsonl"

    def probe_cli(self, tool_id: str) -> dict[str, Any]:
        """Run fixed harmless help/version probes.

        In DDT integration mode probes go through the running DDT app's
        CommandHelper. Otherwise they use the historical local subprocess path.
        """
        if not self.enabled:
            return {"status": "blocked", "reason": "Dynamic execution is disabled. Start with --enable-dynamic-testing."}

        tool = self.repo.find_tool(tool_id)
        dependencies = self.repo.inspect_tool(tool.id)["dependencies"]
        if not dependencies:
            return {"status": "needs_review", "tool_id": tool.id, "reason": "No executable dependency could be extracted from the tool component."}

        results: list[dict[str, Any]] = []
        for command in dependencies:
            if self.integration_bridge is not None and Path(command).name.lower() in _BLOCKED_INTEGRATION_EXECUTABLES:
                results.append({"command": command, "status": "blocked", "reason": "This executable is not permitted through DDT QA integration."})
                continue
            executable = shutil.which(command)
            if not executable:
                results.append({"command": command, "status": "missing", "path": None})
                continue

            command_results = []
            dependency_status = "probed"
            for probe_args in _SAFE_PROBES:
                try:
                    if self.integration_bridge is not None:
                        execution = self.integration_bridge.execute(
                            command=command,
                            args=list(probe_args),
                            timeout_seconds=8,
                            tool_id=tool.id,
                        )
                        if execution.get("status") == "timeout":
                            command_results.append({"args": list(probe_args), "status": "timeout", "execution_backend": "ddt_commandhelper"})
                            continue
                        if execution.get("status") != "completed":
                            dependency_status = "error"
                            command_results.append({
                                "args": list(probe_args),
                                "status": "error",
                                "error": execution.get("reason", "DDT bridge execution failed."),
                                "execution_backend": "ddt_commandhelper",
                            })
                            break
                        output = (execution.get("stdout") or "") + "\n" + (execution.get("stderr") or "")
                        exit_code = execution.get("exit_code")
                        backend = "ddt_commandhelper"
                    else:
                        completed = subprocess.run(
                            [executable, *probe_args],
                            cwd=self._runtime_cwd(),
                            capture_output=True,
                            text=True,
                            errors="replace",
                            timeout=8,
                            check=False,
                            shell=False,
                            env=self._minimal_env(),
                        )
                        output = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-5000:]
                        exit_code = completed.returncode
                        backend = "direct_cli_subprocess"

                    command_results.append({
                        "args": list(probe_args),
                        "exit_code": exit_code,
                        "output": output[-5000:],
                        "execution_backend": backend,
                    })
                    if exit_code == 0 or output.strip():
                        break
                except subprocess.TimeoutExpired:
                    command_results.append({"args": list(probe_args), "status": "timeout"})
                except Exception as exc:
                    dependency_status = "error"
                    command_results.append({"args": list(probe_args), "status": "error", "error": str(exc)})
                    if self.integration_bridge is not None:
                        break
            results.append({"command": command, "status": dependency_status, "path": executable, "probes": command_results})

        overall = "available" if any(item["status"] == "probed" for item in results) else "blocked"
        return {
            "status": overall,
            "tool_id": tool.id,
            "dependencies": results,
            "execution_backend": "ddt_commandhelper" if self.integration_bridge is not None else "direct_cli_subprocess",
        }

    def run_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "blocked", "reason": "Dynamic execution is disabled. Start with --enable-dynamic-testing."}

        tool = self.repo.find_tool(str(plan.get("tool_id", "")))
        dependencies = self.repo.inspect_tool(tool.id)["dependencies"]
        if not dependencies:
            raise DynamicTestError(f"No declared executable dependencies found for {tool.name}.")

        tests = plan.get("tests")
        if not isinstance(tests, list) or not tests or len(tests) > 5:
            raise DynamicTestError("A dynamic plan must contain between 1 and 5 test cases.")

        prepared: list[dict[str, Any]] = []
        for index, case in enumerate(tests, start=1):
            if not isinstance(case, dict):
                raise DynamicTestError(f"Test case {index} must be an object.")
            command = str(case.get("command", ""))
            if command not in dependencies:
                raise DynamicTestError(f"Test case {index}: '{command}' is not a declared dependency for {tool.name}.")
            if self.integration_bridge is not None and Path(command).name.lower() in _BLOCKED_INTEGRATION_EXECUTABLES:
                raise DynamicTestError(f"Test case {index}: executable '{command}' is blocked from DDT QA integration.")
            executable = shutil.which(command)
            if not executable:
                raise DynamicTestError(f"Executable '{command}' is not installed or not on PATH.")

            argv = case.get("args")
            if not isinstance(argv, list) or len(argv) > 40 or not all(isinstance(arg, str) and len(arg) <= 512 for arg in argv):
                raise DynamicTestError(f"Test case {index}: args must be an array of at most 40 strings (512 chars each).")
            if any("\x00" in arg or "\n" in arg or "\r" in arg for arg in argv):
                raise DynamicTestError(f"Test case {index}: null/newline characters are not allowed in arguments.")
            self._check_risky_arguments(argv, index)
            target_indexes = case.get("target_arg_indexes", [])
            if not isinstance(target_indexes, list) or not all(isinstance(i, int) for i in target_indexes):
                raise DynamicTestError(f"Test case {index}: target_arg_indexes must be an integer array.")
            self._validate_targets(argv, target_indexes, index)

            timeout = int(case.get("timeout_seconds", 20))
            if not 1 <= timeout <= 60:
                raise DynamicTestError(f"Test case {index}: timeout must be between 1 and 60 seconds.")
            expected_codes = case.get("expected_exit_codes", [0])
            contains = case.get("expected_contains", [])
            not_contains = case.get("expected_not_contains", [])
            if not isinstance(expected_codes, list) or not expected_codes or not all(isinstance(v, int) for v in expected_codes):
                raise DynamicTestError(f"Test case {index}: expected_exit_codes must be a non-empty integer array.")
            if not isinstance(contains, list) or not all(isinstance(v, str) for v in contains):
                raise DynamicTestError(f"Test case {index}: expected_contains must be a string array.")
            if not isinstance(not_contains, list) or not all(isinstance(v, str) for v in not_contains):
                raise DynamicTestError(f"Test case {index}: expected_not_contains must be a string array.")

            prepared.append({
                "name": str(case.get("name", f"Test {index}"))[:120],
                "purpose": str(case.get("purpose", ""))[:500],
                "command": command,
                "executable": executable,
                "args": argv,
                "timeout_seconds": timeout,
                "expected_exit_codes": expected_codes,
                "expected_contains": contains,
                "expected_not_contains": not_contains,
                "targets": self._detected_targets(argv, target_indexes),
            })

        self._display_plan(tool.name, prepared)
        try:
            answer = self.input_fn("Type RUN DDT QA PLAN to execute this batch: ").strip()
        except (EOFError, OSError):
            return {"status": "blocked", "reason": "No interactive approval was available; no test was executed."}
        if answer != "RUN DDT QA PLAN":
            return {"status": "cancelled", "reason": "Operator did not approve the dynamic test batch."}

        results: list[dict[str, Any]] = []
        execution_backend = "ddt_commandhelper" if self.integration_bridge is not None else "direct_cli_subprocess"
        for case in prepared:
            started = datetime.now(timezone.utc).isoformat()
            try:
                if self.integration_bridge is not None:
                    execution = self.integration_bridge.execute(
                        command=case["command"],
                        args=case["args"],
                        timeout_seconds=case["timeout_seconds"],
                        tool_id=tool.id,
                    )
                    if execution.get("status") == "timeout":
                        results.append({
                            "name": case["name"], "purpose": case["purpose"], "status": "timeout",
                            "command": case["command"], "args": case["args"], "targets": case["targets"],
                            "timeout_seconds": case["timeout_seconds"],
                            "output": ((execution.get("stdout") or "") + "\n" + (execution.get("stderr") or ""))[-10000:],
                            "execution_backend": execution_backend,
                            "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                        })
                        continue
                    if execution.get("status") != "completed":
                        results.append({
                            "name": case["name"], "purpose": case["purpose"], "status": "error",
                            "command": case["command"], "args": case["args"], "targets": case["targets"],
                            "error": execution.get("reason", "DDT bridge execution failed."),
                            "execution_backend": execution_backend,
                            "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                        })
                        continue

                    returncode = execution.get("exit_code")
                    stdout = execution.get("stdout") or ""
                    stderr = execution.get("stderr") or ""
                    output = (stdout + "\n" + stderr)[-10000:]
                else:
                    completed = subprocess.run(
                        [case["executable"], *case["args"]],
                        cwd=self._runtime_cwd(),
                        capture_output=True,
                        text=True,
                        errors="replace",
                        timeout=case["timeout_seconds"],
                        check=False,
                        shell=False,
                        env=self._minimal_env(),
                    )
                    returncode = completed.returncode
                    output = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-10000:]

                checks = []
                checks.append({
                    "assertion": f"exit code in {case['expected_exit_codes']}",
                    "passed": returncode in case["expected_exit_codes"],
                })

                # Normalize whitespace for reliable CLI output assertions.
                normalized_output = re.sub(r"\s+", " ", output).strip()
                checks.extend(
                    {
                        "assertion": f"contains: {value}",
                        "passed": re.sub(r"\s+", " ", value).strip() in normalized_output,
                    }
                    for value in case["expected_contains"]
                )
                checks.extend(
                    {
                        "assertion": f"does not contain: {value}",
                        "passed": re.sub(r"\s+", " ", value).strip() not in normalized_output,
                    }
                    for value in case["expected_not_contains"]
                )

                has_output_assertions = bool(case["expected_contains"] or case["expected_not_contains"])
                assertions_passed = all(check["passed"] for check in checks)
                status = (
                    "passed"
                    if assertions_passed and has_output_assertions
                    else ("failed" if not assertions_passed else "executed_unverified")
                )

                results.append({
                    "name": case["name"], "purpose": case["purpose"], "status": status,
                    "command": case["command"], "args": case["args"], "targets": case["targets"],
                    "exit_code": returncode, "checks": checks, "output": output,
                    "execution_backend": execution_backend,
                    "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                })
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                results.append({
                    "name": case["name"], "purpose": case["purpose"], "status": "timeout",
                    "command": case["command"], "args": case["args"], "targets": case["targets"],
                    "timeout_seconds": case["timeout_seconds"], "output": (stdout + "\n" + stderr)[-10000:],
                    "execution_backend": execution_backend,
                    "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as exc:
                results.append({
                    "name": case["name"], "purpose": case["purpose"], "status": "error",
                    "command": case["command"], "args": case["args"], "targets": case["targets"],
                    "error": f"{type(exc).__name__}: {exc}",
                    "execution_backend": execution_backend,
                    "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                })

        batch = {
            "tool_id": tool.id,
            "tool_name": tool.name,
            "plan_description": str(plan.get("description", ""))[:1000],
            "operator_approved": True,
            "execution_backend": execution_backend,
            "results": results,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._append_report(batch)
        return {"status": "completed", "tool_id": tool.id, "test_count": len(results), "results": results}

    def _validate_targets(self, argv: list[str], indexes: list[int], case_index: int) -> None:
        for idx in indexes:
            if idx < 0 or idx >= len(argv):
                raise DynamicTestError(f"Test case {case_index}: target_arg_indexes contains invalid index {idx}.")
            host = _host_from_value(argv[idx])
            if not host:
                raise DynamicTestError(f"Test case {case_index}: argument {idx} was declared as a target but no host could be parsed.")
            if host not in self._allowed_hosts:
                raise DynamicTestError(f"Test case {case_index}: target '{host}' is not in DDT_QA_ALLOWED_TARGETS.")

        # Independently inspect all URL/IP/FQDN-looking arguments so the model
        # cannot avoid scope enforcement by omitting target_arg_indexes.
        for value in argv:
            host = _host_from_value(value)
            if host and host not in self._allowed_hosts:
                raise DynamicTestError(f"Test case {case_index}: detected target '{host}' is not in DDT_QA_ALLOWED_TARGETS.")

    def _detected_targets(self, argv: list[str], indexes: list[int]) -> list[str]:
        found = set()
        for value in argv:
            host = _host_from_value(value)
            if host:
                found.add(host)
        for idx in indexes:
            if 0 <= idx < len(argv):
                host = _host_from_value(argv[idx])
                if host:
                    found.add(host)
        return sorted(found)

    @staticmethod
    def _check_risky_arguments(argv: list[str], case_index: int) -> None:
        for index, arg in enumerate(argv):
            normalized = arg.lower()
            if normalized in _DANGEROUS_EXACT or any(normalized.startswith(p) for p in _DANGEROUS_PREFIXES):
                raise DynamicTestError(f"Test case {case_index}: blocked high-risk option '{arg}'.")
            if normalized in {"--script", "-scripttype"} and index + 1 < len(argv):
                scripts = argv[index + 1].lower()
                if any(word in scripts for word in _BLOCKED_SCRIPT_WORDS):
                    raise DynamicTestError(f"Test case {case_index}: blocked potentially dangerous script selection '{scripts}'.")
            if normalized.startswith("--script="):
                scripts = normalized.split("=", 1)[1]
                if any(word in scripts for word in _BLOCKED_SCRIPT_WORDS):
                    raise DynamicTestError(f"Test case {case_index}: blocked potentially dangerous script selection '{scripts}'.")

    def _display_plan(self, tool_name: str, prepared: list[dict[str, Any]]) -> None:
        print("\n" + "=" * 76)
        print(f"DYNAMIC TEST PLAN: {tool_name}")
        if self.integration_bridge is not None:
            print("Execution backend: running DDT application via CommandHelper / Tauri Shell.")
        else:
            print("Execution backend: direct local CLI subprocess (not DDT integration).")
        print("Check targets and arguments before approving.")
        print("=" * 76)
        for index, case in enumerate(prepared, start=1):
            print(f"\n[{index}] {case['name']}")
            if case["purpose"]:
                print(f"    Purpose: {case['purpose']}")
            print(f"    Command: {shlex.join([case['command'], *case['args']])}")
            print(f"    Targets: {', '.join(case['targets']) if case['targets'] else '(none detected)'}")
            print(f"    Timeout: {case['timeout_seconds']} seconds")
            print(f"    Expected exit codes: {case['expected_exit_codes']}")
            print(f"    Output contains: {case['expected_contains']}")
        print("\n" + "=" * 76)

    def _runtime_cwd(self) -> str:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        return str(self.runtime_dir)

    @staticmethod
    def _minimal_env() -> dict[str, str]:
        allowed = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "WINDIR")
        env = {key: os.environ[key] for key in allowed if key in os.environ}
        env.setdefault("LC_ALL", "C")
        return env

    def _append_report(self, payload: dict[str, Any]) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        with self.report_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
