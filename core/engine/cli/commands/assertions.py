"""Inspect a relational assertion and its complete resolution trail."""

import json

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.command("assertion")
@click.argument("assertion_id")
@click.pass_context
def assertion(ctx, assertion_id):
    """Show evidence, proposals, reviews, history, and operational projection."""
    try:
        response = httpx.get(f"{ctx.obj['url']}/assertions/{assertion_id}", headers=get_headers(), timeout=30)
        response.raise_for_status()
    except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as exc:
        console.print(f"[red]Unable to inspect assertion:[/red] {exc}")
        return
    console.print_json(json.dumps(response.json(), default=str))
