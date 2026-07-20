# engine/cli/commands/evolve.py
"""CLI command: ace evolve — trigger evolution engine on-demand."""

import click
import httpx


@click.command()
@click.option("--now", is_flag=True, default=True, help="Run evolution immediately")
@click.pass_context
def evolve(ctx, now):
    """Trigger the evolution engine to run on-demand."""
    url = ctx.obj["url"]
    token = ctx.obj["token"]

    click.echo("Triggering evolution engine...")
    try:
        resp = httpx.post(
            f"{url}/evolution/run",
            headers={"Authorization": f"Bearer {token}"},
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()

        click.echo(f"Status: {data.get('status', 'unknown')}")
        click.echo(f"Hypotheses: {data.get('hypotheses', 0)}")
        click.echo(f"Researched: {data.get('researched', 0)}")
        click.echo(f"Experiments: {data.get('experiments_run', 0)}")
        click.echo(f"Committed: {data.get('committed', 0)}")
        click.echo(f"Cost: ${data.get('cost', 0):.2f}")
    except httpx.HTTPError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
