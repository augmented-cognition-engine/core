"""Reusable, provider-free conformance checks for extension task actions."""

from __future__ import annotations

import json
from typing import Any

from core.engine.extensions.invocation import (
    ExtensionActorContext,
    ExtensionCapabilityManifest,
    ExtensionInvocationEnvelope,
    ExtensionInvocationReceipt,
    ExtensionOutcome,
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
    """Exercise the provider-free portion of an experimental action contract.

    Runtime restart, database isolation, idempotency, concurrency, and cancellation
    remain API/runtime tests because a pure extension callback cannot prove them.
    """
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail[:500]})

    try:
        first_manifest = action.public_manifest()
        ExtensionCapabilityManifest.model_validate(first_manifest)
        record("capability_manifest", True)
        record("deterministic_manifest", first_manifest == action.public_manifest())
        record(
            "public_manifest_excludes_callables",
            all(name not in first_manifest for name in ("prepare", "project_outcome", "validate_outcome")),
        )
    except Exception as exc:
        record("capability_manifest", False, str(exc))
        record("deterministic_manifest", False, str(exc))
        record("public_manifest_excludes_callables", False, str(exc))

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
        repeated_outcome = await project_action_outcome(action, sample_output, {"state": "complete"})
        record("deterministic_outcome_projection", outcome == repeated_outcome)
    except Exception as exc:
        record("outcome_projection_and_validation", False, str(exc))
        record("deterministic_outcome_projection", False, str(exc))

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
        serialized = json.dumps(receipt, sort_keys=True)
        try:
            ExtensionInvocationReceipt.model_validate(receipt)
            record("public_receipt_schema", True)
        except Exception as exc:
            record("public_receipt_schema", False, str(exc))
        record("bounded_public_receipt", len(serialized) <= 100_000)
        record("private_plan_not_public", plan.description not in serialized)
        record(
            "private_resolver_content_not_public",
            all(context.content not in serialized for context in plan.context_records),
        )
        record(
            "recommendation_decision_adoption_separation",
            receipt["human_decision"] is None and receipt["adoption"] is None,
        )

        projection_failure = build_extension_receipt(
            {
                "id": "task:conformance-projection-failure",
                "status": "completed",
                "output": sample_output,
                "execution": {"state": "complete"},
                "reasoning_trace": {"provenance": {"provider": "fixture", "model": "fixture:model"}},
            },
            metadata,
            projection_error="token=conformance-private",
        )
        record(
            "projection_failure_preserves_raw_core_output",
            projection_failure["raw_core_output"] == {"available": True, "content": sample_output}
            and projection_failure["coverage"]["state"] == "degraded"
            and any(
                failure.get("code") == "outcome_projection_failed"
                for failure in projection_failure["failures"]
                if isinstance(failure, dict)
            ),
        )
        failure_serialized = str(projection_failure)
        record(
            "credential_redaction",
            "conformance-private" not in failure_serialized and "<redacted>" in failure_serialized,
        )

    invalid_artifacts = [
        {
            "contract_version": action.output_contract,
            "artifact_refs": [
                {
                    "namespace": action.extension_id,
                    "kind": "artifact",
                    "id": "artifact:mutable",
                }
            ],
        },
        {
            "contract_version": action.output_contract,
            "artifact_refs": [
                {
                    "namespace": action.extension_id,
                    "kind": "artifact",
                    "id": "artifact:unaccounted",
                    "digest": "sha256:conformance",
                }
            ],
        },
    ]
    rejected = 0
    for candidate in invalid_artifacts:
        try:
            ExtensionOutcome.model_validate(candidate)
        except Exception:
            rejected += 1
    record(
        "immutable_artifact_provenance_rules",
        rejected == len(invalid_artifacts),
    )

    return {
        "contract_version": CONFORMANCE_VERSION,
        "extension_id": action.extension_id,
        "extension_version": action.extension_version,
        "action": action.action,
        "passed": bool(checks) and all(check["passed"] for check in checks),
        "checks": checks,
    }
