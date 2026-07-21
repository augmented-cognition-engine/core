"""ace doctor — diagnose the developer-preview golden path."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console

_PROVIDER_GUIDE = "https://github.com/augmented-cognition-engine/core/blob/main/docs/providers.md"


def _safe_url(value: str) -> str:
    """Remove userinfo before a URL is rendered in diagnostics."""
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    except (TypeError, ValueError):
        return "configured endpoint"


def _model_policy_check(settings) -> tuple[bool, dict[str, Any]]:
    from core.engine.core.model_policy import build_model_policy

    policy = build_model_policy(settings)
    return policy.valid, policy.public_dict()


async def _provider_check(settings, *, live: bool, timeout: float):
    from core.engine.core.provider_diagnostics import diagnose_provider

    return await diagnose_provider(settings, live=live, timeout=timeout)


def _recovery_actions(checks: dict[str, dict[str, object]]) -> list[str]:
    """Return product-facing next steps for the failed readiness checks."""
    failed = {name for name, item in checks.items() if not bool(item["ok"])}
    if "configuration" in failed:
        return [
            "Run `ace setup` (source checkout: `uv run ace setup`) to repair configuration, then rerun `ace doctor`.",
        ]
    if failed & {"surrealdb", "schema", "api"}:
        return [
            "Run `ace service start` (source checkout: `uv run ace service start`).",
            "If startup fails, inspect `ace service logs --lines 80`.",
            "Then rerun `ace doctor`.",
        ]
    if failed & {"model_provider", "model_policy"}:
        return [
            "Run `ace setup` (source checkout: `uv run ace setup`) to choose or repair a provider, "
            f"using {_PROVIDER_GUIDE} if needed; then rerun `ace doctor`.",
        ]
    return []


async def _database_check(settings) -> tuple[bool, str, bool, str]:
    from surrealdb import AsyncSurreal

    from core.engine.core.db import SurrealPool

    expected = max(int(p.name[1:4]) for p in (Path(__file__).parents[3] / "schema").glob("v*.surql"))
    db = AsyncSurreal(settings.surreal_url)
    try:
        await db.connect()
        await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
        await db.use(settings.surreal_ns, settings.surreal_db)
        # `value` is reserved in SurrealDB 3.2; SELECT * is compatible with the
        # repository's pinned 3.1 runtime and newer local installations.
        result = await db.query("SELECT * FROM config_entry WHERE key = 'schema_version'")
        rows = result[0] if result and isinstance(result[0], list) else result
        actual = int(rows[0]["value"]) if rows else 0
        safe_db_url = SurrealPool._redact_url(settings.surreal_url)
        return True, safe_db_url, actual == expected, f"{actual} (expected {expected})"
    except Exception as exc:
        safe_db_url = SurrealPool._redact_url(settings.surreal_url)
        return False, f"{safe_db_url}: {type(exc).__name__}", False, "unavailable"
    finally:
        try:
            await db.close()
        except Exception:
            pass


@click.command()
@click.option("--json-output", is_flag=True, help="Emit machine-readable JSON")
@click.option(
    "--live-provider",
    is_flag=True,
    help="Make one minimal provider request to verify authentication and model reachability",
)
@click.option(
    "--provider-timeout",
    type=click.FloatRange(min=1.0, max=300.0),
    default=30.0,
    show_default=True,
    help="Deadline in seconds for the explicitly requested live provider check",
)
@click.pass_context
def doctor(ctx, json_output: bool, live_provider: bool, provider_timeout: float):
    """Check configuration, database, schema, auth, provider, API, and MCP."""
    checks: dict[str, dict[str, object]] = {}
    try:
        from core.engine.core.config import settings

        checks["configuration"] = {"ok": True, "detail": ".env loaded"}
    except Exception as exc:
        checks["configuration"] = {
            "ok": False,
            "state": "invalid_configuration",
            "layer": "configuration",
            "detail": f"Configuration could not be loaded ({type(exc).__name__}).",
            "action": "Check .env values and rerun `ace setup` or `ace doctor`.",
        }
        settings = None

    if settings:
        db_ok, db_detail, schema_ok, schema_detail = asyncio.run(_database_check(settings))
        checks["surrealdb"] = {"ok": db_ok, "detail": db_detail}
        checks["schema"] = {"ok": schema_ok, "detail": schema_detail}
        provider_result = asyncio.run(_provider_check(settings, live=live_provider, timeout=provider_timeout))
        checks["model_provider"] = provider_result.public_dict()
        try:
            model_policy_ok, model_policy_detail = _model_policy_check(settings)
            checks["model_policy"] = {"ok": model_policy_ok, "detail": model_policy_detail}
        except Exception as exc:
            checks["model_policy"] = {
                "ok": False,
                "detail": f"Model policy could not be resolved ({type(exc).__name__}).",
            }
    else:
        for name in ("surrealdb", "schema", "model_provider", "model_policy"):
            checks[name] = {"ok": False, "detail": "configuration unavailable"}

    url = ctx.obj["url"]
    safe_url = _safe_url(url)
    try:
        response = httpx.get(f"{url}/health", timeout=5)
        checks["api"] = {"ok": response.status_code == 200, "detail": f"{safe_url} ({response.status_code})"}
    except httpx.HTTPError as exc:
        checks["api"] = {"ok": False, "detail": f"{safe_url}: {type(exc).__name__}"}

    headers = get_headers()
    if not headers.get("Authorization"):
        checks["authentication"] = {
            "ok": False,
            "detail": "no saved bearer token; run `ace login --api-key <API_KEY>`",
        }
    elif not checks["api"]["ok"]:
        checks["authentication"] = {
            "ok": False,
            "detail": "unavailable because the API is not healthy",
        }
    else:
        try:
            protected = httpx.get(
                f"{url}/intel/context",
                params={"q": "doctor", "product": "product:default"},
                headers=headers,
                timeout=5,
            )
            auth_ok = protected.status_code == 200
            checks["authentication"] = {
                "ok": auth_ok,
                "detail": (
                    "protected request accepted"
                    if auth_ok
                    else f"protected request rejected ({protected.status_code}); run `ace login --api-key <API_KEY>`"
                ),
            }
        except httpx.HTTPError as exc:
            checks["authentication"] = {
                "ok": False,
                "detail": f"protected request failed ({type(exc).__name__}); check API reachability and retry",
            }

    try:
        from ace_mcp_client.server import mcp

        tools = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in tools}
        expected = {
            "ace_start",
            "ace_load",
            "ace_capture",
            "ace_task",
            "ace_status",
            "ace_capture_idea",
            "ace_search",
            "ace_briefing",
            "ace_impact",
            "ace_history",
            "ace_related",
        }
        checks["mcp"] = {"ok": names == expected, "detail": f"{len(names)}/11 public tools registered"}
    except Exception as exc:
        checks["mcp"] = {"ok": False, "detail": str(exc)}

    ok = all(bool(item["ok"]) for item in checks.values())
    recovery = _recovery_actions(checks) if not ok else []
    if json_output:
        import json

        click.echo(json.dumps({"ok": ok, "checks": checks, "recovery": recovery}, indent=2))
    else:
        for name, item in checks.items():
            if item["ok"]:
                mark, color = "PASS", "green"
            elif item.get("state") in {"configured_unverified", "authenticated"}:
                mark, color = "CHECK", "yellow"
            else:
                mark, color = "FAIL", "red"
            state = f" [{item['state']}]" if item.get("state") else ""
            console.print(f"[{color}]{mark}[/{color}] {name}{state}: {item['detail']}")
            if item.get("action") and not item["ok"]:
                console.print(f"  Next: {item['action']}")
        console.print("\n[green]ACE is ready.[/green]" if ok else "\n[red]ACE is not ready.[/red]")
        if recovery:
            console.print("\n[bold]Recovery[/bold]")
            for action in recovery:
                console.print(f"- {action}")
    if not ok:
        raise SystemExit(1)
