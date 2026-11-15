from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential

from .profiles import ApprovedProfileRunner, FindingStore, ProfileError
from .dynamic_testing import DynamicTestRunner, DynamicTestError
from .repo_inspector import DDTRepository, RepositoryError


# These schemas are registered on the saved Foundry Prompt Agent once.
# They are NOT sent with every Responses API request.

def _object_schema(
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_tools",
        "description": "List tools registered under DDT's /tools routes. Supports optional text and category filters.",
        "parameters": _object_schema(
            {
                "query": {"type": "string", "description": "Optional name, ID, or description filter; use an empty string for all tools."},
                "category": {"type": "string", "description": "Optional category filter; use an empty string for all categories."},
            },
            ["query", "category"],
        ),
    },
    {
        "name": "inspect_tool",
        "description": "Inspect one DDT tool's registered route, React component source, declared dependencies, and command-construction code evidence.",
        "parameters": _object_schema(
            {"tool_id": {"type": "string", "description": "Tool ID or displayed name from list_tools."}},
            ["tool_id"],
        ),
    },
    {
        "name": "inspect_related_tests",
        "description": "Find and read existing Vitest/Jest test files whose names reference a selected DDT tool. Use only when the user asks to diagnose tests.",
        "parameters": _object_schema(
            {"tool_id": {"type": "string", "description": "Tool ID or displayed name."}},
            ["tool_id"],
        ),
    },
    {
        "name": "inspect_execution_helper",
        "description": "Inspect DDT's shared src/utils/CommandHelper.ts implementation, including execution, output and cancellation behaviour.",
        "parameters": _object_schema({}, []),
    },
    {
        "name": "check_tool_dependencies",
        "description": "Check whether the executable dependencies declared by a selected tool component are available on this machine. This only uses PATH lookup; it does not execute the tool.",
        "parameters": _object_schema(
            {"tool_id": {"type": "string", "description": "Tool ID or displayed name."}},
            ["tool_id"],
        ),
    },
    {
        "name": "probe_tool_cli",
        "description": "Run only fixed harmless CLI discovery probes (--help, -h, --version, -V) for executable dependencies declared by the selected DDT component. It does not scan a target or accept model-provided arguments.",
        "parameters": _object_schema(
            {"tool_id": {"type": "string"}},
            ["tool_id"],
        ),
    },
    {
        "name": "run_dynamic_test_plan",
        "description": "Run an ephemeral AI-generated test batch through the guarded local runner. The runner validates executables, restricts detected targets to DDT_QA_ALLOWED_TARGETS, blocks selected high-risk options, displays every command and requires the operator to type RUN DDT QA PLAN. Maximum five cases.",
        "parameters": _object_schema(
            {
                "tool_id": {"type": "string"},
                "description": {"type": "string"},
                "tests": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": _object_schema(
                        {
                            "name": {"type": "string"},
                            "purpose": {"type": "string"},
                            "command": {"type": "string"},
                            "args": {"type": "array", "items": {"type": "string"}, "maxItems": 40},
                            "target_arg_indexes": {"type": "array", "items": {"type": "integer"}},
                            "timeout_seconds": {"type": "integer"},
                            "expected_exit_codes": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                            "expected_contains": {"type": "array", "items": {"type": "string"}},
                            "expected_not_contains": {"type": "array", "items": {"type": "string"}},
                        },
                        [
                            "name",
                            "purpose",
                            "command",
                            "args",
                            "target_arg_indexes",
                            "timeout_seconds",
                            "expected_exit_codes",
                            "expected_contains",
                            "expected_not_contains",
                        ],
                    ),
                },
            },
            ["tool_id", "description", "tests"],
        ),
    },
    {
        "name": "list_approved_profiles",
        "description": "List human-reviewed, pre-approved execution profiles. Profiles are fixed argument arrays; the model cannot edit them.",
        "parameters": _object_schema(
            {"tool_id": {"type": "string", "description": "Tool ID filter; use an empty string for all tools."}},
            ["tool_id"],
        ),
    },
    {
        "name": "propose_test_profile",
        "description": "Create an unapproved JSON test-profile proposal for a DDT tool. This never executes the command. The proposal is saved for human review; commands must match the tool's declared dependencies and targets must be allowlisted.",
        "parameters": _object_schema(
            {
                "tool_id": {"type": "string"},
                "profile_id": {"type": "string", "description": "Unique lowercase slug, e.g. arjun-local-help-check."},
                "description": {"type": "string"},
                "command": {"type": "string", "description": "Must exactly match one of the tool component's declared dependencies."},
                "args": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 64},
                "target_arg_indexes": {"type": "array", "items": {"type": "integer"}},
                "allowed_targets": {"type": "array", "items": {"type": "string"}, "description": "Hostnames or IPs (not full URLs) that must already be present in DDT_QA_ALLOWED_TARGETS."},
                "timeout_seconds": {"type": "integer"},
                "expected_exit_code": {"type": "integer"},
                "expected_contains": {"type": "array", "items": {"type": "string"}},
                "expected_not_contains": {"type": "array", "items": {"type": "string"}},
            },
            [
                "tool_id",
                "profile_id",
                "description",
                "command",
                "args",
                "target_arg_indexes",
                "allowed_targets",
                "timeout_seconds",
                "expected_exit_code",
                "expected_contains",
                "expected_not_contains",
            ],
        ),
    },
    {
        "name": "run_approved_profile",
        "description": "Execute one exact, human-approved profile from qa-agent/profiles/approved_profiles.json. This is disabled unless the operator started the CLI with --enable-approved-execution. Never supply arbitrary commands or arguments.",
        "parameters": _object_schema(
            {
                "tool_id": {"type": "string", "description": "Tool ID the profile belongs to."},
                "profile_id": {"type": "string", "description": "Exact profile_id returned by list_approved_profiles."},
            },
            ["tool_id", "profile_id"],
        ),
    },
    {
        "name": "save_finding",
        "description": "Save an evidence-backed QA finding to qa-agent/reports/findings.jsonl. A failing test alone is not enough to label a product defect as confirmed.",
        "parameters": _object_schema(
            {
                "tool_id": {"type": "string"},
                "classification": {"type": "string", "enum": ["potential_bug", "confirmed_failure", "test_gap", "dependency_issue", "observation"]},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                "title": {"type": "string"},
                "evidence": {"type": "string", "description": "Exact source/test/output evidence, preferably with file and line references."},
                "impact": {"type": "string"},
                "reproduction": {"type": "string"},
                "confidence": {"type": "number", "description": "Confidence from 0.0 to 1.0."},
            },
            ["tool_id", "classification", "severity", "title", "evidence", "impact", "reproduction", "confidence"],
        ),
    },
]


