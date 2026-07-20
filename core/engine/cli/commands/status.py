"""ace status — check server health."""

import click
import httpx

from core.engine.cli.display import console


@click.command()
@click.pass_context
def status(ctx):
    """Check ACE server status."""
    url = ctx.obj["url"]
    try:
        resp = httpx.get(f"{url}/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            console.print(f"[green]ACE is running[/green] — v{data.get('version', '?')} at {url}")
        else:
            console.print(f"[yellow]ACE responded with {resp.status_code}[/yellow]")
    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to ACE at {url}[/red]")
