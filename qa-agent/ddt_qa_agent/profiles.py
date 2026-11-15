from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .repo_inspector import DDTRepository, RepositoryError


class ProfileError(RuntimeError):
    pass


_SAFE_COMMAND = re.compile(r"^[A-Za-z0-9_.+-]+$")


def _target_host(value: str) -> str:
    """Return host from a URL or bare host/IP so local URLs can be allowlisted by host."""
    raw = value.strip()
    if not raw:
        return raw
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    return (parsed.hostname or raw).lower().rstrip(".")


class ApprovedProfileRunner:
    """Runs only fixed, human-approved JSON profiles; never executes model-supplied shell."""

    def __init__(self, repo: DDTRepository, profile_file: str | Path, execution_enabled: bool = False):
        self.repo = repo
        self.execution_enabled = execution_enabled
        self.profile_file = Path(profile_file).resolve()
        self.allowed_targets = {
            item.strip()
            for item in os.getenv("DDT_QA_ALLOWED_TARGETS", "127.0.0.1,localhost,::1").split(",")
            if item.strip()
        }

    def _load_profiles(self) -> list[dict[str, Any]]:
        if not self.profile_file.exists():
            return []
        data = json.loads(self.profile_file.read_text(encoding="utf-8"))
        profiles = data.get("profiles", [])
        if not isinstance(profiles, list):
            raise ProfileError("Profile file must contain a 'profiles' array")
        return profiles

    def list_profiles(self, tool_id: str = "") -> dict[str, Any]:
        profiles = self._load_profiles()
        if tool_id:
            normalized = self.repo.find_tool(tool_id).id
            profiles = [p for p in profiles if p.get("tool_id") == normalized]
        return {
            "count": len(profiles),
            "profiles": [
                {
                    "profile_id": p.get("profile_id"),
                    "tool_id": p.get("tool_id"),
                    "description": p.get("description"),
                    "approved": bool(p.get("approved", False)),
                    "target_scope": p.get("allowed_targets", []),
                }
                for p in profiles
            ],
        }


    def propose(self, proposal: dict[str, Any]) -> dict[str, Any]:
        """Persist an unapproved profile suggestion; proposals are never executable."""
        tool = self.repo.find_tool(str(proposal.get("tool_id", "")))
        profile_id = str(proposal.get("profile_id", "")).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", profile_id):
            raise ProfileError("profile_id must be a lowercase slug (2-64 characters)")
        command = str(proposal.get("command", ""))
        if not _SAFE_COMMAND.fullmatch(command):
            raise ProfileError("Proposed command contains unsupported characters")
        dependencies = self.repo.inspect_tool(tool.id)["dependencies"]
        if command not in dependencies:
            raise ProfileError(f"Command '{command}' is not declared in {tool.name}'s dependencies: {dependencies}")

        args = proposal.get("args")
        if not isinstance(args, list) or not args or len(args) > 64 or not all(isinstance(arg, str) and len(arg) <= 512 for arg in args):
            raise ProfileError("args must be a non-empty array of at most 64 strings (512 characters each)")
        target_indexes = proposal.get("target_arg_indexes", [])
        allowed_targets = proposal.get("allowed_targets", [])
        if not isinstance(target_indexes, list) or not all(isinstance(i, int) for i in target_indexes):
            raise ProfileError("target_arg_indexes must be an array of integer indexes")
        if not isinstance(allowed_targets, list) or not all(isinstance(x, str) for x in allowed_targets):
            raise ProfileError("allowed_targets must be an array of strings")
        proposed_allowlist = set(allowed_targets)
        if not proposed_allowlist.issubset(self.allowed_targets):
            raise ProfileError("Proposed allowed_targets must be explicitly configured in DDT_QA_ALLOWED_TARGETS")
        effective_allowlist = self.allowed_targets
        for index in target_indexes:
            if index < 0 or index >= len(args):
                raise ProfileError("target_arg_indexes contains an invalid argument index")
            host = _target_host(args[index])
            if host not in {_target_host(item) for item in effective_allowlist}:
                raise ProfileError(f"Proposed target '{args[index]}' (host '{host}') is not allowlisted. Only local/explicitly allowlisted lab targets can be proposed.")

        timeout = int(proposal.get("timeout_seconds", 20))
        if not 1 <= timeout <= 120:
            raise ProfileError("timeout_seconds must be between 1 and 120")
        expected_contains = proposal.get("expected_contains", [])
        expected_not_contains = proposal.get("expected_not_contains", [])
        if not isinstance(expected_contains, list) or not all(isinstance(x, str) for x in expected_contains):
            raise ProfileError("expected_contains must be an array of strings")
        if not isinstance(expected_not_contains, list) or not all(isinstance(x, str) for x in expected_not_contains):
            raise ProfileError("expected_not_contains must be an array of strings")

        profile = {
            "profile_id": profile_id,
            "tool_id": tool.id,
            "description": str(proposal.get("description", ""))[:1000],
            "proposal_status": "requires_human_review",
            "approved": False,
            "command": command,
            "args": args,
            "target_arg_indexes": target_indexes,
            "allowed_targets": sorted(set(allowed_targets)),
            "timeout_seconds": timeout,
            "expected_exit_code": int(proposal.get("expected_exit_code", 0)),
            "expected_contains": expected_contains,
            "expected_not_contains": expected_not_contains,
        }
        proposal_dir = self.profile_file.parent / "proposals"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = proposal_dir / f"{tool.id}-{profile_id}.json"
        if proposal_path.exists():
            raise ProfileError(f"Proposal already exists: {proposal_path.name}")
        proposal_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "saved": True,
            "approved": False,
            "status": "requires_human_review",
            "proposal_file": str(proposal_path),
            "profile": profile,
            "message": "This profile cannot run until a human reviews and explicitly approves it.",
        }

    def run(self, tool_id: str, profile_id: str) -> dict[str, Any]:
        if not self.execution_enabled:
            return {"status": "blocked", "reason": "Execution is disabled. Restart the QA agent with --enable-approved-execution to run pre-approved profiles."}
        tool = self.repo.find_tool(tool_id)
        profiles = self._load_profiles()
        profile = next((p for p in profiles if p.get("profile_id") == profile_id), None)
        if profile is None:
            raise ProfileError(f"No approved profile named '{profile_id}' exists")
        if profile.get("tool_id") != tool.id:
            raise ProfileError("Profile tool_id does not match the requested DDT tool")
        if profile.get("approved") is not True:
            raise ProfileError("Profile is not approved. Review and approve it in profiles/approved_profiles.json")

        command = str(profile.get("command", ""))
        if not _SAFE_COMMAND.fullmatch(command):
            raise ProfileError("Profile command contains unsupported characters")
        dependencies = self.repo.inspect_tool(tool.id)["dependencies"]
        if command not in dependencies:
            raise ProfileError(f"Command '{command}' is not declared by {tool.name}'s component dependencies: {dependencies}")

        executable = __import__("shutil").which(command)
        if not executable:
            return {"status": "blocked", "reason": f"Executable '{command}' is not installed"}

        args = profile.get("args")
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ProfileError("Profile args must be an array of strings")

        target_indexes = profile.get("target_arg_indexes", [])
        if not isinstance(target_indexes, list):
            raise ProfileError("target_arg_indexes must be an array")
        profile_targets = set(profile.get("allowed_targets", []))
        if not profile_targets.issubset(self.allowed_targets):
            raise ProfileError("Profile target allowlist contains targets not explicitly allowed by DDT_QA_ALLOWED_TARGETS")
        effective_allowlist = self.allowed_targets
        for raw_index in target_indexes:
            if not isinstance(raw_index, int) or raw_index < 0 or raw_index >= len(args):
                raise ProfileError("Invalid target_arg_indexes entry")
            target = args[raw_index]
            host = _target_host(target)
            if host not in {_target_host(item) for item in effective_allowlist}:
                raise ProfileError(
                    f"Blocked target '{target}' (host '{host}'). Add its host to DDT_QA_ALLOWED_TARGETS only when you own or have permission to test it."
                )

        timeout = int(profile.get("timeout_seconds", 20))
        timeout = max(1, min(timeout, 120))
        expected = profile.get("expected_contains", [])
        unexpected = profile.get("expected_not_contains", [])
        if not all(isinstance(x, str) for x in expected + unexpected):
            raise ProfileError("Expected output checks must be arrays of strings")

        started = datetime.now(timezone.utc).isoformat()
        try:
            completed = subprocess.run(
                [executable, *args],
                cwd=self.repo.root_path,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
                env={**os.environ, "LC_ALL": "C"},
            )
            output = (completed.stdout or "") + "\n" + (completed.stderr or "")
            checks = [{"assertion": f"contains: {s}", "passed": s in output} for s in expected]
            checks.extend({"assertion": f"does not contain: {s}", "passed": s not in output} for s in unexpected)
            passed = completed.returncode == int(profile.get("expected_exit_code", 0)) and all(c["passed"] for c in checks)
            result = {
                "status": "passed" if passed else "failed",
                "tool_id": tool.id,
                "profile_id": profile_id,
                "command": command,
                "args": args,
                "exit_code": completed.returncode,
                "checks": checks,
                "output": output[-8000:],
                "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            result = {
                "status": "timeout",
                "tool_id": tool.id,
                "profile_id": profile_id,
                "command": command,
                "args": args,
                "timeout_seconds": timeout,
                "output": (stdout + "\n" + stderr)[-8000:],
                "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }

        report_dir = self.repo.root_path / "qa-agent" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "executions.jsonl"
        with report_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        result["report_file"] = str(report_file.relative_to(self.repo.root_path))
        return result


class FindingStore:
    def __init__(self, repo: DDTRepository):
        self.path = repo.root_path / "qa-agent" / "reports" / "findings.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        tool_id: str,
        classification: str,
        severity: str,
        title: str,
        evidence: str,
        impact: str,
        reproduction: str,
        confidence: float,
    ) -> dict[str, Any]:
        if classification not in {"potential_bug", "confirmed_failure", "test_gap", "dependency_issue", "observation"}:
            raise ValueError("Unsupported finding classification")
        if severity not in {"critical", "high", "medium", "low", "info"}:
            raise ValueError("Unsupported severity")
        if not title.strip() or not evidence.strip():
            raise ValueError("Finding title and evidence are required")
        record = {
            "id": f"QA-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tool_id": tool_id,
            "classification": classification,
            "severity": severity,
            "title": title[:200],
            "evidence": evidence[:5000],
            "impact": impact[:2000],
            "reproduction": reproduction[:2000],
            "confidence": max(0.0, min(float(confidence), 1.0)),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"saved": True, "finding": record, "file": str(self.path)}
