# engine/cli/display.py
"""Pretty-print helpers for CLI output."""

import json

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()

_PHASE_DOTS = {
    1: "[dim]●○○○○[/dim] Nascent",
    2: "[yellow]●●○○○[/yellow] Forming",
    3: "[green]●●●○○[/green] Reliable",
    4: "[blue]●●●●○[/blue] Expert",
    5: "[magenta]●●●●●[/magenta] Authoritative",
}


def print_task_result(result: dict) -> None:
    console.print(
        Panel(
            result.get("output", "(no output)"),
            title=f"[bold]{result.get('domain_path', 'unknown')}[/bold]",
            subtitle=f"intel loaded: {result.get('intelligence_loaded', {}).get('total_count', 0)} insights",
        )
    )


def print_deliberation_receipt(result: dict) -> None:
    """Print the bounded I2 receipt without exposing private task inputs."""
    receipt = result.get("deliberation_receipt")
    if not isinstance(receipt, dict):
        console.print("[yellow]No deliberation receipt is available from this server.[/yellow]")
        return
    console.print(
        Panel(
            Syntax(json.dumps(receipt, indent=2, sort_keys=True), "json", word_wrap=True),
            title="[bold]Attributable deliberation[/bold]",
        )
    )


def print_intelligence(snapshot: dict) -> None:
    table = Table(title=f"Intelligence: {snapshot.get('domain_path', '')}")
    table.add_column("Type", style="cyan")
    table.add_column("Content")
    table.add_column("Confidence", justify="right")
    table.add_column("Tier")

    for i in snapshot.get("insights", []):
        table.add_row(
            i.get("insight_type", ""),
            i.get("content", "")[:80],
            f"{i.get('confidence', 0):.2f}",
            i.get("tier", ""),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {snapshot.get('total_count', 0)} insights[/dim]")


def print_phase(phase: int) -> None:
    console.print(_PHASE_DOTS.get(phase, f"Phase {phase}"))
