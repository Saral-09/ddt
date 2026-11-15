from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .foundry_agent import DDTFoundryQAAgent
from .repo_inspector import DDTRepository, RepositoryError


def _default_repo() -> Path:
    # Installed at <ddt-root>/qa-agent/ddt_qa_agent/cli.py
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ddt-qa-agent",
        description="Microsoft Foundry-powered QA agent for the Deakin Detonator Toolkit.",
    )
    parser.add_argument("--repo", type=Path, default=_default_repo(), help="Path to DDT repository root (default: detected from this folder)")
    parser.add_argument("--task", type=str, help="QA task for the agent. If omitted, an interactive prompt is shown.")
    parser.add_argument("--enable-dynamic-testing", action="store_true", help="Allow AI-generated ephemeral test batches; each batch is shown and requires interactive operator approval")
    parser.add_argument("--max-tool-rounds", type=int, default=12, help="Maximum Foundry tool-calling rounds (default: 12)")
    args = parser.parse_args()

    qa_dir = Path(__file__).resolve().parents[1]
    load_dotenv(qa_dir / ".env")

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    deployment = os.getenv("FOUNDRY_MODEL_DEPLOYMENT", "").strip()
    if not endpoint or not deployment:
        print("Missing Foundry configuration. Copy .env.example to .env and set:")
        print("  FOUNDRY_PROJECT_ENDPOINT")
        print("  FOUNDRY_MODEL_DEPLOYMENT (your GPT-5.6 Terra deployment name)")
        return 2

    task = args.task
    if not task:
        print("\nDDT Foundry QA Agent")
        print("Dynamic testing:", "ENABLED (each batch requires terminal approval)" if args.enable_dynamic_testing else "DISABLED")
        print("Enter your QA task. Submit an empty line to cancel.\n")
        task = input("QA task > ").strip()
    if not task:
        print("No task provided.")
        return 2

    try:
        repo = DDTRepository(args.repo)
        print(f"DDT repository: {repo.root_path}")
        print(f"Discovered {repo.list_tools()['count']} tool routes")
        print(f"Foundry model deployment: {deployment}")
        print("Dynamic testing:", "enabled (operator approval per batch)" if args.enable_dynamic_testing else "disabled")
        print("Connecting to Microsoft Foundry using DefaultAzureCredential...\n")

        agent = DDTFoundryQAAgent(
            repo=repo,
            model_deployment=deployment,
            project_endpoint=endpoint,
            dynamic_testing_enabled=args.enable_dynamic_testing,
        )
        try:
            report = agent.run(task, max_tool_rounds=max(1, min(args.max_tool_rounds, 20)))
        finally:
            agent.close()

        print("\n" + "=" * 76)
        print("DDT QA AGENT RESULT")
        print("=" * 76)
        print(report["final_response"] or "No final text returned by the model.")
        print("\nFunction calls:", len(report["tool_calls"]))
        print("Report:", report["report_file"])
        print("=" * 76)
        return 0
    except RepositoryError as exc:
        print(f"Repository error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"QA agent failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
