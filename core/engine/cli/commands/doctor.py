"""ace doctor — diagnose the developer-preview golden path."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


def _model_policy_check(settings) -> tuple[bool, dict[str, Any]]:
    from core.engine.core.model_policy import build_model_policy

    policy = build_model_policy(settings)
    return policy.valid, policy.public_dict()


def _provider_configured(settings) -> tuple[bool, str]:
    if settings.openai_compat_base_url:
        return True, f"OpenAI-compatible ({settings.openai_compat_model})"
    if settings.ollama_host:
        return True, f"Ollama ({settings.ollama_model})"
    if getattr(settings, "subscription_provider", "auto") == "codex":
        from core.engine.core.llm import _find_codex_bin

        codex_bin = _find_codex_bin()
        if codex_bin:
            effort = getattr(settings, "codex_cli_effort", "default")
            return True, f"Codex CLI / ChatGPT subscription ({settings.codex_cli_model}, effort={effort})"
        return False, "SUBSCRIPTION_PROVIDER=codex but Codex CLI is unavailable"
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return True, "Claude subscription token"
    if settings.llm_api_key and settings.llm_api_key not in {
        "dev-placeholder-not-a-real-key",
        "sk-test",
        "sk-test-placeholder",
    }:
        return True, f"Anthropic ({settings.llm_model})"
    if shutil.which("claude"):
        return True, "Claude CLI"
    return False, "no usable provider; configure one path from docs/providers.md"


async def _database_check(settings) -> tuple[bool, str, bool, str]:
    from surrealdb import AsyncSurreal

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
        return True, settings.surreal_url, actual == expected, f"{actual} (expected {expected})"
    except Exception as exc:
        return False, f"{settings.surreal_url}: {exc}", False, "unavailable"
    finally:
        try:
            await db.close()
        except Exception:
            pass


@click.command()
@click.option("--json-output", is_flag=True, help="Emit machine-readable JSON")
@click.pass_context
def doctor(ctx, json_output: bool):
    """Check configuration, database, schema, auth, provider, API, and MCP."""
    checks: dict[str, dict[str, object]] = {}
    try:
        from core.engine.core.config import settings

        checks["configuration"] = {"ok": True, "detail": ".env loaded"}
    except Exception as exc:
        checks["configuration"] = {"ok": False, "detail": str(exc)}
        settings = None

    if settings:
        db_ok, db_detail, schema_ok, schema_detail = asyncio.run(_database_check(settings))
        checks["surrealdb"] = {"ok": db_ok, "detail": db_detail}
        checks["schema"] = {"ok": schema_ok, "detail": schema_detail}
        provider_ok, provider_detail = _provider_configured(settings)
        checks["model_provider"] = {"ok": provider_ok, "detail": provider_detail}
        try:
            model_policy_ok, model_policy_detail = _model_policy_check(settings)
            checks["model_policy"] = {"ok": model_policy_ok, "detail": model_policy_detail}
        except Exception as exc:
            checks["model_policy"] = {"ok": False, "detail": str(exc)}
    else:
        for name in ("surrealdb", "schema", "model_provider", "model_policy"):
            checks[name] = {"ok": False, "detail": "configuration unavailable"}

    url = ctx.obj["url"]
    try:
        response = httpx.get(f"{url}/health", timeout=5)
        checks["api"] = {"ok": response.status_code == 200, "detail": f"{url} ({response.status_code})"}
    except httpx.HTTPError as exc:
        checks["api"] = {"ok": False, "detail": f"{url}: {exc}"}

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
            checks["authentication"] = {"ok": False, "detail": f"protected request failed: {exc}"}

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
    if json_output:
        import json

        click.echo(json.dumps({"ok": ok, "checks": checks}, indent=2))
    else:
        for name, item in checks.items():
            mark = "PASS" if item["ok"] else "FAIL"
            color = "green" if item["ok"] else "red"
            console.print(f"[{color}]{mark}[/{color}] {name}: {item['detail']}")
        console.print("\n[green]ACE is ready.[/green]" if ok else "\n[red]ACE is not ready.[/red]")
    if not ok:
        raise SystemExit(1)
