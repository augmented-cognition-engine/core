"""ace idea / ace ideas — idea lifecycle management."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.command("idea")
@click.argument("text")
@click.option("--workspace", "-w", default=None)
@click.pass_context
def idea(ctx, text, workspace):
    """Capture a new idea."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        with console.status("Capturing idea..."):
            resp = httpx.post(
                f"{url}/ideas",
                json={"raw_input": text, "workspace_id": workspace},
                headers=headers,
                timeout=30,
            )
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 201:
        data = resp.json()
        console.print(f"[green]Idea captured:[/green] {data.get('id', 'unknown')}")
        console.print(f"  Title: {data.get('title', text[:50])}")
        console.print(f"  Status: {data.get('status', 'captured')}")
        tags = data.get("tags", [])
        if tags:
            console.print(f"  Tags: {', '.join(tags)}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@click.group("ideas")
@click.pass_context
def ideas(ctx):
    """Manage ideas."""
    pass


@ideas.command("list")
@click.option("--status", "-s", default=None)
@click.option("--org", default=None)
@click.pass_context
def list_cmd(ctx, status, org):
    """List ideas."""
    url = ctx.obj["url"]
    headers = get_headers()
    params = {}
    if status:
        params["status"] = status
    if org:
        params["product"] = org

    try:
        resp = httpx.get(f"{url}/ideas", params=params, headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        idea_list = data.get("ideas", [])
        if not idea_list:
            console.print("[dim]No ideas found.[/dim]")
            return
        status_colors = {
            "captured": "blue",
            "qualifying": "yellow",
            "incubating": "cyan",
            "ready": "green",
            "active": "magenta",
            "completed": "dim",
            "archived": "red",
        }
        for i in idea_list:
            color = status_colors.get(i.get("status", ""), "white")
            console.print(f"  [{color}]{i.get('status', '?'):12}[/{color}] {i.get('id', ''):25} {i.get('title', '')}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@ideas.command("show")
@click.argument("idea_id")
@click.pass_context
def show(ctx, idea_id):
    """Show idea detail."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.get(f"{url}/ideas/{idea_id}", headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"\n[bold]{data.get('title', 'Untitled')}[/bold]")
        console.print(f"  Status: {data.get('status', '?')}")
        brief = data.get("brief")
        if brief:
            console.print(f"\n  [bold]What:[/bold] {brief.get('what', '')}")
            console.print(f"  [bold]Why:[/bold] {brief.get('why', '')}")
            console.print(f"  [bold]Approach:[/bold] {brief.get('approach', '')}")
            console.print(f"  [bold]Effort:[/bold] {brief.get('effort', '')}")
            console.print(f"  [bold]First step:[/bold] {brief.get('first_step', '')}")
    elif resp.status_code == 404:
        console.print(f"[red]Idea not found:[/red] {idea_id}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@ideas.command("qualify")
@click.argument("idea_id")
@click.option("--answer", "-a", multiple=True, help="Answer to qualifying question")
@click.pass_context
def qualify(ctx, idea_id, answer):
    """Answer qualifying questions for an idea."""
    url = ctx.obj["url"]
    headers = get_headers()

    body = {}
    if answer:
        body["answers"] = list(answer)

    try:
        resp = httpx.post(f"{url}/ideas/{idea_id}/qualify", json=body, headers=headers, timeout=30)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Status:[/green] {data.get('status', '?')}")
        qs = data.get("questions")
        if qs:
            console.print("  Questions:")
            for q in qs:
                console.print(f"    - {q}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@ideas.command("activate")
@click.argument("idea_id")
@click.pass_context
def activate(ctx, idea_id):
    """Activate a ready idea — creates an initiative."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        with console.status("Activating idea..."):
            resp = httpx.post(f"{url}/ideas/{idea_id}/activate", headers=headers, timeout=30)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Initiative created:[/green] {data.get('id', 'unknown')}")
        console.print(f"  Source: {data.get('source', '?')}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
