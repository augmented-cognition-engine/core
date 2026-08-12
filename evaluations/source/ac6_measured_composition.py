"""Provider-free deterministic AC6 matched-composition evaluation fixture."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ace.application.measured_composition import (
    CompositionEvaluationAuthorityResolutionV1Alpha1,
    MeasuredCompositionEvaluationService,
    evaluation_authority_reference,
)
from ace.core.agent_composition import CompositionBudgetV1Alpha1, ExactArtifactReferenceV1Alpha1
from ace.core.contracts import canonical_hash
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.measured_composition import (
    CompositionConditionAssignmentV1Alpha1,
    CompositionConditionPlanV1Alpha1,
    CompositionEvaluationCondition,
    CompositionEvaluationDeviationV1Alpha1,
    CompositionEvaluationFailure,
    CompositionEvaluationProtocolV1Alpha1,
    CompositionHeldConstantsV1Alpha1,
    CompositionMaterialityThresholdsV1Alpha1,
    CompositionMaterialUseV1Alpha1,
    CompositionRunMetricsV1Alpha1,
    CompositionRunObservationV1Alpha1,
    OutcomeAvailability,
    TelemetryAvailability,
    measured_composition_reference,
)
from ace.testing.immutable_records import InMemoryImmutableRecordStore

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "ac6_measured_composition_conformance_v1.json"
BASE = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)


def _ref(key: str, contract: str) -> ExactArtifactReferenceV1Alpha1:
    return ExactArtifactReferenceV1Alpha1(
        artifact_id=key,
        artifact_digest=f"sha256:{canonical_hash([key, contract])}",
        artifact_contract=contract,
    )


def _head(*, kind: str, state_id: str, product_id: str) -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind=kind,
        product_id=product_id,
        state_id=state_id,
        sequence=1,
        revision_id=f"{kind}_revision:ac6-1",
        commit_receipt_id=f"governed_state_commit:{kind}-ac6-1",
        updated_at=BASE - timedelta(minutes=1),
    )


def _build_authority(product_id: str):
    actor = "principal:ac6-evaluator"
    grant = _head(kind="authority_grant", state_id="grant:evaluate-agent-composition", product_id=product_id)
    configuration = _head(
        kind="composition_evaluation_configuration",
        state_id="configuration:ac6-evaluation-v1",
        product_id=product_id,
    )
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref=actor,
        authentication_receipt_ref="authentication:ac6-provider-free",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=BASE - timedelta(minutes=5),
        expires_at=BASE + timedelta(days=1),
    )
    subject_digest = f"sha256:{canonical_hash(['ac6-preregistration', product_id])}"
    authority_use = AuthorityUseReceiptV1Alpha1(
        product_id=product_id,
        actor_ref=actor,
        authenticated_context=context,
        use_subject_ref="composition_evaluation_preregistration:ac6-v1",
        use_subject_digest=subject_digest,
        operation="evaluate_agent_composition",
        authority="evaluate_agent_composition",
        grant_ref=grant.state_id,
        grant_hash="b" * 64,
        evaluated_at=BASE,
        expires_at=context.expires_at,
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(grant),
    )
    heads = tuple(
        sorted(
            (
                GovernedStateHeadPreconditionV1Alpha1.from_head(grant),
                GovernedStateHeadPreconditionV1Alpha1.from_head(configuration),
            ),
            key=lambda item: item.state_kind,
        )
    )
    authority = CompositionEvaluationAuthorityResolutionV1Alpha1(
        product_id=product_id,
        actor_ref=actor,
        authenticated_context=context,
        authority_use=authority_use,
        current_heads=heads,
        evaluated_at=BASE,
    )
    return authority, (grant, configuration)


def _build_protocol(fixture: dict, authority) -> CompositionEvaluationProtocolV1Alpha1:
    config = fixture["protocol"]
    held = config["held_constants"]
    return CompositionEvaluationProtocolV1Alpha1(
        product_id=fixture["product_id"],
        protocol_key="ac6-measured-composition-v1",
        task_inputs=(_ref("task:ac6-exact-input", "ace.evaluation.fixture-task/v1"),),
        evidence_inputs=(_ref("evidence:ac6-exact-input", "ace.evaluation.fixture-evidence/v1"),),
        context_inputs=(_ref("context:ac6-exact-input", "ace.evaluation.fixture-context/v1"),),
        admissible_output_contracts=(config["admissible_output_contract"],),
        evidence_closure_criteria=tuple(config["evidence_closure_criteria"]),
        material_use_criteria=tuple(config["material_use_criteria"]),
        conditions=tuple(CompositionEvaluationCondition),
        held_constants=CompositionHeldConstantsV1Alpha1(
            provider_ref=held["provider_ref"],
            model_ref=held["model_ref"],
            model_version_ref=held["model_version_ref"],
            randomness_seed=held["randomness_seed"],
            time_assumption_ref=held["time_assumption_ref"],
            authority_scope_ref=held["authority_scope_ref"],
            destination_policy_ref=held["destination_policy_ref"],
            budget=CompositionBudgetV1Alpha1(**held["budget"]),
        ),
        thresholds=CompositionMaterialityThresholdsV1Alpha1(**config["thresholds"]),
        failure_taxonomy=tuple(CompositionEvaluationFailure),
        evaluation_authority=evaluation_authority_reference(authority),
        current_governed_heads=authority.current_heads,
        preregistered_at=BASE + timedelta(seconds=1),
    )


def _participants(condition: CompositionEvaluationCondition) -> tuple[str, ...]:
    if condition is CompositionEvaluationCondition.FIXED_MINIMAL:
        return ("service:deterministic-primary",)
    if condition is CompositionEvaluationCondition.FIXED_MULTI:
        return ("service:deterministic-primary", "service:deterministic-reviewer")
    return ("service:deterministic-primary", "service:deterministic-specialist")


def _build_assignment(
    protocol: CompositionEvaluationProtocolV1Alpha1,
    *,
    case_id: str,
    assigned_at: datetime,
) -> CompositionConditionAssignmentV1Alpha1:
    return CompositionConditionAssignmentV1Alpha1(
        product_id=protocol.product_id,
        protocol=measured_composition_reference(protocol),
        pair_key=f"matched-pair:{case_id}",
        task_inputs=protocol.task_inputs,
        evidence_inputs=protocol.evidence_inputs,
        context_inputs=protocol.context_inputs,
        condition_plans=tuple(
            CompositionConditionPlanV1Alpha1(
                condition=condition,
                composition_plan=_ref(
                    f"task_composition_plan:{case_id}:{condition.value}",
                    "ace.core.task-composition-plan/v1alpha1",
                ),
                participant_refs=_participants(condition),
                composition_policy_ref=f"composition_policy:ac6-{condition.value}-control-v1",
            )
            for condition in CompositionEvaluationCondition
        ),
        held_constants=protocol.held_constants,
        assigned_at=assigned_at,
    )


def _metrics(fixture: dict, case: dict, condition: CompositionEvaluationCondition) -> dict:
    values = deepcopy(fixture["default_metrics"][condition.value])
    values.update(case.get("overrides", {}).get(condition.value, {}))
    if condition is CompositionEvaluationCondition.DYNAMIC and "dynamic_failure" in case:
        failure = case["dynamic_failure"]
        values.update({key: value for key, value in failure.items() if key not in {"deviation", "disqualifies_pair"}})
    return values


def _build_observation(
    fixture: dict,
    protocol: CompositionEvaluationProtocolV1Alpha1,
    assignment: CompositionConditionAssignmentV1Alpha1,
    case: dict,
    condition: CompositionEvaluationCondition,
    *,
    observed_at: datetime,
) -> CompositionRunObservationV1Alpha1:
    raw = _metrics(fixture, case, condition)
    participant_count = int(raw["material_participant_count"])
    final_output = _ref(
        f"fixture_output:{case['case_id']}:{condition.value}:final",
        fixture["protocol"]["admissible_output_contract"],
    )
    participant_outputs = tuple(
        _ref(
            f"fixture_output:{case['case_id']}:{condition.value}:participant-{index}",
            fixture["protocol"]["admissible_output_contract"],
        )
        for index in range(participant_count)
    )
    participants = _participants(condition)
    material_uses = tuple(
        CompositionMaterialUseV1Alpha1(
            participant_ref=participants[index],
            participant_output=participant_output,
            final_output=final_output,
            use_kind="structurally_incorporated",
        )
        for index, participant_output in enumerate(participant_outputs)
    )
    failure = case.get("dynamic_failure") if condition is CompositionEvaluationCondition.DYNAMIC else None
    deviations = ()
    if failure is not None:
        deviations = (
            CompositionEvaluationDeviationV1Alpha1(
                code=failure["deviation"],
                detail=f"Frozen deterministic observation for {case['case_id']}.",
                disqualifies_pair=failure.get("disqualifies_pair", True),
            ),
        )
    metrics = CompositionRunMetricsV1Alpha1(
        valid_completion=raw["valid_completion"],
        evidence_closure_bps=raw["evidence_closure_bps"],
        material_participant_count=participant_count,
        outcome_availability=OutcomeAvailability(raw["outcome_availability"]),
        bounded_outcome_value=raw["bounded_outcome_value"],
        latency_ms=raw["latency_ms"],
        model_calls=raw["model_calls"],
        tool_calls=raw["tool_calls"],
        token_telemetry=TelemetryAvailability(raw["token_telemetry"]),
        tokens=raw["tokens"],
        cost_telemetry=TelemetryAvailability(raw["cost_telemetry"]),
        cost_microunits=raw["cost_microunits"],
        failures=tuple(CompositionEvaluationFailure(item) for item in raw.get("failures", ())),
        timeouts=raw.get("timeouts", 0),
        abstentions=raw.get("abstentions", 0),
        partial_joins=raw.get("partial_joins", 0),
        tainted_joins=raw.get("tainted_joins", 0),
        authority_denials=raw.get("authority_denials", 0),
        destination_denials=raw.get("destination_denials", 0),
        effect_denials=raw.get("effect_denials", 0),
        retries=raw.get("retries", 0),
        duplicate_effects_prevented=raw.get("duplicate_effects_prevented", 0),
    )
    return CompositionRunObservationV1Alpha1(
        product_id=protocol.product_id,
        protocol=measured_composition_reference(protocol),
        assignment=measured_composition_reference(assignment),
        pair_key=assignment.pair_key,
        condition=condition,
        invocation=_ref(
            f"stage_run_manifest:{case['case_id']}:{condition.value}",
            "ace.core.stage-run-manifest/v1alpha1",
        ),
        run_receipts=(
            _ref(
                f"stage_run_receipt:{case['case_id']}:{condition.value}",
                "ace.core.stage-run-receipt/v1alpha1",
            ),
        ),
        authority_resolutions=(
            _ref(
                f"composition_authority_resolution:{case['case_id']}:{condition.value}",
                "ace.application.composition-authority-resolution/v1alpha1",
            ),
        ),
        output_artifacts=(*participant_outputs, final_output),
        cited_evidence=protocol.evidence_inputs if raw["evidence_closure_bps"] else (),
        material_uses=material_uses,
        metrics=metrics,
        deviations=deviations,
        observed_at=observed_at,
    )


async def run_provider_free_fixture() -> dict:
    fixture = json.loads(FIXTURE_PATH.read_text())
    authority, heads = _build_authority(fixture["product_id"])
    store = InMemoryImmutableRecordStore(
        governed_state_heads={(item.state_kind, item.product_id, item.state_id): item for item in heads}
    )
    service = MeasuredCompositionEvaluationService(store=store)
    protocol = _build_protocol(fixture, authority)
    preregistration = await service.preregister(authority=authority, protocol=protocol)
    current_policy = _ref("composition_policy:ac6-current-v1", "ace.governance.composition-policy/v1")
    results = []
    replay_identical = False
    for index, case in enumerate(fixture["cases"], start=1):
        assigned_at = BASE + timedelta(minutes=index)
        assignment = _build_assignment(protocol, case_id=case["case_id"], assigned_at=assigned_at)
        await service.assign(assignment)
        observations = tuple(
            _build_observation(
                fixture,
                protocol,
                assignment,
                case,
                condition,
                observed_at=assigned_at + timedelta(seconds=condition_index + 1),
            )
            for condition_index, condition in enumerate(CompositionEvaluationCondition)
        )
        observation_refs = tuple([await service.observe(item) for item in observations])
        compared_at = assigned_at + timedelta(seconds=10)
        closure = await service.close(
            product_id=protocol.product_id,
            protocol_ref=measured_composition_reference(protocol),
            assignment_ref=measured_composition_reference(assignment),
            observation_refs=tuple(measured_composition_reference(item) for item in observations),
            current_policy=current_policy,
            proposed_policy_rule_ref="composition_policy_rule:dynamic-only-for-exact-ac6-scope",
            compared_at=compared_at,
        )
        assert closure.comparison.disposition.value == case["expected"]
        assert (closure.proposal is not None) is bool(case.get("proposal", False))
        results.append(
            {
                "case_id": case["case_id"],
                "disposition": closure.comparison.disposition.value,
                "paired_and_controlled": closure.comparison.paired_and_controlled,
                "comparison_id": closure.comparison.comparison_id,
                "comparison_digest": closure.comparison.comparison_digest,
                "proposal_id": closure.proposal.proposal_id if closure.proposal is not None else None,
                "proposal_digest": closure.proposal.proposal_digest if closure.proposal is not None else None,
                "observation_records": len(observation_refs),
            }
        )
        if case["case_id"] == "dynamic_helps":
            restarted = MeasuredCompositionEvaluationService(store=store)
            replay = await restarted.close(
                product_id=protocol.product_id,
                protocol_ref=measured_composition_reference(protocol),
                assignment_ref=measured_composition_reference(assignment),
                observation_refs=tuple(measured_composition_reference(item) for item in observations),
                current_policy=current_policy,
                proposed_policy_rule_ref="composition_policy_rule:dynamic-only-for-exact-ac6-scope",
                compared_at=compared_at,
            )
            replay_identical = replay == closure and replay.transaction_receipt == closure.transaction_receipt
    proposals = [item for item in results if item["proposal_id"] is not None]
    return {
        "fixture_contract": fixture["contract"],
        "protocol_id": protocol.protocol_id,
        "protocol_digest": protocol.protocol_digest,
        "authority_id": authority.resolution_id,
        "authority_digest": authority.resolution_digest,
        "preregistration_receipt_id": preregistration.transaction_receipt.receipt_id,
        "condition_count": len(CompositionEvaluationCondition),
        "case_count": len(results),
        "proposal_count": len(proposals),
        "restart_replay_identical": replay_identical,
        "network_used": False,
        "provider_credentials_used": False,
        "results": results,
    }


__all__ = ["FIXTURE_PATH", "run_provider_free_fixture"]
