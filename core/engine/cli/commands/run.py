# engine/cli/commands/run.py
"""ace run / ace quick — submit tasks."""

import time

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console, print_deliberation_receipt, print_task_result

_TERMINAL_TASK_STATES = {"completed", "failed", "degraded"}
_TASK_POLL_TIMEOUT_SECONDS = 900.0


def _feedback_payload(feedback: str) -> dict:
    payload = {"feedback_human": feedback, "surface": "cli"}
    if feedback == "edited":
        payload["edited_output"] = click.prompt("Edited result", type=str)
    return payload


def _submit_and_wait(url: str, body: dict, headers: dict) -> tuple[dict | None, str | None]:
    """Submit promptly, then poll the durable receipt for CLI compatibility."""
    payload = {**body, "wait_seconds": 1.0}
    try:
        response = httpx.post(f"{url}/tasks", json=payload, headers=headers, timeout=30)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        return None, f"Submission connection failed: {exc}"

    if response.status_code not in (200, 202):
        return None, f"Error {response.status_code}: {response.text}"

    task = response.json()
    # Old servers returned output without a status; preserve that compatibility.
    if task.get("status") in _TERMINAL_TASK_STATES or task.get("output") is not None:
        return task, None

    task_id = task.get("id")
    if not task_id:
        return task, "Server returned a non-terminal task without a durable identifier"

    console.print(f"[dim]Accepted as {task_id}; waiting on the durable receipt…[/dim]")
    deadline = time.monotonic() + _TASK_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(1.0)
        try:
            status_response = httpx.get(f"{url}/tasks/{task_id}", headers=headers, timeout=10)
        except (httpx.ConnectError, httpx.TimeoutException):
            continue
        if status_response.status_code != 200:
            continue
        task = status_response.json()
        if task.get("status") in _TERMINAL_TASK_STATES:
            return task, None

    return task, f"Polling stopped; {task_id} may still be running and remains retrievable"


@click.command()
@click.argument("description")
@click.option("--workspace", "-w", default="workspace:default", help="Workspace ID")
@click.option("--deep", is_flag=True, default=False, help="Force multi-framework synthesis")
@click.option(
    "--skill",
    "force_skill",
    default=None,
    hidden=True,
    help="Legacy experimental compatibility selector",
)
@click.option("--framework", "framework_hints", multiple=True, help="Suggest a reasoning framework (repeatable)")
@click.option(
    "--show-deliberation",
    is_flag=True,
    default=False,
    help="Print the bounded attributable-deliberation receipt after the result.",
)
@click.pass_context
def run(ctx, description, workspace, deep, force_skill, framework_hints, show_deliberation):
    """Submit a task and wait for the result."""
    url = ctx.obj["url"]
    headers = get_headers()

    body = {"description": description, "workspace_id": workspace}
    if deep:
        body["deep"] = True
    if force_skill:
        body["force_skill"] = force_skill
    if framework_hints:
        body["frameworks_hint"] = list(framework_hints)

    with console.status("Running task..."):
        result, error = _submit_and_wait(url, body, headers)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
    if result and result.get("status") == "completed" or (result and result.get("status") is None):
        print_task_result(result)

        # Show framework info if used
        if result.get("strategies_used"):
            frameworks = ", ".join(result["strategies_used"])
            console.print(f"\n[dim]Frameworks: {frameworks}[/dim]")
        if result.get("skill_slug"):
            console.print(f"[dim]Skill: {result['skill_slug']}[/dim]")

        # Prompt for feedback
        feedback = click.prompt(
            "\n[a]ccept / [r]eject / [e]dit",
            type=click.Choice(["a", "r", "e"], case_sensitive=False),
            default="a",
        )
        feedback_map = {"a": "accepted", "r": "rejected", "e": "edited"}
        task_id = result.get("id")
        if task_id:
            httpx.patch(
                f"{url}/tasks/{task_id}",
                json=_feedback_payload(feedback_map[feedback]),
                headers=headers,
                timeout=10,
            )
            console.print(f"[dim]Feedback recorded: {feedback_map[feedback]}[/dim]")
    elif result:
        console.print(f"[yellow]Task {result.get('id', '?')}: {result.get('status', 'unknown')}[/yellow]")
        if result.get("error"):
            console.print(result["error"].get("message", "Task did not complete"))
    if show_deliberation and result:
        print_deliberation_receipt(result)


@click.command()
@click.argument("description")
@click.option("--workspace", "-w", default="workspace:default")
@click.pass_context
def quick(ctx, description, workspace):
    """Submit a quick task using the budget model."""
    url = ctx.obj["url"]
    headers = get_headers()

    with console.status("Running quick task..."):
        result, error = _submit_and_wait(
            url,
            {"description": description, "workspace_id": workspace, "model": "budget"},
            headers,
        )
    if error:
        console.print(f"[yellow]{error}[/yellow]")
    if result and result.get("status") == "completed" or (result and result.get("status") is None):
        print_task_result(result)

        feedback = click.prompt(
            "\n[a]ccept / [r]eject / [e]dit",
            type=click.Choice(["a", "r", "e"], case_sensitive=False),
            default="a",
        )
        feedback_map = {"a": "accepted", "r": "rejected", "e": "edited"}
        task_id = result.get("id")
        if task_id:
            httpx.patch(
                f"{url}/tasks/{task_id}",
                json=_feedback_payload(feedback_map[feedback]),
                headers=headers,
                timeout=10,
            )
            console.print(f"[dim]Feedback recorded: {feedback_map[feedback]}[/dim]")
    elif result:
        console.print(f"[yellow]Task {result.get('id', '?')}: {result.get('status', 'unknown')}[/yellow]")