class DDTFoundryQAAgent:
    """Local DDT QA tool executor connected to a saved Microsoft Foundry Prompt Agent.

    The saved Foundry agent owns the model, permanent instructions, and function schemas.
    This process owns the actual local Python function implementations and safety checks.
    """

    def __init__(
        self,
        repo: DDTRepository,
        model_deployment: str,
        project_endpoint: str,
        execution_enabled: bool = False,
        dynamic_testing_enabled: bool = False,
        integration_bridge: Any | None = None,
    ):
        self.repo = repo
        self.model_deployment = model_deployment  # Kept for compatibility with the CLI constructor.
        self.project_endpoint = project_endpoint
        self.agent_name = os.getenv("FOUNDRY_AGENT_NAME", "").strip()
        if not self.agent_name:
            raise ValueError(
                "FOUNDRY_AGENT_NAME is missing. Add the exact saved Foundry Prompt Agent name to qa-agent/.env."
            )

        self.credential = DefaultAzureCredential()
        self.project = AIProjectClient(endpoint=project_endpoint, credential=self.credential)

        # Ensure the saved agent has the local function schemas. This creates a new agent
        # version only if one or more DDT function tools are missing. It reuses the model
        # and instructions already stored on the existing Foundry agent.
        self.agent_version = self._ensure_function_tools_registered()

        # A client pre-bound to the saved agent. The agent's instructions, model and tools
        # are resolved by Foundry; they are not repeated in each Responses API request.
        self.openai = self.project.get_openai_client(agent_name=self.agent_name)

        profile_path = repo.root_path / "qa-agent" / "profiles" / "approved_profiles.json"
        self.runner = ApprovedProfileRunner(repo, profile_path, execution_enabled=execution_enabled)
        self.integration_bridge = integration_bridge
        self.dynamic_runner = DynamicTestRunner(
            repo,
            enabled=dynamic_testing_enabled,
            integration_bridge=integration_bridge,
        )
        self.findings = FindingStore(repo)

        self.execution_enabled = execution_enabled
        self.dynamic_testing_enabled = dynamic_testing_enabled

        self._tool_handlers = {
            "list_tools": self._list_tools,
            "inspect_tool": self._inspect_tool,
            "inspect_related_tests": self._inspect_related_tests,
            "inspect_execution_helper": self._inspect_execution_helper,
            "check_tool_dependencies": self._check_tool_dependencies,
            "probe_tool_cli": self._probe_tool_cli,
            "run_dynamic_test_plan": self._run_dynamic_test_plan,
            "list_approved_profiles": self._list_approved_profiles,
            "propose_test_profile": self._propose_test_profile,
            "run_approved_profile": self._run_approved_profile,
            "save_finding": self._save_finding,
        }

    @staticmethod
    def _field(value: Any, name: str, default: Any = None) -> Any:
        """Read a field from an Azure SDK model or a plain dictionary."""
        if isinstance(value, dict):
            return value.get(name, default)
        getter = getattr(value, "get", None)
        if callable(getter):
            try:
                result = getter(name, default)
                if result is not None:
                    return result
            except TypeError:
                pass
        return getattr(value, name, default)

    def _ensure_function_tools_registered(self) -> str:
        versions = self.project.agents.list_versions(
            agent_name=self.agent_name,
            limit=1,
            order="desc",
        )
        current = next(iter(versions), None)
        if current is None:
            raise RuntimeError(
                f"Foundry agent '{self.agent_name}' has no active version. Create its Prompt Agent first."
            )

        current_version = str(self._field(current, "version", ""))
        current_definition = self._field(current, "definition")
        if current_definition is None:
            raise RuntimeError("Could not read the saved Foundry agent definition.")

        model = self._field(current_definition, "model")
        instructions = self._field(current_definition, "instructions")
        if not model or not instructions:
            raise RuntimeError(
                "The saved Foundry agent must be a Prompt Agent with a model and instructions. "
                "No local fallback instructions will be injected."
            )

        existing_tools = list(self._field(current_definition, "tools", []) or [])
        existing_names = {
            self._field(tool, "name")
            for tool in existing_tools
            if self._field(tool, "name")
        }

        missing = [spec for spec in TOOL_DEFINITIONS if spec["name"] not in existing_names]
        if not missing:
            print(
                f"Foundry agent '{self.agent_name}' is ready (version {current_version}); "
                f"all {len(TOOL_DEFINITIONS)} DDT function tools are registered."
            )
            return current_version

        function_tools = [
            FunctionTool(
                name=spec["name"],
                description=spec["description"],
                parameters=spec["parameters"],
                strict=True,
            )
            for spec in missing
        ]

        # Preserve existing tools and the exact model/instructions already saved in Foundry.
        updated_definition = PromptAgentDefinition(
            model=model,
            instructions=instructions,
            tools=existing_tools + function_tools,
        )
        updated = self.project.agents.create_version(
            agent_name=self.agent_name,
            definition=updated_definition,
            description="Register DDT local QA function tools; preserve saved agent instructions.",
        )
        new_version = str(self._field(updated, "version", current_version))
        print(
            f"Registered {len(missing)} DDT function tool(s) on Foundry agent "
            f"'{self.agent_name}'. New version: {new_version}."
        )
        return new_version

    def _list_tools(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.repo.list_tools(args["query"], args["category"])

    def _inspect_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.repo.inspect_tool(args["tool_id"])

    def _inspect_related_tests(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.repo.inspect_related_tests(args["tool_id"])

    def _inspect_execution_helper(self, _args: dict[str, Any]) -> dict[str, Any]:
        return self.repo.inspect_execution_helper()

    def _check_tool_dependencies(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.repo.check_dependencies(args["tool_id"])

    def _probe_tool_cli(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.dynamic_runner.probe_cli(args["tool_id"])

    def _run_dynamic_test_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.dynamic_runner.run_plan(args)

    def _list_approved_profiles(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.runner.list_profiles(args["tool_id"])

    def _propose_test_profile(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.runner.propose(args)

    def _run_approved_profile(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.runner.run(args["tool_id"], args["profile_id"])

    def _save_finding(self, args: dict[str, Any]) -> dict[str, Any]:
        tool = self.repo.find_tool(args["tool_id"])
        normalized = dict(args)
        normalized["tool_id"] = tool.id
        return self.findings.save(**normalized)

    def _dispatch(self, name: str, raw_arguments: str) -> dict[str, Any]:
        handler = self._tool_handlers.get(name)
        if handler is None:
            return {"status": "error", "error": f"Unknown function: {name}"}

        try:
            args = json.loads(raw_arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError("Function arguments must be a JSON object")
            return handler(args)
        except (RepositoryError, ProfileError, DynamicTestError, ValueError, KeyError) as exc:
            return {"status": "blocked_or_error", "error": str(exc)}
        except Exception as exc:
            # Keep local tool errors visible to the model without terminating the run.
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _function_calls(response: Any) -> list[Any]:
        return [
            item
            for item in (getattr(response, "output", None) or [])
            if getattr(item, "type", None) == "function_call"
        ]

    def run(self, task: str, max_tool_rounds: int = 12) -> dict[str, Any]:
        if not task or not task.strip():
            raise ValueError("Task must not be empty")
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be at least 1")

        report_dir = self.repo.root_path / "qa-agent" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        calls_log: list[dict[str, Any]] = []

        # The saved Foundry agent supplies its model, instructions and registered tools.
        response = self.openai.responses.create(input=task)

        rounds = 0
        while rounds < max_tool_rounds:
            calls = self._function_calls(response)
            if not calls:
                break

            rounds += 1
            outputs: list[dict[str, str]] = []

            for call in calls:
                try:
                    parsed_arguments = json.loads(call.arguments or "{}")
                except json.JSONDecodeError:
                    parsed_arguments = {"_invalid_json": call.arguments}

                result = self._dispatch(call.name, call.arguments)
                calls_log.append(
                    {
                        "round": rounds,
                        "function": call.name,
                        "arguments": parsed_arguments,
                        "result": result,
                    }
                )
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            if not outputs:
                break

            # Continue the same response chain. The pre-bound client keeps using the saved agent.
            response = self.openai.responses.create(
                input=outputs,
                previous_response_id=response.id,
            )

        final_text = (getattr(response, "output_text", "") or "").strip()
        pending_calls = self._function_calls(response)
        report = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "foundry_agent_name": self.agent_name,
            "foundry_agent_version": self.agent_version,
            "model_deployment": self.model_deployment,
            "repository": str(self.repo.root_path),
            "execution_enabled": self.execution_enabled,
            "dynamic_testing_enabled": self.dynamic_testing_enabled,
            "ddt_integration_enabled": self.integration_bridge is not None,
            "task": task,
            "tool_rounds": rounds,
            "tool_calls": calls_log,
            "final_response": final_text,
            "max_rounds_reached": bool(pending_calls) and rounds >= max_tool_rounds,
        }
        report_path = report_dir / f"foundry-qa-{run_id}.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        report["report_file"] = str(report_path.relative_to(self.repo.root_path))
        return report

    def close(self) -> None:
        try:
            self.openai.close()
        finally:
            try:
                self.project.close()
            finally:
                self.credential.close()
