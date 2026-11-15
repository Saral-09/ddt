from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown

from .foundry_agent import DDTFoundryQAAgent
from .integration_bridge import DDTBridgeError, DDTIntegrationBridge
from .repo_inspector import DDTRepository, RepositoryError


console = Console()


def _default_repo() -> Path:
    # Installed at <ddt-root>/qa-agent/ddt_qa_agent/cli.py
    return Path(__file__).resolve().parents[2]


def _print_markdown(content: str | None) -> None:
    """Render the model's Markdown response in the terminal."""
    content = (content or "").strip()
    if not content:
        console.print("[dim]No final text returned by the model.[/dim]")
        return
    console.print(Markdown(content))


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ddt-qa-agent",
        description="Microsoft Foundry-powered QA agent for the Deakin Detonator Toolkit.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=_default_repo(),
        help="Path to DDT repository root (default: detected from this folder)",
    )
    parser.add_argument("--task", type=str, help="QA task for the agent. If omitted, an interactive prompt is shown.")
    parser.add_argument(
        "--enable-dynamic-testing",
        action="store_true",
        help="Allow AI-generated ephemeral test batches; each batch requires terminal approval",
    )
    parser.add_argument(
        "--enable-ddt-integration",
        action="store_true",
        help="Execute approved tests through the running DDT app's CommandHelper/Tauri Shell instead of Python subprocess",
    )
    parser.add_argument(
        "--ddt-bridge-port",
        type=int,
        default=int(os.getenv("DDT_QA_BRIDGE_PORT", "8765")),
        help="Loopback WebSocket port for the DDT frontend bridge (default: 8765)",
    )
    parser.add_argument(
        "--ddt-bridge-wait",
        type=int,
        default=180,
        help="Seconds to wait for the running DDT app to connect (default: 180)",
    )
    parser.add_argument("--max-tool-rounds", type=int, default=12, help="Maximum Foundry tool-calling rounds (default: 12)")
    args = parser.parse_args()

    qa_dir = Path(__file__).resolve().parents[1]
    load_dotenv(qa_dir / ".env")

    if args.enable_ddt_integration and not args.enable_dynamic_testing:
        console.print("[bold red]DDT integration requires --enable-dynamic-testing.[/bold red]")
        return 2
    if args.ddt_bridge_wait < 1 or args.ddt_bridge_wait > 900:
        console.print("[bold red]--ddt-bridge-wait must be between 1 and 900 seconds.[/bold red]")
        return 2

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    deployment = os.getenv("FOUNDRY_MODEL_DEPLOYMENT", "").strip()
    if not endpoint or not deployment:
        console.print("[bold red]Missing Foundry configuration.[/bold red] Copy .env.example to .env and set:")
        console.print("  FOUNDRY_PROJECT_ENDPOINT")
        console.print("  FOUNDRY_MODEL_DEPLOYMENT")
        return 2

    task = args.task
    if not task:
        console.print("\n[bold cyan]DDT Foundry QA Agent[/bold cyan]")
        console.print(
            "Dynamic testing: "
            + ("[green]ENABLED (terminal approval per batch)[/green]" if args.enable_dynamic_testing else "[yellow]DISABLED[/yellow]")
        )
        console.print(
            "DDT integration: "
            + ("[green]ENABLED (production CommandHelper)[/green]" if args.enable_ddt_integration else "[yellow]DISABLED[/yellow]")
        )
        task = console.input("[bold]QA task > [/bold]").strip()
    if not task:
        console.print("[yellow]No task provided.[/yellow]")
        return 2

    integration_bridge: DDTIntegrationBridge | None = None
    agent: DDTFoundryQAAgent | None = None
    try:
        repo = DDTRepository(args.repo)
        console.print(f"DDT repository: {repo.root_path}")
        console.print(f"Discovered {repo.list_tools()['count']} tool routes")
        console.print(f"Foundry model deployment: {deployment}")
        console.print(
            "Dynamic testing: "
            + ("[green]enabled (operator approval per batch)[/green]" if args.enable_dynamic_testing else "[yellow]disabled[/yellow]")
        )

        if args.enable_ddt_integration:
            integration_bridge = DDTIntegrationBridge(host="127.0.0.1", port=args.ddt_bridge_port)
            integration_bridge.start()
            console.print("\n[bold cyan]DDT integration bridge is listening.[/bold cyan]")
            console.print("Start DDT in development mode if it is not already running.")
            console.print("In the DDT QA Bridge panel, paste this one-time token:")
            console.print(f"[bold yellow]{integration_bridge.token}[/bold yellow]")
            console.print(f"Bridge address: ws://127.0.0.1:{args.ddt_bridge_port}")
            console.print(f"Waiting up to {args.ddt_bridge_wait} seconds for DDT to connect...\n")
            if not integration_bridge.wait_for_client(args.ddt_bridge_wait):
                raise DDTBridgeError("DDT did not connect before the wait period expired. No tests were executed.")
            console.print("[bold green]DDT application connected. Integration execution is ready.[/bold green]\n")

        console.print("Connecting to Microsoft Foundry using DefaultAzureCredential...\n")
        agent = DDTFoundryQAAgent(
            repo=repo,
            model_deployment=deployment,
            project_endpoint=endpoint,
            dynamic_testing_enabled=args.enable_dynamic_testing,
            integration_bridge=integration_bridge,
        )
        report = agent.run(task, max_tool_rounds=max(1, min(args.max_tool_rounds, 20)))

        console.print("\n" + "=" * 76)
        console.print("[bold cyan]DDT QA AGENT RESULT[/bold cyan]")
        console.print("=" * 76)
        _print_markdown(report.get("final_response"))
        console.print("\n[bold]Function calls:[/bold] " + str(len(report["tool_calls"])))
        console.print("[bold]Report:[/bold] " + str(report["report_file"]))
        console.print("=" * 76)
        return 0
    except RepositoryError as exc:
        console.print(f"[bold red]Repository error:[/bold red] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        console.print(f"[bold red]QA agent failed:[/bold red] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            if agent is not None:
                agent.close()
        finally:
            if integration_bridge is not None:
                integration_bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
