"""Reusable, provider-free conformance checks for extension task actions."""

from __future__ import annotations

from typing import Any

from core.engine.extensions.invocation import (
    ExtensionActorContext,
    ExtensionCapabilityManifest,
    ExtensionInvocationEnvelope,
    RegisteredTaskAction,
    build_extension_receipt,
    invocation_metadata,
    prepare_action,
    project_action_outcome,
)

CONFORMANCE_VERSION = "extension-task-action-conformance-v1"


async def run_task_action_conformance(
    action: RegisteredTaskAction,
    envelope: ExtensionInvocationEnvelope,
    actor: ExtensionActorContext,
    *,
    sample_output: str = "A bounded sample output.",
) -> dict[str, Any]:
    """Exercise the stable, non-metered portion of an action's public contract.

    Runtime restart, database isolation, idempotency, concurrency, and cancellation
    remain API/runtime tests because a pure extension callback cannot prove them.
    """
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail[:500]})

    try:
        ExtensionCapabilityManifest.model_validate(action.public_manifest())
        record("capability_manifest", True)
    except Exception as exc:
        record("capability_manifest", False, str(exc))

    record(
        "input_contract_negotiation",
        envelope.contract_version in action.accepted_input_contract_versions,
    )
    try:
        plan = await prepare_action(action, envelope, actor)
        record("preparation_and_reference_accounting", True)
    except Exception as exc:
        record("preparation_and_reference_accounting", False, str(exc))
        plan = None

    outcome = None
    try:
        outcome = await project_action_outcome(action, sample_output, {"state": "complete"})
        record("outcome_projection_and_validation", outcome.contract_version == action.output_contract)
    except Exception as exc:
        record("outcome_projection_and_validation", False, str(exc))

    if plan is not None:
        metadata = invocation_metadata(envelope, plan, action)
        receipt = build_extension_receipt(
            {
                "id": "task:conformance",
                "status": "completed",
                "output": sample_output,
                "execution": {"state": "complete"},
                "reasoning_trace": {"provenance": {"provider": "fixture", "model": "fixture:model"}},
            },
            metadata,
            outcome=outcome,
        )
        serialized = str(receipt)
        record("bounded_public_receipt", len(serialized) <= 100_000)
        record("private_plan_not_public", plan.description not in serialized)

    return {
        "contract_version": CONFORMANCE_VERSION,
        "extension_id": action.extension_id,
        "extension_version": action.extension_version,
        "action": action.action,
        "passed": bool(checks) and all(check["passed"] for check in checks),
        "checks": checks,
    }
