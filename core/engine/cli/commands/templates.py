"""ace templates — template management."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.group("templates")
@click.pass_context
def templates(ctx):
    """Manage templates."""
    pass


@templates.command("list")
@click.option("--org", default=None)
@click.pass_context
def list_cmd(ctx, org):
    """List templates."""
    url = ctx.obj["url"]
    headers = get_headers()
    params = {}
    if org:
        params["product"] = org

    try:
        resp = httpx.get(f"{url}/templates", params=params, headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        pbs = data.get("templates", [])
        if not pbs:
            console.print("[dim]No templates found.[/dim]")
            return
        for pb in pbs:
            console.print(f"  {pb.get('id', ''):25} {pb.get('name', '')} [dim](used {pb.get('times_used', 0)}x)[/dim]")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@templates.command("show")
@click.argument("template_id")
@click.pass_context
def show(ctx, template_id):
    """Show template detail."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.get(f"{url}/templates/{template_id}", headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"\n[bold]{data.get('name', 'Untitled')}[/bold]")
        console.print(f"  {data.get('description', '')}")
        console.print(f"  Domain: {data.get('domain_path', '?')}")
        console.print(f"  Used: {data.get('times_used', 0)} times")
        variables = data.get("variables", [])
        if variables:
            console.print("  Variables:")
            for v in variables:
                console.print(f"    - {v.get('name', '?')}: {v.get('prompt', '?')}")
    elif resp.status_code == 404:
        console.print(f"[red]Template not found:[/red] {template_id}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@templates.command("run")
@click.argument("template_id")
@click.pass_context
def run_template(ctx, template_id):
    """Instantiate a template with interactive variable prompts."""
    url = ctx.obj["url"]
    headers = get_headers()

    # First, fetch the template to get variable definitions
    try:
        resp = httpx.get(f"{url}/templates/{template_id}", headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code != 200:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        return

    pb = resp.json()
    console.print(f"\n[bold]Running template:[/bold] {pb.get('name', '')}")

    # Prompt for variables
    variables = {}
    for var in pb.get("variables", []):
        default = var.get("default", "")
        value = click.prompt(f"  {var.get('prompt', var.get('name', '?'))}", default=default or "")
        variables[var["name"]] = value

    # Instantiate
    try:
        with console.status("Creating initiative from template..."):
            resp = httpx.post(
                f"{url}/templates/{template_id}/instantiate",
                json={"variables": variables},
                headers=headers,
                timeout=30,
            )
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Initiative created:[/green] {data.get('id', 'unknown')}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
