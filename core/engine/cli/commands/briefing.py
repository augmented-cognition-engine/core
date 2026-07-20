# engine/cli/commands/briefing.py
"""ace briefing — display intelligence briefings from the terminal."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.group(invoke_without_command=True)
@click.option("--org", "-o", default="product:default")
@click.pass_context
def briefing(ctx, org):
    """Show the latest intelligence briefing."""
    if ctx.invoked_subcommand is None:
        url = ctx.obj["url"]
        headers = get_headers()

        resp = httpx.get(
            f"{url}/briefings/latest",
            params={"product": org},
            headers=headers,
            timeout=30,
        )

        if resp.status_code == 404:
            console.print("\n[dim]No briefings yet. Run the briefing generator first:[/dim]")
            console.print("  ace sentinel trigger briefing_generator\n")
            return

        if resp.status_code != 200:
            console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
            return

        data = resp.json()
        content = data.get("content", "")
        created_at = data.get("created_at", "")

        console.print(f"\n{content}")
        console.print(f"\n[dim]Generated: {created_at}[/dim]\n")


@briefing.command("list")
@click.option("--org", "-o", default="product:default")
@click.option("--limit", "-l", default=10, type=int)
@click.pass_context
def list_briefings(ctx, org, limit):
    """List recent briefings."""
    url = ctx.obj["url"]
    headers = get_headers()

    resp = httpx.get(
        f"{url}/briefings",
        params={"product": org, "limit": limit},
        headers=headers,
        timeout=30,
    )

    if resp.status_code != 200:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        return

    data = resp.json()
    briefings = data.get("briefings", [])

    if not briefings:
        console.print("\n[dim]No briefings found.[/dim]\n")
        return

    console.print(f"\n[bold]Intelligence Briefings[/bold] ({len(briefings)} total)\n")
    console.print(f"  {'ID':<24s} {'Period':<10s} {'Created':<24s} {'Engines Summarized'}")
    console.print(f"  {'─' * 80}")

    for b in briefings:
        bid = str(b.get("id", ""))[:24]
        period = b.get("period", "?")
        created = str(b.get("created_at", ""))[:24]
        metrics = b.get("metrics", {})
        engine_count = metrics.get("engine_runs_summarized", 0)
        console.print(f"  {bid:<24s} {period:<10s} {created:<24s} {engine_count}")

    console.print()
