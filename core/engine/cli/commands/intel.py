"""ace intel / ace search — query intelligence."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console, print_intelligence, print_phase


@click.command()
@click.argument("domain_path")
@click.option("--org", "-o", default="product:default", help="Organization ID")
@click.pass_context
def intel(ctx, domain_path, org):
    """Show accumulated intelligence at a domain path."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.get(
            f"{url}/intel/{domain_path}",
            params={"product": org},
            headers=headers,
            timeout=30,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        snapshot = resp.json()
        print_intelligence(snapshot)

        # Also show maturation
        try:
            mat_resp = httpx.get(
                f"{url}/intel/{domain_path}/maturation",
                params={"product": org},
                headers=headers,
                timeout=10,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            console.print(f"[red]Cannot connect to server:[/red] {e}")
            return
        if mat_resp.status_code == 200:
            mat = mat_resp.json()
            console.print("\nMaturation: ", end="")
            print_phase(mat.get("phase", 1))
            console.print(f"Score: {mat.get('score', 0)}/100")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


@click.command()
@click.argument("query")
@click.option("--org", "-o", default="product:default")
@click.pass_context
def search(ctx, query, org):
    """Search across all insights."""
    url = ctx.obj["url"]
    headers = get_headers()

    try:
        resp = httpx.get(
            f"{url}/intel/search",
            params={"q": query, "product": org},
            headers=headers,
            timeout=30,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        console.print(f"[red]Cannot connect to server:[/red] {e}")
        return

    if resp.status_code == 200:
        data = resp.json()
        if data.get("results"):
            for r in data["results"]:
                console.print(f"  [{r.get('insight_type', '?')}] {r.get('content', '')}")
                console.print(f"    [dim]confidence: {r.get('confidence', 0):.2f} | {r.get('domain_hint', '')}[/dim]")
            console.print(f"\n[dim]{data.get('count', 0)} results[/dim]")
        else:
            console.print("[dim]No results found.[/dim]")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
