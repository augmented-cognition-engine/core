"""ace init — initiative lifecycle management."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.group("init")
@click.pass_context
def init(ctx):
    """Manage initiatives."""
    pass


@init.command("create")
@click.argument("title")
@click.option("--description", "-d", default="", help="Initiative description")
@click.option("--priority", "-p", default="medium", type=click.Choice(["low", "medium", "high", "critical"]))
@click.option("--budget", "-b", type=float, default=None, help="Cost budget")
@click.option("--workspace", "-w", default="workspace:default")
@click.pass_context
def create(ctx, title, description, priority, budget, workspace):
    """Create a new initiative."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.post(
            f"{url}/initiatives",
            json={
                "title": title,
                "description": description or title,
                "workspace_id": workspace,
                "priority": priority,
                "cost_budget": budget,
            },
            headers=headers,
            timeout=30,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 201:
        result = resp.json()
        console.print(f"[green]Initiative created:[/green] {result.get('id', 'unknown')}")
        console.print(f"  Title: {result.get('title', title)}")
        console.print(f"  Status: {result.get('status', 'planning')}")
        console.print(f"  Priority: {result.get('priority', priority)}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@init.command("list")
@click.option(
    "--status", "-s", default=None, type=click.Choice(["planning", "active", "paused", "completed", "cancelled"])
)
@click.option("--org", default=None)
@click.pass_context
def list_cmd(ctx, status, org):
    """List initiatives."""
    url = ctx.obj["url"]
    headers = get_headers()

    params = {}
    if status:
        params["status"] = status
    if org:
        params["product"] = org

    try:
        resp = httpx.get(f"{url}/initiatives", params=params, headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        initiatives = data.get("initiatives", [])
        if not initiatives:
            console.print("[dim]No initiatives found.[/dim]")
            return
        for init_item in initiatives:
            status_color = {
                "planning": "blue",
                "active": "green",
                "paused": "yellow",
                "completed": "dim",
                "cancelled": "red",
            }.get(init_item.get("status", ""), "white")
            console.print(
                f"  [{status_color}]{init_item.get('status', '?'):10}[/{status_color}] "
                f"{init_item.get('id', ''):30} {init_item.get('title', '')}"
            )
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@init.command("activate")
@click.argument("initiative_id")
@click.pass_context
def activate(ctx, initiative_id):
    """Activate a planning-stage initiative."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.post(f"{url}/initiatives/{initiative_id}/activate", headers=headers, timeout=30)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        console.print(f"[green]Initiative activated:[/green] {initiative_id}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@init.command("status")
@click.argument("initiative_id")
@click.pass_context
def status_cmd(ctx, initiative_id):
    """Show initiative status with milestones and progress."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.get(f"{url}/initiatives/{initiative_id}", headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"\n[bold]{data.get('title', '')}[/bold]")
        console.print(f"  Status: {data.get('status', '?')}")
        console.print(f"  Priority: {data.get('priority', '?')}")
        console.print(f"  Progress: {data.get('progress', 0)}%")

        budget = data.get("budget_status", {})
        if budget.get("status") != "ok":
            console.print(f"  [yellow]Budget: {budget.get('percentage', 0)}% ({budget.get('status', '')})[/yellow]")

        milestones = data.get("milestones_detail", [])
        if milestones:
            console.print("\n  [bold]Milestones:[/bold]")
            for ms in milestones:
                ms_status = ms.get("status", "pending")
                icon = {"completed": "✓", "active": "▶", "review": "⏸", "blocked": "✗"}.get(ms_status, "○")
                console.print(f"    {icon} M{ms.get('sequence', '?')}: {ms.get('title', '')}")
    elif resp.status_code == 404:
        console.print(f"[red]Initiative not found:[/red] {initiative_id}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@init.command("pause")
@click.argument("initiative_id")
@click.pass_context
def pause(ctx, initiative_id):
    """Pause a running initiative."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.post(f"{url}/initiatives/{initiative_id}/pause", headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        console.print(f"[yellow]Initiative paused:[/yellow] {initiative_id}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@init.command("cancel")
@click.argument("initiative_id")
@click.pass_context
def cancel(ctx, initiative_id):
    """Cancel an initiative."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.post(f"{url}/initiatives/{initiative_id}/cancel", headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        console.print(f"[red]Initiative cancelled:[/red] {initiative_id}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
