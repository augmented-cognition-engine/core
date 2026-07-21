# engine/cli/commands/login.py
"""ace login — mint a bearer token from an API key and save it locally.

Collapses the manual `curl -X POST /auth/token | python -c '...'` bootstrap
(docs/build-your-first-extension.md §3) into one command, and wires the
`save_config` helper (core/engine/cli/auth.py) that previously had no
caller.
"""

import click
import httpx

from core.engine.cli.auth import get_base_url, get_config_path, save_config
from core.engine.cli.display import console


@click.command()
@click.option("--url", envvar="ACE_URL", default=None, help="ACE API URL")
@click.option(
    "--api-key",
    envvar="ACE_API_KEY",
    default=None,
    help="ACE API key (or set ACE_API_KEY, or omit to be prompted)",
)
@click.pass_context
def login(ctx, url, api_key):
    """Authenticate with the ACE server and save a bearer token.

    Exchanges an API key for a bearer token via POST /auth/token and writes
    it to ~/.ace/token.json — the same file every `ace` subcommand reads via
    get_token(), locked down to 0600 by save_config().
    """
    # URL precedence: subcommand `--url` (explicit) / ACE_URL env — click folds
    # both into the `url` option, explicit winning — then the group's resolved
    # `ctx.obj["url"]` (so `ace --url <staging> login` authenticates against the
    # server every other subcommand targets, not a silently-dropped default),
    # then get_base_url()'s default. Auth against the wrong server is dangerous,
    # so the group option must never be silently discarded.
    group_url = (ctx.obj or {}).get("url")
    resolved_url = url or group_url or get_base_url()

    if not api_key:
        api_key = click.prompt("API key", hide_input=True)

    try:
        resp = httpx.post(f"{resolved_url}/auth/token", json={"api_key": api_key}, timeout=10)
    except httpx.ConnectError:
        console.print(
            f"[red]Cannot connect to ACE at {resolved_url}.[/red] "
            "Is the server running? Start it with `ace service start` (or run `ace setup` first), or pass "
            "`--url`/set `ACE_URL` if it's running somewhere else."
        )
        raise SystemExit(1)
    except httpx.TimeoutException:
        console.print(f"[red]Timed out connecting to ACE at {resolved_url}.[/red]")
        raise SystemExit(1)

    if resp.status_code == 401:
        console.print(
            "[red]Login failed: invalid API key.[/red] Check `API_KEY` (or `DEMO_PASS`) in your .env and try again."
        )
        raise SystemExit(1)
    if resp.status_code != 200:
        # Truncate the raw server body — it's unsanitized and shouldn't be
        # echoed verbatim next to our curated messages.
        detail = resp.text[:200].strip()
        console.print(f"[red]Login failed ({resp.status_code}).[/red] Server said: {detail}")
        raise SystemExit(1)

    token = resp.json().get("token")
    if not token:
        console.print("[red]Login failed:[/red] server response did not include a token.")
        raise SystemExit(1)

    save_config(resolved_url, token)
    console.print(f"[green]Logged in.[/green] Token saved to {get_config_path()} (mode 0600) — `ace run` now works.")
