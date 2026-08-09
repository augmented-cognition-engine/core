"""Builder-facing governed-cognition lifecycle over the supported HTTP API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.commands.run import _submit_and_wait
from core.engine.cli.display import console


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
            code = str(detail.get("code") or "cognition_request_failed")
            reason = detail.get("reason") or detail.get("recovery")
        else:
            code = "cognition_request_failed"
            reason = None
        suffix = f": {reason}" if reason else ""
        raise click.ClickException(f"{code}{suffix}")
    value = response.json()
    if not isinstance(value, dict):
        raise click.ClickException("ACE returned an invalid governed-cognition response.")
    return value


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise click.ClickException(f"Draft body does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Draft body is not valid JSON: {path} ({exc.msg})") from exc
    if not isinstance(value, dict):
        raise click.ClickException("Draft body must be one JSON object.")
    return value


def _print(payload: dict[str, Any]) -> None:
    console.print_json(json.dumps(payload, sort_keys=True, default=str))


def _require_attributed_use(task: dict[str, Any]) -> None:
    if task.get("status") != "completed":
        raise click.ClickException(f"cognition_use_not_completed: task state is {task.get('status', 'unknown')}")
    selection = task.get("cognition_selection_receipt")
    use = task.get("cognition_use_receipt")
    if not isinstance(selection, dict) or not isinstance(use, dict):
        raise click.ClickException("cognition_use_attribution_missing")
    selected = tuple(str(item) for item in selection.get("selected_revision_ids", []))
    used = tuple(str(item) for item in use.get("selected_revision_ids", []))
    if not selected or selected != used or use.get("state") != "used" or not use.get("material_use_hash"):
        raise click.ClickException("cognition_use_attribution_incomplete")


@click.group("cognition")
def cognition() -> None:
    """Teach, inspect, govern, use, and retire reusable cognition."""


@cognition.command("teach")
@click.argument("task_id")
@click.option("--stable-key", required=True, help="Stable product-scoped cognition key.")
@click.option("--name", required=True, help="Human-readable cognition name.")
@click.option("--description", required=True, help="What the reusable cognition does.")
@click.option("--intent", required=True, help="Why this task should become reusable cognition.")
@click.option("--base-recipe", default="coding_intelligence", show_default=True)
@click.option("--draft-body", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.pass_context
def teach(
    ctx: click.Context,
    task_id: str,
    stable_key: str,
    name: str,
    description: str,
    intent: str,
    base_recipe: str,
    draft_body: Path | None,
) -> None:
    """Create a non-selectable sourced proposal from an existing task."""
    body: dict[str, Any] = {
        "task_id": task_id,
        "stable_key": stable_key,
        "name": name,
        "description": description,
        "intent": intent,
        "base_recipe_slug": base_recipe,
    }
    if draft_body is not None:
        body["draft_body"] = _json_file(draft_body)
    _print(_request(ctx, "POST", "/cognition/proposals/from-task", json=body))


@cognition.command("inspect")
@click.argument("proposal_id")
@click.pass_context
def inspect_proposal(ctx: click.Context, proposal_id: str) -> None:
    """Inspect a proposal and its durable governance state."""
    _print(_request(ctx, "GET", f"/cognition/proposals/{proposal_id}"))


@cognition.command("diff")
@click.argument("proposal_id")
@click.pass_context
def proposal_diff(ctx: click.Context, proposal_id: str) -> None:
    """Inspect the exact semantic change before review."""
    _print(_request(ctx, "GET", f"/cognition/proposals/{proposal_id}/diff"))


@cognition.command("review")
@click.argument("proposal_id")
@click.option("--review-request-id", required=True, help="Caller-stable idempotency identity.")
@click.option(
    "--disposition",
    required=True,
    type=click.Choice(["approve", "reject", "request_changes"], case_sensitive=False),
)
@click.option("--rationale", required=True)
@click.option("--expected-generation", type=click.IntRange(min=0), default=0, show_default=True)
@click.pass_context
def review(
    ctx: click.Context,
    proposal_id: str,
    review_request_id: str,
    disposition: str,
    rationale: str,
    expected_generation: int,
) -> None:
    """Record an authorized human disposition and durable receipt."""
    _print(
        _request(
            ctx,
            "POST",
            f"/cognition/proposals/{proposal_id}/review",
            json={
                "review_request_id": review_request_id,
                "disposition": disposition,
                "rationale": rationale,
                "expected_head_generation": expected_generation,
            },
        )
    )


@cognition.command("use")
@click.argument("stable_key")
@click.argument("description")
@click.option("--workspace", "-w", default="workspace:default", show_default=True)
@click.option("--timeout", type=click.FloatRange(min=1, max=900), default=900.0, show_default=True)
@click.pass_context
def use_cognition(
    ctx: click.Context,
    stable_key: str,
    description: str,
    workspace: str,
    timeout: float,
) -> None:
    """Run a fresh task that requires one approved cognition identity."""
    from core.engine.cli.commands import run as run_module

    prior_timeout = run_module._TASK_POLL_TIMEOUT_SECONDS
    run_module._TASK_POLL_TIMEOUT_SECONDS = timeout
    try:
        task, error = _submit_and_wait(
            ctx.obj["url"],
            {
                "description": description,
                "workspace_id": workspace,
                "force_skill": stable_key,
            },
            get_headers(),
        )
    finally:
        run_module._TASK_POLL_TIMEOUT_SECONDS = prior_timeout
    if task is None:
        raise click.ClickException(error or "ACE did not return a task receipt.")
    if error:
        raise click.ClickException(f"cognition_use_incomplete: {error}")
    _require_attributed_use(task)
    _print(task)


@cognition.command("revision")
@click.argument("revision_id")
@click.pass_context
def revision(ctx: click.Context, revision_id: str) -> None:
    """Inspect one immutable cognition revision."""
    _print(_request(ctx, "GET", f"/cognition/revisions/{revision_id}"))


@cognition.command("head")
@click.argument("head_id")
@click.pass_context
def head(ctx: click.Context, head_id: str) -> None:
    """Inspect the current product-scoped active pointer."""
    _print(_request(ctx, "GET", f"/cognition/heads/{head_id}"))


@cognition.command("lifecycle")
@click.argument("head_id")
@click.option("--review-request-id", required=True, help="Caller-stable idempotency identity.")
@click.option(
    "--action",
    required=True,
    type=click.Choice(["rollback", "reactivate", "disable", "expire", "retire"], case_sensitive=False),
)
@click.option("--rationale", required=True)
@click.option("--expected-generation", required=True, type=click.IntRange(min=1))
@click.option("--target-revision")
@click.option("--expires-at", help="Timezone-aware ISO-8601 expiry for reactivation.")
@click.pass_context
def lifecycle(
    ctx: click.Context,
    head_id: str,
    review_request_id: str,
    action: str,
    rationale: str,
    expected_generation: int,
    target_revision: str | None,
    expires_at: str | None,
) -> None:
    """Apply a human-authorized rollback, reactivation, disablement, expiry, or retirement."""
    body: dict[str, Any] = {
        "review_request_id": review_request_id,
        "action": action,
        "rationale": rationale,
        "expected_head_generation": expected_generation,
    }
    if target_revision is not None:
        body["target_revision_id"] = target_revision
    if expires_at is not None:
        body["expires_at"] = expires_at
    _print(_request(ctx, "POST", f"/cognition/heads/{head_id}/lifecycle", json=body))


@cognition.command("selection")
@click.argument("receipt_id")
@click.pass_context
def selection(ctx: click.Context, receipt_id: str) -> None:
    """Inspect the exact bounded-selection receipt from a task."""
    _print(_request(ctx, "GET", f"/cognition/selections/{receipt_id}"))


@cognition.command("use-receipt")
@click.argument("receipt_id")
@click.pass_context
def use_receipt(ctx: click.Context, receipt_id: str) -> None:
    """Inspect exact cognition-use attribution from a task."""
    _print(_request(ctx, "GET", f"/cognition/uses/{receipt_id}"))
