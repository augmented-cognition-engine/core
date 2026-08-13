"""Launch the installed Atrium command center."""

from __future__ import annotations

import click
import uvicorn

from core.engine.api.canvas_host import create_app
from core.engine.atrium import static_dir


@click.command("atrium")
@click.option("--port", type=click.IntRange(1, 65535), default=5173, show_default=True)
@click.option("--open/--no-open", "open_browser", default=True, show_default=True)
@click.pass_context
def atrium(ctx: click.Context, port: int, open_browser: bool) -> None:
    """Open Atrium, the personal ACE Intelligence command center.

    The ACE API must already be running (``ace service start``).  Atrium is
    served from this installed package and forwards API calls same-origin, so
    neither a source checkout nor a JavaScript development server is required.
    """

    api_url = str(ctx.obj.get("url", "")).rstrip("/")
    token = ctx.obj.get("token")
    if not api_url:
        raise click.ClickException("No ACE API URL is configured. Run `ace setup` first.")
    if not token:
        raise click.ClickException("No ACE login is available. Run `ace setup` or `ace login`, then retry.")

    assets = static_dir()
    if not (assets / "index.html").is_file():
        raise click.ClickException(
            "This ace-core installation does not contain Atrium assets. Reinstall the release package and retry."
        )

    app = create_app(
        dist=assets,
        core_api_url=api_url,
        access_token=str(token),
    )
    address = f"http://127.0.0.1:{port}/atrium"
    click.echo(f"Atrium is available at {address}")
    click.echo(f"Forwarding its ACE requests to {api_url}")
    if open_browser:
        click.launch(address)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
