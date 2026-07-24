from __future__ import annotations

import pytest
from pydantic import ValidationError

import core.engine.extensions.registry as registry
from core.engine.extensions.conformance import run_task_action_conformance
from core.engine.extensions.invocation import (
    ContextResolution,
    ExtensionActorContext,
    ExtensionCapabilityManifest,
    ExtensionInvocationEnvelope,
    ExtensionOutcome,
    ExtensionTaskPlan,
    ResolvedContextRecord,
    build_extension_receipt,
    invocation_metadata,
    normalize_extension_receipt,
    prepare_action,
    project_action_outcome,
)


def _envelope(**updates) -> ExtensionInvocationEnvelope:
    values = {
        "extension_id": "example",
        "extension_version": "1.2.3",
        "action": "decide",
        "workspace_id": "workspace:default",
        "question": "Which option should we choose?",
        "references": [
            {
                "namespace": "example",
                "kind": "decision",
                "id": "decision:42",
                "version": "7",
            }
        ],
        "correlation_id": "corr:test",
    }
    values.update(updates)
    return ExtensionInvocationEnvelope.model_validate(values)


def _prepare(envelope, actor):
    reference = envelope.references[0]
    return ExtensionTaskPlan(
        description=f"{envelope.question}\nReference: {reference.id}",
        context_resolution=[
            ContextResolution(
                reference=reference,
                status="resolved",
                resolver="example.resolve",
                record_version="7",
                content_hash="sha256:record-42",
                product_scope=actor.product_id,
                provenance={"product_id": actor.product_id},
            )
        ],
        context_records=[
            ResolvedContextRecord(
                reference=reference,
                resolver_identity="example.resolve",
                record_version="7",
                content_hash="sha256:record-42",
                product_scope=actor.product_id,
                content="Bounded domain record content.",
            )
        ],
        outcome_contract="example-outcome-v1",
    )


def _project(output, execution):
    return ExtensionOutcome(
        contract_version="example-outcome-v1",
        data={"recommendation": output, "coverage": execution.get("state")},
    )


def test_task_action_requires_scoped_registry():
    with pytest.raises(RuntimeError, match="extension-scoped"):
        registry.Registry().register_task_action("decide", _prepare)


@pytest.mark.asyncio
async def test_provider_free_conformance_covers_manifest_plan_outcome_and_receipt():
    action = registry.RegisteredTaskAction(
        extension_id="example",
        extension_version="1.2.3",
        action="decide",
        prepare=_prepare,
        project_outcome=_project,
        output_contract="example-outcome-v1",
    )

    result = await run_task_action_conformance(
        action,
        _envelope(),
        ExtensionActorContext(
            product_id="product:one",
            workspace_id="workspace:default",
            user_id="user:one",
        ),
    )

    assert result["contract_version"] == "extension-task-action-conformance-v1"
    assert result["passed"] is True
    assert {check["name"] for check in result["checks"]} == {
        "capability_manifest",
        "deterministic_manifest",
        "public_manifest_excludes_callables",
        "input_contract_negotiation",
        "preparation_and_reference_accounting",
        "outcome_projection_and_validation",
        "deterministic_outcome_projection",
        "public_receipt_schema",
        "bounded_public_receipt",
        "private_plan_not_public",
        "private_resolver_content_not_public",
        "recommendation_decision_adoption_separation",
        "projection_failure_preserves_raw_core_output",
        "credential_redaction",
        "immutable_artifact_provenance_rules",
    }


@pytest.mark.asyncio
async def test_scoped_task_action_prepares_and_projects(monkeypatch):
    monkeypatch.setattr(registry, "_task_actions", {})
    reg = registry.Registry(extension_id="example", extension_version="1.2.3")
    registered = reg.register_task_action(
        "decide",
        _prepare,
        project_outcome=_project,
        output_contract="example-outcome-v1",
    )

    action = registry.registered_task_action("example", "decide")
    assert action is not None
    assert registered is action
    envelope = _envelope()
    plan = await prepare_action(
        action,
        envelope,
        ExtensionActorContext(
            product_id="product:one",
            workspace_id="workspace:default",
            user_id="user:one",
        ),
    )
    outcome = await project_action_outcome(action, "Choose A", {"state": "complete"})

    assert plan.context_resolution[0].status == "resolved"
    assert outcome.data == {"recommendation": "Choose A", "coverage": "complete"}
    with pytest.raises(RuntimeError, match="already registered"):
        reg.register_task_action("decide", _prepare)


