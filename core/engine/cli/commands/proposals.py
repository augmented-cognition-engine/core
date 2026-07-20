# engine/cli/commands/proposals.py
"""ace proposals — manage synapse proposals."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.group()
@click.pass_context
def proposals(ctx):
    """Manage synapse proposals."""
    pass


@proposals.command("list")
@click.option("--org", "-o", default="product:default")
@click.pass_context
def list_proposals(ctx, org):
    """List pending synapse proposals."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.get(f"{url}/proposals", params={"product": org}, headers=headers, timeout=30)
    except (httpx.ConnectError, httpx.TimeoutException):
        console.print("[red]Cannot connect to ACE API[/red]")
        return

    if resp.status_code != 200:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        return

    data = resp.json()
    props = data.get("proposals", [])

    if not props:
        console.print("[dim]No pending proposals.[/dim]")
        return

    console.print("\n[bold]Synapse Proposals[/bold]\n")
    for p in props:
        co = p.get("co_occurrence", 0)
        from_slug = p.get("from_slug", "?")
        to_slug = p.get("to_slug", "?")
        console.print(f"  {p.get('id', '?')}: {from_slug} <-> {to_slug}  co-occurrence: {co}")


@proposals.command()
@click.argument("synapse_id")
@click.pass_context
def confirm(ctx, synapse_id):
    """Confirm a synapse proposal."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.post(f"{url}/proposals/{synapse_id}/confirm", headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException):
        console.print("[red]Cannot connect to ACE API[/red]")
        return

    if resp.status_code == 200:
        console.print(f"[green]Confirmed:[/green] {synapse_id}")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@proposals.command()
@click.argument("synapse_id")
@click.pass_context
def dismiss(ctx, synapse_id):
    """Dismiss a synapse proposal (doubles threshold)."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.post(f"{url}/proposals/{synapse_id}/dismiss", headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException):
        console.print("[red]Cannot connect to ACE API[/red]")
        return

    if resp.status_code == 200:
        data = resp.json()
        console.print(
            f"[yellow]Dismissed:[/yellow] {synapse_id} (next threshold: {data.get('dismiss_threshold', '?')})"
        )
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
