"""Read-only product landscape inspection through the supported ACE CLI."""

from __future__ import annotations

import json

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console
from core.engine.product.living_graph import PROJECTION_VERSION


@click.command("landscape")
@click.option(
    "--projection-version",
    default=PROJECTION_VERSION,
    show_default=True,
    help="Pinned compatibility version for the read projection.",
)
@click.pass_context
def landscape(ctx, projection_version: str):
    """Inspect product objects, evidence, decisions, uncertainty, and outcomes."""
    try:
        response = httpx.get(
            f"{ctx.obj['url']}/product/landscape",
            params={"projection_version": projection_version},
            headers=get_headers(),
            timeout=30,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise click.ClickException(
            "ACE API is unavailable. Run `ace doctor`, restore the service if needed, and retry this read."
        ) from exc

    if response.status_code != 200:
        try:
            detail = response.json().get("detail", {})
        except (ValueError, AttributeError):
            detail = {}
        code = detail.get("code", "landscape_read_failed") if isinstance(detail, dict) else "landscape_read_failed"
        recovery = (
            detail.get("recovery", "Run `ace doctor` and retry.")
            if isinstance(detail, dict)
            else "Run `ace doctor` and retry."
        )
        raise click.ClickException(f"{code}: {recovery}")

    console.print_json(json.dumps(response.json(), sort_keys=True, default=str))
