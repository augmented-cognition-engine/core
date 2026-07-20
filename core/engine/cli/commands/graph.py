# engine/cli/commands/graph.py
"""ace graph — show synaptic connections."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.command()
@click.argument("domain_path", required=False)
@click.option("--org", "-o", default="product:default")
@click.pass_context
def graph(ctx, domain_path, org):
    """Show synaptic graph connections."""
    url = ctx.obj["url"]
    headers = get_headers()

    path = f"/graph/{domain_path}" if domain_path else "/graph"

    try:
        resp = httpx.get(f"{url}{path}", params={"product": org}, headers=headers, timeout=30)
    except (httpx.ConnectError, httpx.TimeoutException):
        console.print("[red]Cannot connect to ACE API[/red]")
        return

    if resp.status_code != 200:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        return

    data = resp.json()
    edges = data.get("edges", [])

    if not edges:
        console.print("[dim]No connections found.[/dim]")
        return

    console.print(f"\n[bold]Synaptic Graph[/bold] ({org})\n")

    confirmed = 0
    proposals = 0

    for e in edges:
        strength = e.get("strength", 0)
        dots = int(strength * 5)
        dot_str = "●" * dots + "○" * (5 - dots)
        origin = e.get("origin", "")
        iface = e.get("interface_type", "") or ""
        is_confirmed = e.get("confirmed", False)

        from_id = e.get("from", "?")[:30]
        to_id = e.get("to", "?")[:30]

        if is_confirmed:
            confirmed += 1
            arrow = f"--{iface}-->" if e.get("direction") == "one_way" else f"<-{iface}-->"
            console.print(f"  {from_id:30s} {arrow:20s} {to_id:30s}  {dot_str} {strength:.2f}  {origin}")
        else:
            proposals += 1
            console.print(
                f"  {from_id:30s} {'- - - - - ->':20s} {to_id:30s}  {dot_str} {strength:.2f}  {origin} [yellow](proposed)[/yellow]"
            )

    console.print(f"\n  [dim]{confirmed + proposals} connections ({confirmed} confirmed, {proposals} proposals)[/dim]")
