"""Inspect ACE's provider-neutral fast/capable/frontier model policy."""

from __future__ import annotations

import json

import click

from core.engine.cli.display import console
from core.engine.core.model_policy import build_model_policy


@click.command("model-policy")
@click.option("--json-output", is_flag=True, help="Emit machine-readable policy and validation")
def model_policy(json_output: bool) -> None:
    """Show effective route, role mapping, cost/privacy posture, and fallback."""
    try:
        # Loading server settings at command-registration time makes unrelated
        # client-only commands such as `ace login` require server secrets.
        from core.engine.core.config import settings

        policy = build_model_policy(settings)
    except Exception as exc:
        if json_output:
            click.echo(json.dumps({"valid": False, "error": str(exc)}, indent=2))
        else:
            console.print(f"[red]Model policy is invalid:[/red] {exc}")
        raise SystemExit(1) from exc

    payload = policy.public_dict()
    if json_output:
        click.echo(json.dumps(payload, indent=2))
    else:
        access = payload["access"]
        console.print(
            f"Route: [bold]{access['provider']}[/bold] ({access['access_class']}; "
            f"cost={access['cost_model']}; privacy={access['privacy']}; "
            f"availability={access['availability']}; concurrency={access['concurrency']})"
        )
        readiness_style = "green" if payload["ready"] else "yellow"
        console.print(
            f"Readiness: [{readiness_style}]{payload['readiness_state']}[/{readiness_style}] "
            f"(interactive_suitable={str(payload['interactive_suitable']).lower()})"
        )
        for role in payload["roles"]:
            console.print(
                f"  {role['role']}: {role['resolved_model']} "
                f"(requested {role['requested_model']}; effort={role['resolved_effort']}; {role['purpose']})"
            )
        console.print(f"Escalation: {payload['escalation']}")
        console.print(f"Fallback: {payload['fallback']}")
        for warning in payload["warnings"]:
            console.print(f"[yellow]DEGRADED:[/yellow] {warning}")
        for error in payload["validation_errors"]:
            console.print(f"[red]FAILED:[/red] {error}")
    if not policy.valid:
        raise SystemExit(1)
