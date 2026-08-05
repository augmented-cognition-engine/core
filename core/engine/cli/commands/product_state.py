"""Extension-first Productized State workflow through supported ACE APIs."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console

_TERMINAL_TASK_STATES = {"completed", "failed", "degraded"}


def _request(ctx: click.Context, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = httpx.request(
            method,
            f"{ctx.obj['url']}{path}",
            headers=get_headers(),
            timeout=30,
            **kwargs,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise click.ClickException(
            "ACE is unavailable. Run `ace service start`, then `ace doctor`, and retry."
        ) from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", {})
        except (ValueError, AttributeError):
            detail = {}
        if isinstance(detail, dict):
            code = detail.get("code", "product_state_request_failed")
            recovery = detail.get("recovery", "Run `ace doctor`, inspect the input, and retry intentionally.")
        else:
            code = "product_state_request_failed"
            recovery = "Run `ace doctor`, inspect the input, and retry intentionally."
        raise click.ClickException(f"{code}: {recovery}")
    value = response.json()
    if not isinstance(value, dict):
        raise click.ClickException("ACE returned an invalid Product State response.")
    return value


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise click.ClickException(f"Input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Input file is not valid JSON: {path} ({exc.msg})") from exc
    if not isinstance(value, dict):
        raise click.ClickException("Product State input must be one JSON object.")
    return value


def _print(payload: dict[str, Any]) -> None:
    console.print_json(json.dumps(payload, sort_keys=True, default=str))


@click.group("state")
def state() -> None:
    """Give a product inspectable, extension-owned state without forking Core."""


@state.command("capabilities")
@click.pass_context
def state_capabilities(ctx: click.Context) -> None:
    """Show installed State adapters, versions, actions, and authority boundaries."""
    _print(_request(ctx, "GET", "/product-state/capabilities"))


@state.command("ingest")
@click.argument("input_file", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.pass_context
def state_ingest(ctx: click.Context, input_file: Path) -> None:
    """Ingest extension-mapped context under the authenticated product scope."""
    _print(_request(ctx, "POST", "/product-state/ingestions", json=_json_file(input_file)))


@state.command("inspect")
@click.pass_context
def state_inspect(ctx: click.Context) -> None:
    """Inspect state, decisions, attribution, corrections, and outcomes read-only."""
    snapshot = _request(ctx, "GET", "/product/landscape")
    _print(
        {
            "contract_version": "ace.product-state.inspection/v1",
            "snapshot_id": snapshot.get("snapshot_id"),
            "projection_state": snapshot.get("projection_state"),
            "authority": snapshot.get("authority"),
            "state_engine": snapshot.get("state_engine", {}),
            "decisions": snapshot.get("decisions", []),
            "tasks": (snapshot.get("work") or {}).get("tasks", []),
            "corrections": [
                item
                for item in (snapshot.get("intelligence") or {}).get("observations", [])
                if item.get("observation_type") == "correction"
            ],
            "source_states": snapshot.get("source_states", []),
            "issues": snapshot.get("issues", []),
        }
    )


@state.command("invoke")
@click.argument("input_file", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.option("--wait/--no-wait", default=True, show_default=True, help="Wait for a terminal durable task receipt.")
@click.option("--timeout", type=click.FloatRange(min=1, max=900), default=120.0, show_default=True)
@click.pass_context
def state_invoke(ctx: click.Context, input_file: Path, wait: bool, timeout: float) -> None:
    """Invoke one installed extension action from a versioned JSON envelope."""
    task = _request(ctx, "POST", "/extension-invocations", json=_json_file(input_file))
    if wait and task.get("status") not in _TERMINAL_TASK_STATES:
        deadline = time.monotonic() + timeout
        while task.get("status") not in _TERMINAL_TASK_STATES and time.monotonic() < deadline:
            time.sleep(0.25)
            task = _request(ctx, "GET", f"/tasks/{task['id']}")
        if task.get("status") not in _TERMINAL_TASK_STATES:
            raise click.ClickException(
                f"Task {task.get('id')} is still {task.get('status')}. Retrieve the same receipt with `ace status`."
            )
    _print(task)


@state.command("correct")
@click.argument("content")
@click.option("--domain", "domain_path", required=True, help="Extension-owned domain path.")
@click.option("--correction-id", help="Stable product identifier to prefix in the retained correction.")
@click.option("--confidence", type=click.FloatRange(min=0, max=1), default=1.0, show_default=True)
@click.pass_context
def state_correct(
    ctx: click.Context,
    content: str,
    domain_path: str,
    correction_id: str | None,
    confidence: float,
) -> None:
    """Capture an explicit human correction; promotion authority remains separate."""
    text = f"{correction_id}: {content}" if correction_id else content
    _print(
        _request(
            ctx,
            "POST",
            "/observations",
            json={
                "observation_type": "correction",
                "content": text,
                "domain_path": domain_path,
                "confidence": confidence,
            },
        )
    )