def test_registration_rejects_invalid_and_duplicate_manifest_values(monkeypatch):
    monkeypatch.setattr(registry, "_task_actions", {})
    reg = registry.Registry(extension_id="example", extension_version="1.2.3")

    with pytest.raises(ValidationError, match="unsupported characters"):
        reg.register_task_action("not valid", _prepare)
    with pytest.raises(ValidationError, match="at least 1 item"):
        reg.register_task_action(
            "no-input-contract",
            _prepare,
            accepted_input_contract_versions=[],
        )
    with pytest.raises(ValidationError, match="at least 1 item"):
        reg.register_task_action("no-lifecycle", _prepare, lifecycle_operations=[])
    with pytest.raises(ValidationError, match="duplicates"):
        reg.register_task_action(
            "duplicate-lifecycle",
            _prepare,
            lifecycle_operations=["submit", "submit"],
        )
    with pytest.raises(ValidationError, match="cancel lifecycle"):
        reg.register_task_action(
            "invalid-cancel",
            _prepare,
            lifecycle_operations=["submit"],
            cancellation_supported=True,
        )


def test_manifest_model_revalidates_public_invariants():
    manifest = registry.RegisteredTaskAction(
        extension_id="example",
        extension_version="1.2.3",
        action="decide",
        prepare=_prepare,
    ).public_manifest()

    assert ExtensionCapabilityManifest.model_validate(manifest).stability == "experimental"
    with pytest.raises(ValidationError, match="duplicates"):
        ExtensionCapabilityManifest.model_validate({**manifest, "lifecycle_operations": ["submit", "submit"]})
    with pytest.raises(ValidationError, match="cancel lifecycle"):
        ExtensionCapabilityManifest.model_validate(
            {
                **manifest,
                "lifecycle_operations": ["submit"],
                "cancellation_supported": True,
            }
        )


def test_task_action_identity_is_unambiguous_when_identifiers_contain_separator(monkeypatch):
    monkeypatch.setattr(registry, "_task_actions", {})
    registry.Registry(extension_id="a:b", extension_version="1").register_task_action("c", _prepare)
    registry.Registry(extension_id="a", extension_version="1").register_task_action("b:c", _prepare)

    assert set(registry._task_actions) == {("a:b", "c"), ("a", "b:c")}
    assert registry._task_actions[("a:b", "c")].identity != registry._task_actions[("a", "b:c")].identity


def test_task_action_registration_is_bounded(monkeypatch):
    monkeypatch.setattr(
        registry,
        "_task_actions",
        {("extension", str(index)): object() for index in range(registry.MAX_TASK_ACTIONS)},
    )
    reg = registry.Registry(extension_id="example", extension_version="1.2.3")

    with pytest.raises(RuntimeError, match=f"limited to {registry.MAX_TASK_ACTIONS}"):
        reg.register_task_action("one-too-many", _prepare)


@pytest.mark.asyncio
async def test_default_projection_and_registered_validator_succeed():
    validated: list[ExtensionOutcome] = []

    def validate(outcome):
        validated.append(outcome)
        return outcome

    default_action = registry.RegisteredTaskAction(
        extension_id="example",
        extension_version="1.2.3",
        action="default",
        prepare=_prepare,
        output_contract="example-outcome-v1",
    )
    default = await project_action_outcome(default_action, "Bounded recommendation.", {"state": "complete"})
    assert default.contract_version == "example-outcome-v1"
    assert default.data == {"content": "Bounded recommendation."}

    validated_action = default_action.model_copy(
        update={
            "action": "validated",
            "project_outcome": _project,
            "validate_outcome": validate,
        }
    )
    projected = await project_action_outcome(validated_action, "Choose A", {"state": "complete"})
    assert projected.data["recommendation"] == "Choose A"
    assert validated == [projected]


@pytest.mark.asyncio
async def test_wrong_contract_and_validator_rejection_fail_projection():
    wrong_contract = registry.RegisteredTaskAction(
        extension_id="example",
        extension_version="1.2.3",
        action="wrong-contract",
        prepare=_prepare,
        project_outcome=lambda output, execution: ExtensionOutcome(
            contract_version="future-outcome-v2",
            data={"content": output},
        ),
        output_contract="example-outcome-v1",
    )
    with pytest.raises(ValueError, match="does not match"):
        await project_action_outcome(wrong_contract, "Choose A", {"state": "complete"})

    def reject(_outcome):
        raise ValueError("token=validator-private")

    rejected = wrong_contract.model_copy(
        update={
            "action": "validator-rejection",
            "project_outcome": _project,
            "validate_outcome": reject,
        }
    )
    with pytest.raises(ValueError, match="validator-private"):
        await project_action_outcome(rejected, "Choose A", {"state": "complete"})


