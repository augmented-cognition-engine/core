# engine/cli/commands/sentinel.py
"""CLI commands for sentinel scheduler management.

ace sentinel status — show scheduler status + engine list
ace sentinel runs — show recent engine run history
ace sentinel trigger <engine> — manually trigger an engine run

Spec: docs/superpowers/specs/2026-03-21-phase3a-scheduler-signals.md
"""

from __future__ import annotations

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.group()
def sentinel():
    """Sentinel scheduler management."""
    pass


@sentinel.command()
@click.pass_context
def status(ctx):
    """Show scheduler status and registered engines."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        response = httpx.get(f"{url}/sentinel/status", headers=headers)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)

    running = data.get("scheduler_running", False)
    status_text = "[green]running[/green]" if running else "[red]stopped[/red]"
    console.print(f"\nSentinel Scheduler ({status_text})\n")

    from rich.table import Table

    table = Table()
    table.add_column("Engine", style="cyan")
    table.add_column("Cron")
    table.add_column("Last Run")
    table.add_column("Status")
    table.add_column("Duration")

    engines = data.get("engines", [])
    failures_7d = 0

    for eng in engines:
        last_run = eng.get("last_run")
        if last_run:
            run_time = str(last_run.get("started_at", "—"))[:16].replace("T", " ")
            run_status = last_run.get("status", "—")
            duration_ms = last_run.get("duration_ms")
            duration = f"{duration_ms / 1000:.1f}s" if duration_ms else "—"
            if run_status == "failed":
                failures_7d += 1
                run_status = f"[red]{run_status}[/red]"
            elif run_status == "completed":
                run_status = f"[green]{run_status}[/green]"
        else:
            run_time = "—"
            run_status = "—"
            duration = "—"

        table.add_row(eng["name"], eng["cron"], run_time, run_status, duration)

    console.print(table)
    console.print(f"\n  {len(engines)} engines registered, {failures_7d} failures in last 7 days\n")


@sentinel.command()
@click.option("--org", default="product:default", help="Organization ID")
@click.option("--engine", "engine_name", default=None, help="Filter by engine name")
@click.option("--limit", default=20, help="Max results")
@click.pass_context
def runs(ctx, org: str, engine_name: str | None, limit: int):
    """Show recent engine run history."""
    url = ctx.obj["url"]
    headers = get_headers()

    params = {"product": org, "limit": limit}
    if engine_name:
        params["engine"] = engine_name

    try:
        response = httpx.get(f"{url}/sentinel/runs", params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)

    from rich.table import Table

    table = Table()
    table.add_column("ID", style="dim")
    table.add_column("Engine", style="cyan")
    table.add_column("Status")
    table.add_column("Started")
    table.add_column("Duration")
    table.add_column("Results")

    for run in data.get("runs", []):
        run_id = str(run.get("id", "—"))
        engine = run.get("engine", "—")
        run_status = run.get("status", "—")
        started = str(run.get("started_at", "—"))[:19].replace("T", " ")
        duration_ms = run.get("duration_ms")
        duration = f"{duration_ms / 1000:.1f}s" if duration_ms else "—"
        results = str(run.get("results", "—"))[:60]

        if run_status == "failed":
            run_status = f"[red]{run_status}[/red]"
        elif run_status == "completed":
            run_status = f"[green]{run_status}[/green]"

        table.add_row(run_id, engine, run_status, started, duration, results)

    console.print(table)


@sentinel.command()
@click.argument("engine_name")
@click.option("--org", default="product:default", help="Organization ID")
@click.pass_context
def trigger(ctx, engine_name: str, org: str):
    """Manually trigger an engine run."""
    url = ctx.obj["url"]
    headers = get_headers()

    console.print(f"Triggering {engine_name}...")

    try:
        response = httpx.post(
            f"{url}/sentinel/trigger/{engine_name}",
            params={"product": org},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]Error:[/red] Engine '{engine_name}' not found")
        else:
            console.print(f"[red]Error:[/red] {e.response.text}")
        raise SystemExit(1)
    except httpx.HTTPError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)

    status = data.get("status", "unknown")
    duration_ms = data.get("duration_ms", 0)
    results = data.get("results", {})

    if status == "completed":
        console.print(f"  Engine run: {data.get('engine_run_id', '—')}")
        console.print(f"  Status: [green]{status}[/green] ({duration_ms / 1000:.1f}s)")
        if results:
            results_str = ", ".join(f"{k}: {v}" for k, v in results.items())
            console.print(f"  Results: {results_str}")
    elif status == "failed":
        console.print(f"  Engine run: {data.get('engine_run_id', '—')}")
        console.print(f"  Status: [red]{status}[/red]")
        console.print(f"  Error: {data.get('error', '—')}")
    else:
        console.print(f"  Status: {status}")
