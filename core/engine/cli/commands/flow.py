# engine/cli/commands/flow.py
"""ace flow — manage domain flow control settings."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.group(invoke_without_command=True)
@click.option("--org", "-o", default="product:default")
@click.pass_context
def flow(ctx, org):
    """Manage domain flow control settings."""
    ctx.ensure_object(dict)
    ctx.obj["flow_org"] = org
    if ctx.invoked_subcommand is None:
        url = ctx.obj["url"]
        headers = get_headers()

        try:
            resp = httpx.get(f"{url}/flow-config", params={"product": org}, headers=headers, timeout=30)
        except (httpx.ConnectError, httpx.TimeoutException):
            console.print("[red]Cannot connect to ACE API[/red]")
            return

        if resp.status_code != 200:
            console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
            return

        data = resp.json()
        configs = data.get("configs", [])
        unconfigured = data.get("unconfigured_domains", [])

        console.print(f"\n[bold]Flow Configuration[/bold] ({org})\n")
        console.print(f"  {'Domain':<20s} {'Clearance':<14s} {'Propagate':<12s} {'Consume':<10s} {'Contribute':<12s}")
        console.print(f"  {'─' * 68}")

        for c in configs:
            slug = c.get("domain_slug", "?")
            clr = c.get("default_clearance", "open")
            prop = "yes" if c.get("insight_propagation", True) else "no"
            consume = "yes" if c.get("consume_org_intelligence", True) else "no"
            contrib = "yes" if c.get("contribute_org_intelligence", True) else "no"
            console.print(f"  {slug:<20s} {clr:<14s} {prop:<12s} {consume:<10s} {contrib:<12s}")

        for slug in unconfigured:
            console.print(f"  {slug:<20s} {'open':<14s} {'yes':<12s} {'yes':<10s} {'yes':<12s} [dim](default)[/dim]")

        console.print(f"\n  [dim]{len(configs)} configured, {len(unconfigured)} using defaults[/dim]")


@flow.command("get")
@click.argument("domain")
@click.option("--org", "-o", default="product:default")
@click.pass_context
def get_config(ctx, domain, org):
    """Show flow config for a domain."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.get(f"{url}/flow-config/{domain}", params={"product": org}, headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException):
        console.print("[red]Cannot connect to ACE API[/red]")
        return

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"\n[bold]{domain}[/bold]")
        console.print(f"  Clearance:   {data.get('default_clearance', 'open')}")
        console.print(f"  Propagation: {'yes' if data.get('insight_propagation', True) else 'no'}")
        console.print(f"  Consume org: {'yes' if data.get('consume_org_intelligence', True) else 'no'}")
        console.print(f"  Contribute:  {'yes' if data.get('contribute_org_intelligence', True) else 'no'}")
        if data.get("defaults"):
            console.print("  [dim](using defaults — no explicit config)[/dim]")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@flow.command("set")
@click.argument("domain")
@click.option("--clearance", type=click.Choice(["open", "domain", "restricted", "sealed"]), default=None)
@click.option("--propagation/--no-propagation", default=None)
@click.option("--consume/--no-consume", default=None)
@click.option("--contribute/--no-contribute", default=None)
@click.option("--org", "-o", default="product:default")
@click.pass_context
def set_config(ctx, domain, clearance, propagation, consume, contribute, org):
    """Set flow config for a domain."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        current = httpx.get(f"{url}/flow-config/{domain}", params={"product": org}, headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException):
        console.print("[red]Cannot connect to ACE API[/red]")
        return

    if current.status_code != 200:
        console.print(f"[red]Error getting current config:[/red] {current.text}")
        return

    data = current.json()

    body = {
        "product_id": org,
        "default_clearance": clearance or data.get("default_clearance", "open"),
        "insight_propagation": propagation if propagation is not None else data.get("insight_propagation", True),
        "consume_org_intelligence": consume if consume is not None else data.get("consume_org_intelligence", True),
        "contribute_org_intelligence": contribute
        if contribute is not None
        else data.get("contribute_org_intelligence", True),
    }

    try:
        resp = httpx.put(f"{url}/flow-config/{domain}", json=body, headers=headers, timeout=10)
    except (httpx.ConnectError, httpx.TimeoutException):
        console.print("[red]Cannot connect to ACE API[/red]")
        return

    if resp.status_code == 200:
        console.print(f"[green]Updated:[/green] {domain}")
        ctx.invoke(get_config, domain=domain, org=org)
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