def test_envelope_rejects_duplicate_references():
    reference = {
        "namespace": "example",
        "kind": "decision",
        "id": "decision:42",
        "version": "7",
    }
    with pytest.raises(ValidationError, match="duplicates"):
        _envelope(references=[reference, reference])


def test_outcome_artifacts_require_immutable_matching_provenance():
    artifact = {
        "namespace": "example",
        "kind": "report",
        "id": "artifact:one",
        "digest": "sha256:artifact-one",
    }
    outcome = ExtensionOutcome(
        contract_version="example-outcome-v1",
        artifact_refs=[artifact],
        artifact_provenance=[
            {
                "reference": artifact,
                "producer": "example.decide",
                "source_invocation_id": "task:one",
                "provenance_receipt_ids": ["provenance:one"],
            }
        ],
    )
    assert outcome.artifact_provenance[0].reference.digest == "sha256:artifact-one"

    with pytest.raises(ValidationError, match="artifact_provenance"):
        ExtensionOutcome(
            contract_version="example-outcome-v1",
            artifact_refs=[artifact],
        )

    mutable = {
        "namespace": "example",
        "kind": "report",
        "id": "artifact:mutable",
    }
    with pytest.raises(ValidationError, match="immutable"):
        ExtensionOutcome(
            contract_version="example-outcome-v1",
            artifact_refs=[mutable],
        )

    with pytest.raises(ValidationError, match="no others"):
        ExtensionOutcome(
            contract_version="example-outcome-v1",
            artifact_provenance=[
                {
                    "reference": artifact,
                    "producer": "example.decide",
                }
            ],
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExtensionOutcome(
            contract_version="example-outcome-v1",
            artifact_refs=[artifact],
            artifact_provenance=[
                {
                    "reference": artifact,
                    "producer": "example.decide",
                    "resolver_state": {"private_prompt": "do-not-persist"},
                }
            ],
        )

    with pytest.raises(ValidationError, match="duplicate references"):
        ExtensionOutcome(
            contract_version="example-outcome-v1",
            artifact_refs=[artifact],
            artifact_provenance=[
                {"reference": artifact, "producer": "example.decide"},
                {"reference": artifact, "producer": "example.decide"},
            ],
        )

    with pytest.raises(ValidationError, match="references must not contain duplicates"):
        ExtensionOutcome(
            contract_version="example-outcome-v1",
            artifact_refs=[artifact, artifact],
            artifact_provenance=[
                {"reference": artifact, "producer": "example.decide"},
            ],
        )


@pytest.mark.asyncio
async def test_prepare_requires_exact_reference_resolution_coverage():
    action = registry.RegisteredTaskAction(
        extension_id="example",
        extension_version="1.2.3",
        action="decide",
        prepare=lambda envelope, actor: ExtensionTaskPlan(description="Missing resolution"),
    )
    with pytest.raises(ValueError, match="account for every input reference"):
        await prepare_action(
            action,
            _envelope(),
            ExtensionActorContext(
                product_id="product:one",
                workspace_id="workspace:default",
                user_id="user:one",
            ),
        )

    reference = _envelope().references[0]
    duplicate_action = action.model_copy(
        update={
            "prepare": lambda envelope, actor: ExtensionTaskPlan(
                description="Duplicate resolution",
                context_resolution=[
                    ContextResolution(reference=reference, status="declared", resolver="example.resolve"),
                    ContextResolution(reference=reference, status="declared", resolver="example.resolve"),
                ],
            )
        }
    )
    with pytest.raises(ValueError, match="exactly once"):
        await prepare_action(
            duplicate_action,
            _envelope(),
            ExtensionActorContext(
                product_id="product:one",
                workspace_id="workspace:default",
                user_id="user:one",
            ),
        )


def test_receipt_preserves_attempt_lineage_and_provenance(monkeypatch):
    monkeypatch.setattr(registry, "_task_actions", {})
    reg = registry.Registry(extension_id="example", extension_version="1.2.3")
    reg.register_task_action("decide", _prepare, output_contract="example-outcome-v1")
    action = registry.registered_task_action("example", "decide")
    assert action is not None
    envelope = _envelope()
    plan = _prepare(
        envelope,
        ExtensionActorContext(
            product_id="product:one",
            workspace_id="workspace:default",
            user_id="user:one",
        ),
    )
    metadata = invocation_metadata(
        envelope,
        plan,
        action,
        attempt_number=2,
        retry_of_task_id="task:prior",
    )
    receipt = build_extension_receipt(
        {
            "id": "task:current",
            "status": "completed",
            "output": "Choose A",
            "execution": {"state": "complete"},
            "reasoning_trace": {
                "provenance": {
                    "provider": "OpenAIProvider",
                    "model": "gpt-example",
                    "requested_model": "reasoning",
                }
            },
            "deliberation_receipt": {"receipt_id": "deliberation:one"},
        },
        metadata,
        outcome=ExtensionOutcome(
            contract_version="example-outcome-v1",
            data={"recommendation": "Choose A"},
        ),
    )

    assert receipt["attempt"] == {
        "number": 2,
        "retry_of_task_id": "task:prior",
        "resumed_by_task_id": None,
        "status": "completed",
        "terminal": True,
        "resumable": False,
        "root_invocation_id": "task:prior",
        "retry_reason": "unspecified_retry",
        "retry_actor": "unknown_actor",
        "retry_requested_at": receipt["attempt"]["retry_requested_at"],
        "retry_policy_version": "extension-retry-v1",
    }
    assert receipt["attempt"]["retry_requested_at"] is not None
    assert receipt["input"]["references"][0]["id"] == "decision:42"
    assert "product_id" not in receipt["input"]["context_resolution"][0]["provenance"]
    assert receipt["outcome"]["data"]["recommendation"] == "Choose A"
    assert receipt["provenance"]["provider"] == "OpenAIProvider"
    assert receipt["coverage"]["state"] == "complete"


def test_public_receipt_redacts_credentials_and_recanonicalizes_stored_fields():
    envelope = _envelope()
    action = registry.RegisteredTaskAction(
        extension_id="example",
        extension_version="1.2.3",
        action="decide",
        prepare=_prepare,
    )
    plan = _prepare(
        envelope,
        ExtensionActorContext(
            product_id="product:one",
            workspace_id="workspace:default",
            user_id="user:one",
        ),
    )
    metadata = invocation_metadata(envelope, plan, action)
    metadata["capability"]["prompt"] = "secret=capability-private"
    metadata["context_resolution"][0]["note"] = "token=context-private"
    metadata["context_resolution"][0]["provenance"]["source"] = "password=source-private"
    task = {
        "id": "task:redaction",
        "status": "completed",
        "output": "authorization=output-private",
        "execution": {"state": "complete"},
        "reasoning_trace": {"provenance": {"provider": "fixture", "model": "fixture:model"}},
        "extension_invocation": metadata,
    }
    receipt = build_extension_receipt(
        task,
        metadata,
        outcome={"contract_version": "example-v1", "data": {"api_key": "outcome-private"}},
        projection_error="bearer projection-private",
    )
    serialized = str(receipt)
    assert "capability-private" not in serialized
    assert "context-private" not in serialized
    assert "source-private" not in serialized
    assert "outcome-private" not in serialized
    assert "projection-private" not in serialized
    assert "<redacted>" in serialized

    task["extension_receipt"] = {
        "contract_version": "extension-invocation-receipt-v1",
        "attempt": {"resumed_by_task_id": "token=stored-private"},
        "outcome": receipt["outcome"],
    }
    normalized = normalize_extension_receipt(task["extension_receipt"], task=task)
    assert normalized["attempt"]["resumed_by_task_id"] is None
    assert "stored-private" not in str(normalized)


def test_outcome_bounds_nested_redaction_artifacts_and_decision_separation():
    envelope = _envelope()
    action = registry.RegisteredTaskAction(
        extension_id="example",
        extension_version="1.2.3",
        action="decide",
        prepare=_prepare,
        output_contract="example-outcome-v1",
    )
    plan = _prepare(
        envelope,
        ExtensionActorContext(
            product_id="product:one",
            workspace_id="workspace:default",
            user_id="user:one",
        ),
    )
    metadata = invocation_metadata(envelope, plan, action)
    artifact = {
        "namespace": "example",
        "kind": "report",
        "id": "artifact:one",
        "digest": "sha256:artifact-one",
    }
    outcome = ExtensionOutcome(
        contract_version="example-outcome-v1",
        data={
            "recommendation": "Choose A",
            "private_prompt": "prompt-private",
            "resolver_state": {"content": "resolver-private"},
            "nested": {"token": "nested-private"},
            "items": [f"item-{index}" for index in range(250)],
        },
        artifact_refs=[artifact],
        artifact_provenance=[
            {
                "reference": artifact,
                "producer": "token=artifact-private",
                "provenance_receipt_ids": ["receipt:one"],
            }
        ],
        warnings=["authorization=warning-private"],
    )
    task = {
        "id": "task:outcome",
        "status": "completed",
        "output": "Usable raw output.",
        "execution": {"state": "complete"},
        "reasoning_trace": {"provenance": {"provider": "fixture", "model": "fixture:model"}},
    }
    receipt = build_extension_receipt(task, metadata, outcome=outcome)
    serialized = str(receipt)

    assert receipt["outcome"]["data"]["recommendation"] == "Choose A"
    assert receipt["outcome"]["data"]["private_prompt"] == "<redacted>"
    assert receipt["outcome"]["data"]["resolver_state"] == "<redacted>"
    assert receipt["outcome"]["data"]["nested"]["token"] == "<redacted>"
    assert len(receipt["outcome"]["data"]["items"]) == 200
    assert receipt["artifacts"][0]["reference"]["digest"] == "sha256:artifact-one"
    assert receipt["human_decision"] is None
    assert receipt["adoption"] is None
    assert all(
        secret not in serialized
        for secret in (
            "prompt-private",
            "resolver-private",
            "nested-private",
            "artifact-private",
            "warning-private",
        )
    )

    decided = build_extension_receipt(
        {
            **task,
            "decision_receipt": {
                "contract_version": "decision-receipt-v1",
                "receipt_id": "decision-receipt:one",
                "decision_id": "decision:one",
            },
        },
        metadata,
        outcome=outcome,
    )
    assert decided["human_decision"]["decision_id"] == "decision:one"
    assert decided["adoption"] is None
    assert decided["outcome"]["data"]["recommendation"] == "Choose A"


def test_outcome_size_limit_is_enforced():
    with pytest.raises(ValidationError, match="bounded serialized size"):
        ExtensionOutcome(
            contract_version="example-outcome-v1",
            data={"content": "x" * 81_000},
        )


def test_missing_or_rejected_reference_keeps_receipt_degraded():
    envelope = _envelope()
    action = registry.RegisteredTaskAction(
        extension_id="example",
        extension_version="1.2.3",
        action="decide",
        prepare=_prepare,
    )
    plan = ExtensionTaskPlan(
        description="Proceed without the missing record",
        context_resolution=[
            ContextResolution(
                reference=envelope.references[0],
                status="missing",
                resolver="example.resolve",
                failure_reason="record_not_found",
            )
        ],
    )
    metadata = invocation_metadata(envelope, plan, action)
    receipt = build_extension_receipt(
        {
            "id": "task:missing",
            "status": "completed",
            "execution": {"state": "complete"},
            "reasoning_trace": {"provenance": {"provider": "fixture", "model": "fixture:model"}},
        },
        metadata,
    )
    assert receipt["coverage"]["state"] == "degraded"
    assert "references_missing" in receipt["coverage"]["missing_or_degraded"]


def test_future_metadata_and_receipt_versions_fail_closed_without_artifacts():
    task = {
        "id": "task:future",
        "status": "completed",
        "extension_invocation": {
            "contract_version": "extension-invocation-v99",
            "request": {"references": [{"id": "secret future reference"}]},
        },
    }
    future_metadata = normalize_extension_receipt(None, task=task)
    assert future_metadata["coverage"]["missing_or_degraded"] == ["unsupported_extension_invocation_version"]
    assert future_metadata["input"]["references"] == []

    envelope = _envelope()
    action = registry.RegisteredTaskAction(
        extension_id="example",
        extension_version="1.2.3",
        action="decide",
        prepare=_prepare,
    )
    task["extension_invocation"] = invocation_metadata(
        envelope,
        _prepare(
            envelope,
            ExtensionActorContext(
                product_id="product:one",
                workspace_id="workspace:default",
                user_id="user:one",
            ),
        ),
        action,
    )
    future_receipt = normalize_extension_receipt(
        {
            "contract_version": "extension-invocation-receipt-v99",
            "outcome": {"private": "future private artifact"},
        },
        task=task,
    )
    assert future_receipt["coverage"]["missing_or_degraded"] == ["unsupported_extension_receipt_version"]
    assert "future private artifact" not in str(future_receipt)
