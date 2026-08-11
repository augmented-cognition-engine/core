"""0.6 kickoff: exact, durable useful/harmful/unproven impact slice."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ace.application import (
    MEASURED_IMPACT_RECORD_SPACE,
    MeasuredImpactError,
    MeasuredImpactReplayConflict,
    MeasuredImpactService,
)
from ace.application.measured_impact import _transaction_key
from ace.core import (
    ActionAdmissionV1Alpha1,
    ActionDisposition,
    ActionEffectState,
    ActionIntentV1Alpha1,
    ActionResultV1Alpha1,
    ActionReversibility,
    ActionReviewDisposition,
    ActionReviewReceiptV1Alpha1,
    ActionTerminalV1Alpha1,
    AppendOnlyTransactionRequestV1,
    AuthenticatedRuntimeContextV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    ContextBindingV1Alpha1,
    ContextUseReceiptV1Alpha1,
    DecisionActionDisposition,
    DecisionDisposition,
    DecisionIntentV1Alpha1,
    DecisionV1Alpha1,
    GovernedActionAuthorizationProjection,
    GovernedOperationBindingV1Alpha1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    ImmutableRecordV1,
    OutcomeIntentV1Alpha1,
    OutcomeV1Alpha1,
    PreparedActionV1Alpha1,
    ReceiptReferenceV1Alpha1,
    canonical_json,
)
from ace.intelligence import (
    ImpactClassification,
    ImpactConditionsV1Alpha1,
    ImpactCriterionV1Alpha1,
    ImpactEvaluationRequestV1Alpha1,
    ImpactEvidenceV1Alpha1,
    ImpactGovernanceAction,
    ImpactGovernanceProposalV1Alpha1,
    ImpactMetricDirection,
    ImpactOutcomeMeasuresV1Alpha1,
    ImpactTargetKind,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

BASE = datetime(2026, 8, 10, 12, tzinfo=UTC)
DECIDED = BASE + timedelta(days=2)
COMPLETED = BASE + timedelta(days=3)
OBSERVED = BASE + timedelta(days=4)
CUTOFF = BASE + timedelta(days=6)
REQUESTED = BASE + timedelta(days=7)
AUTHORIZED = REQUESTED + timedelta(minutes=1)


def _context(product_id: str, actor: str = "operator") -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref=f"principal:{actor}",
        authentication_receipt_ref=f"authentication:{actor}",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=BASE - timedelta(days=1),
        expires_at=BASE + timedelta(days=30),
    )


def _heads(product_id: str, criterion_id: str = "impact_criterion:quality"):
    criterion = GovernedStateHeadV1(
        state_kind="impact_criterion",
        product_id=product_id,
        state_id=criterion_id,
        sequence=1,
        revision_id="impact_criterion_revision:1",
        commit_receipt_id="governed_state_commit:impact-criterion-1",
        updated_at=BASE,
    )
    operation = GovernedStateHeadV1(
        state_kind="governed_operation_configuration",
        product_id=product_id,
        state_id="operation_configuration:measured-impact",
        sequence=1,
        revision_id="operation_configuration_revision:1",
        commit_receipt_id="governed_state_commit:operation-configuration-1",
        updated_at=BASE,
    )
    return criterion, operation


def _binding(product_id: str, operation_head: GovernedStateHeadV1) -> GovernedOperationBindingV1Alpha1:
    return GovernedOperationBindingV1Alpha1(
        product_id=product_id,
        artifact=CapabilityArtifactIdentityV1Alpha1(
            capability="measured_impact_evaluation",
            contract="ace.application.measured-impact-service/v1alpha1",
            implementation_id="core_measured_impact",
            implementation_version="0.1.0",
            artifact_digest="sha256:" + "b" * 64,
        ),
        configuration_ref=operation_head.state_id,
        authority="append_measured_impact",
        grant_ref="authority_grant:append-measured-impact",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(operation_head),
    )


def _projection(product_id: str, *, suffix: str, authorized_at: datetime):
    criterion, operation = _heads(product_id)
    return GovernedActionAuthorizationProjection(
        authorization_ref=ReceiptReferenceV1Alpha1(
            receipt_id=f"authorization:{suffix}",
            receipt_digest="sha256:" + f"{(len(suffix) % 9) + 1}" * 64,
        ),
        authorized_at=authorized_at,
        state_preconditions=(
            GovernedStateHeadPreconditionV1Alpha1.from_head(criterion),
            GovernedStateHeadPreconditionV1Alpha1.from_head(operation),
        ),
    )


class _Authorizer:
    def __init__(self, *, deny: bool = False, expand: bool = False, change_head: bool = False) -> None:
        self.deny = deny
        self.expand = expand
        self.change_head = change_head
        self.requests = []

    async def authorize_action(self, request):
        self.requests.append(request)
        if self.deny:
            raise PermissionError("denied")
        preconditions = list(request.required_state_preconditions)
        if self.change_head:
            preconditions[0] = preconditions[0].model_copy(
                update={
                    "sequence": preconditions[0].sequence + 1,
                    "revision_id": "changed-revision",
                    "commit_receipt_id": "changed-commit",
                }
            )
        if self.expand:
            preconditions.append(
                GovernedStateHeadPreconditionV1Alpha1(
                    state_kind="authority_grant",
                    product_id=request.product_id,
                    state_id="authority_grant:append-measured-impact",
                    sequence=1,
                    revision_id="authority_grant_revision:1",
                    commit_receipt_id="governed_state_commit:authority-grant-1",
                )
            )
        return GovernedActionAuthorizationProjection(
            authorization_ref=ReceiptReferenceV1Alpha1(
                receipt_id="authorization:measured-impact",
                receipt_digest="sha256:" + "9" * 64,
            ),
            authorized_at=AUTHORIZED,
            state_preconditions=tuple(preconditions),
        )


async def _persist(store, record: ImmutableRecordV1) -> None:
    request = AppendOnlyTransactionRequestV1(
        product_id=record.product_id,
        record_space=record.record_space,
        transaction_key=f"seed:{record.storage_id}",
        records=(record,),
        submitted_at=record.available_at,
    )
    assert await store.append(request) == request.receipt()


async def _target(
    store,
    *,
    product_id: str,
    suffix: str,
    target_kind: ImpactTargetKind = ImpactTargetKind.INTELLIGENCE_ARTIFACT,
):
    record = ImmutableRecordV1(
        product_id=product_id,
        record_space="live",
        record_kind=("cognition_revision" if target_kind is ImpactTargetKind.COGNITION_REVISION else "brief"),
        record_key=f"{suffix}:fixture",
        payload_contract="fixture.intelligence-artifact/v1",
        payload={"artifact": suffix},
        as_of=BASE,
        available_at=BASE,
        processing_order=0,
    )
    await _persist(store, record)
    return record.reference()


def _record(value, *, product_id: str, space: str, kind: str, key: str, as_of, available_at):
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=space,
        record_kind=kind,
        record_key=key,
        payload_contract=value.contract,
        payload=value.model_dump(mode="python"),
        as_of=as_of,
        available_at=available_at,
        processing_order=0,
    )


async def _variant(
    store,
    *,
    product_id: str,
    suffix: str,
    target,
    primary_value: float,
    outcome_available_at: datetime | None = None,
    observed_result_available_at: datetime | None = None,
    persist_observed_result: bool = True,
    observed_result_product_id: str | None = None,
):
    context = _context(product_id, suffix)
    use = ContextUseReceiptV1Alpha1(
        product_id=product_id,
        request_id=f"reasoning_request:{suffix}",
        request_digest="sha256:" + "c" * 64,
        result_id=f"reasoning_result:{suffix}",
        result_digest="sha256:" + "d" * 64,
        context=ContextBindingV1Alpha1(
            context_id=f"context:{suffix}",
            context_digest="sha256:" + "e" * 64,
            storage_id=target.storage_id,
            material_digest=target.material_hash,
            as_of=target.as_of,
            available_at=target.available_at,
        ),
        output_referenced=True,
        recorded_at=DECIDED - timedelta(hours=1),
    )
    use_record = _record(
        use,
        product_id=product_id,
        space="reasoning",
        kind="context_use",
        key=str(use.receipt_id),
        as_of=use.recorded_at,
        available_at=use.recorded_at,
    )
    await _persist(store, use_record)

    decision_intent = DecisionIntentV1Alpha1(
        product_id=product_id,
        authenticated_context=context,
        subject=target,
        actor_role_ref="role:analyst",
        decision_type="respond",
        disposition=DecisionDisposition.ACCEPT,
        action_disposition=DecisionActionDisposition.AUTHORIZE_ACTION,
        action_type="record_response",
        rationale="Use the exact evaluated artifact under the frozen product criterion.",
        decided_at=DECIDED,
    )
    decision = DecisionV1Alpha1(
        intent=decision_intent,
        authorization=_projection(
            product_id, suffix=f"decision-{suffix}", authorized_at=DECIDED + timedelta(minutes=1)
        ),
    )
    decision_record = _record(
        decision,
        product_id=product_id,
        space="decision",
        kind="decision",
        key=str(decision.decision_id),
        as_of=DECIDED,
        available_at=DECIDED + timedelta(minutes=1),
    )
    await _persist(store, decision_record)
    decision_ref = decision_record.reference()

    action_intent = ActionIntentV1Alpha1(
        action_key=f"action:{suffix}",
        product_id=product_id,
        authenticated_context=context,
        decision=decision_ref,
        action_type="record_response",
        parameters_json=canonical_json({"variant": suffix}),
        requested_at=DECIDED + timedelta(minutes=2),
    )
    plan = PreparedActionV1Alpha1(
        product_id=product_id,
        intent_id=str(action_intent.intent_id),
        intent_digest=str(action_intent.intent_digest),
        artifact=CapabilityArtifactIdentityV1Alpha1(
            capability="bounded_action_execution",
            contract="ace.core.action-adapter/v1alpha1",
            implementation_id="fixture_action",
            implementation_version="0.1.0",
            artifact_digest="sha256:" + "f" * 64,
        ),
        action_type=action_intent.action_type,
        target_ref=f"target:{suffix}",
        target_digest="sha256:" + "1" * 64,
        required_permissions=("record",),
        declared_side_effects=("append_record",),
        reversibility=ActionReversibility.REVERSIBLE,
        prepared_at=DECIDED + timedelta(minutes=3),
    )
    action_authorization = _projection(
        product_id,
        suffix=f"action-{suffix}",
        authorized_at=DECIDED + timedelta(minutes=4),
    )
    review = ActionReviewReceiptV1Alpha1(
        review_key=f"review:{suffix}",
        product_id=product_id,
        intent=action_intent,
        plan=plan,
        authorization=action_authorization,
        reviewer_context=context,
        disposition=ActionReviewDisposition.APPROVE,
        rationale="Human review approved this exact effect-free plan.",
        reviewed_at=DECIDED + timedelta(minutes=5),
    )
    review_record = _record(
        review,
        product_id=product_id,
        space="action_execution",
        kind="action_review",
        key=str(review.receipt_id),
        as_of=review.reviewed_at,
        available_at=review.reviewed_at,
    )
    await _persist(store, review_record)
    admission = ActionAdmissionV1Alpha1(
        product_id=product_id,
        intent=action_intent,
        plan=plan,
        authorization=action_authorization,
        admitted_at=DECIDED + timedelta(minutes=6),
    )
    admission_record = _record(
        admission,
        product_id=product_id,
        space="action_execution",
        kind="action_admission",
        key=str(admission.receipt_id),
        as_of=admission.admitted_at,
        available_at=admission.admitted_at,
    )
    await _persist(store, admission_record)
    result = ActionResultV1Alpha1(
        disposition=ActionDisposition.SUCCEEDED,
        effect_state=ActionEffectState.CONFIRMED,
        result_json=canonical_json({"recorded": True}),
        completed_at=COMPLETED,
    )
    terminal = ActionTerminalV1Alpha1(
        product_id=product_id,
        action_key=action_intent.action_key,
        admission=admission.reference(),
        result=result,
    )
    terminal_record = _record(
        terminal,
        product_id=product_id,
        space="action_execution",
        kind="action_terminal",
        key=str(terminal.receipt_id),
        as_of=COMPLETED,
        available_at=COMPLETED,
    )
    await _persist(store, terminal_record)

    result_product_id = observed_result_product_id or product_id
    observed_result_record = ImmutableRecordV1(
        product_id=result_product_id,
        record_space="observed_result",
        record_kind="product_review",
        record_key=f"review:{suffix}",
        payload_contract="fixture.product-review/v1",
        payload={"score": primary_value, "subject": target.storage_id},
        as_of=OBSERVED,
        available_at=observed_result_available_at or OBSERVED + timedelta(seconds=30),
        processing_order=0,
    )
    if persist_observed_result:
        await _persist(store, observed_result_record)
    measures = ImpactOutcomeMeasuresV1Alpha1(
        primary_value=primary_value,
        observed_result=observed_result_record.reference(),
        latency_ms=100 if suffix.startswith("treatment") else 120,
        cost_usd=0.01 if suffix.startswith("treatment") else 0.012,
        failure_count=0,
        degraded=False,
    )
    recorded_at = OBSERVED + timedelta(minutes=1)
    outcome = OutcomeV1Alpha1(
        intent=OutcomeIntentV1Alpha1(
            product_id=product_id,
            authenticated_context=context,
            decision=decision_ref,
            outcome_type="quality",
            measure_id="product_quality",
            value_json=canonical_json(measures.model_dump(mode="json")),
            observed_at=OBSERVED,
            recorded_at=recorded_at,
        ),
        authorization=_projection(
            product_id,
            suffix=f"outcome-{suffix}",
            authorized_at=recorded_at + timedelta(minutes=1),
        ),
    )
    outcome_record = _record(
        outcome,
        product_id=product_id,
        space="outcome",
        kind="outcome",
        key=str(outcome.outcome_id),
        as_of=OBSERVED,
        available_at=outcome_available_at or recorded_at + timedelta(minutes=1),
    )
    await _persist(store, outcome_record)
    return {
        "attribution": use_record.reference(),
        "decision": decision_ref,
        "review": review_record.reference(),
        "admission": admission_record.reference(),
        "terminal": terminal_record.reference(),
        "outcome": outcome_record.reference(),
    }


def _conditions(product_id: str, key: str, *, context_json: str = '{"workload":"bounded"}'):
    return ImpactConditionsV1Alpha1(
        product_id=product_id,
        condition_key=key,
        route_id="route:fixed",
        context_json=context_json,
        observation_window_start=BASE + timedelta(days=3),
        observation_window_end=BASE + timedelta(days=5),
        frozen_at=BASE,
    )


async def _scenario(
    *,
    product_id: str,
    treatment_value: float,
    control_value: float,
    missing_treatment_attribution: bool = False,
    mismatch_conditions: bool = False,
    unavailable_treatment_outcome: bool = False,
    late_treatment_outcome: bool = False,
    unavailable_treatment_observed_result: bool = False,
    late_treatment_observed_result: bool = False,
    foreign_treatment_observed_result: bool = False,
    harmful_action: ImpactGovernanceAction = ImpactGovernanceAction.ROLLBACK,
    target_kind: ImpactTargetKind = ImpactTargetKind.INTELLIGENCE_ARTIFACT,
    store=None,
    criterion_head: GovernedStateHeadV1 | None = None,
    operation_head: GovernedStateHeadV1 | None = None,
):
    default_criterion, default_operation = _heads(product_id)
    criterion_head = criterion_head or default_criterion
    operation_head = operation_head or default_operation
    if store is None:
        store = InMemoryImmutableRecordStore(
            governed_state_heads={
                (criterion_head.state_kind, product_id, criterion_head.state_id): criterion_head,
                (operation_head.state_kind, product_id, operation_head.state_id): operation_head,
            }
        )
    target = await _target(store, product_id=product_id, suffix="target", target_kind=target_kind)
    control = await _target(store, product_id=product_id, suffix="control", target_kind=target_kind)
    evidence = []
    for index in range(2):
        treatment = await _variant(
            store,
            product_id=product_id,
            suffix=f"treatment-{index}",
            target=target,
            primary_value=treatment_value,
            outcome_available_at=CUTOFF + timedelta(minutes=1) if late_treatment_outcome else None,
            observed_result_available_at=CUTOFF + timedelta(minutes=1) if late_treatment_observed_result else None,
            persist_observed_result=not unavailable_treatment_observed_result,
            observed_result_product_id="product:foreign" if foreign_treatment_observed_result else None,
        )
        baseline = await _variant(
            store,
            product_id=product_id,
            suffix=f"control-{index}",
            target=control,
            primary_value=control_value,
        )
        matched = _conditions(product_id, f"pair:{index}")
        treatment_outcome = treatment["outcome"]
        treatment_unavailable_reason = None
        if unavailable_treatment_outcome:
            treatment_outcome = None
            treatment_unavailable_reason = "product outcome is not yet available"
        evidence.append(
            ImpactEvidenceV1Alpha1(
                product_id=product_id,
                evidence_key=f"evidence:{index}",
                treatment_attribution=None if missing_treatment_attribution else treatment["attribution"],
                control_attribution=baseline["attribution"],
                treatment_decision=treatment["decision"],
                control_decision=baseline["decision"],
                treatment_action_review=treatment["review"],
                treatment_action_admission=treatment["admission"],
                treatment_action_terminal=treatment["terminal"],
                control_action_review=baseline["review"],
                control_action_admission=baseline["admission"],
                control_action_terminal=baseline["terminal"],
                treatment_outcome=treatment_outcome,
                control_outcome=baseline["outcome"],
                treatment_outcome_unavailable_reason=treatment_unavailable_reason,
                control_outcome_unavailable_reason=None,
                treatment_conditions=matched,
                control_conditions=(
                    _conditions(product_id, f"pair:{index}", context_json='{"workload":"different"}')
                    if mismatch_conditions
                    else matched
                ),
            )
        )
    criterion = ImpactCriterionV1Alpha1(
        product_id=product_id,
        criterion_id=criterion_head.state_id,
        criterion_version="1.0.0",
        target_kind=target_kind,
        outcome_type="quality",
        measure_id="product_quality",
        metric_direction=ImpactMetricDirection.HIGHER_IS_BETTER,
        useful_effect_threshold=0.2,
        harmful_effect_threshold=0.2,
        minimum_matched_pairs=2,
        requires_observed_result=True,
        harmful_action=harmful_action,
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(criterion_head),
        frozen_at=BASE,
    )
    request = ImpactEvaluationRequestV1Alpha1(
        evaluation_key="evaluation:bounded-impact",
        product_id=product_id,
        authenticated_context=_context(product_id),
        criterion=criterion,
        target=target,
        control=control,
        evidence=tuple(evidence),
        cutoff_at=CUTOFF,
        requested_at=REQUESTED,
    )
    authorizer = _Authorizer()
    service = MeasuredImpactService(
        store=store,
        authorizer=authorizer,
        operation_binding=_binding(product_id, operation_head),
    )
    return store, service, request, operation_head


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("treatment", "control", "classification", "action"),
    [
        (1.0, 0.0, ImpactClassification.USEFUL, ImpactGovernanceAction.PROMOTE),
        (0.0, 1.0, ImpactClassification.HARMFUL, ImpactGovernanceAction.ROLLBACK),
        (0.5, 0.5, ImpactClassification.UNPROVEN, None),
    ],
)
async def test_exact_matched_journey_classifies_use_harm_or_unproven(
    treatment,
    control,
    classification,
    action,
) -> None:
    _, service, request, _ = await _scenario(
        product_id=f"product:{classification.value}",
        treatment_value=treatment,
        control_value=control,
    )
    admission = await service.evaluate(request)
    assert admission.evaluation.classification is classification
    assert admission.evaluation.matched_pair_count == 2
    assert admission.evaluation.treatment_mean_latency_ms == 100.0
    assert admission.evaluation.control_mean_latency_ms == 120.0
    assert admission.evaluation.treatment_cost_usd == 0.02
    assert admission.evaluation.control_cost_usd == 0.024
    assert (admission.proposal.action if admission.proposal else None) is action
    if admission.proposal is not None:
        assert admission.proposal.live_effect is False
        assert admission.proposal.selectable is False
        assert admission.proposal.requires_human_review is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_updates", "reason"),
    [
        ({"missing_treatment_attribution": True}, "missing_exact_attribution"),
        ({"mismatch_conditions": True}, "condition_mismatch"),
        ({"unavailable_treatment_outcome": True}, "outcome_unavailable"),
        ({"late_treatment_outcome": True}, "evidence_after_cutoff"),
        ({"unavailable_treatment_observed_result": True}, "observed_result_unavailable"),
        ({"late_treatment_observed_result": True}, "evidence_after_cutoff"),
    ],
)
async def test_unsafe_or_unavailable_evidence_is_explicitly_unproven(scenario_updates, reason) -> None:
    _, service, request, _ = await _scenario(
        product_id=f"product:negative-{reason}",
        treatment_value=1.0,
        control_value=0.0,
        **scenario_updates,
    )
    admission = await service.evaluate(request)
    assert admission.evaluation.classification is ImpactClassification.UNPROVEN
    assert admission.evaluation.matched_pair_count == 0
    assert {item.reasons[0] for item in admission.evaluation.exclusions} == {reason}
    assert admission.proposal is None


@pytest.mark.asyncio
async def test_post_cutoff_evidence_is_excluded_without_loading_its_payload() -> None:
    store, service, request, _ = await _scenario(
        product_id="product:negative-no-leakage",
        treatment_value=1.0,
        control_value=0.0,
        late_treatment_outcome=True,
    )
    future_storage_ids = {
        str(item.treatment_outcome.storage_id)
        for item in request.evidence
        if item.treatment_outcome is not None and item.treatment_outcome.available_at > request.cutoff_at
    }
    loaded_storage_ids: list[str] = []
    load_record = store.load_record

    async def tracked_load_record(storage_id, **scope):
        loaded_storage_ids.append(storage_id)
        return await load_record(storage_id, **scope)

    store.load_record = tracked_load_record
    admission = await service.evaluate(request)

    assert admission.evaluation.classification is ImpactClassification.UNPROVEN
    assert future_storage_ids
    assert future_storage_ids.isdisjoint(loaded_storage_ids)


@pytest.mark.asyncio
async def test_post_cutoff_observed_result_is_excluded_without_loading_its_payload() -> None:
    store, service, request, _ = await _scenario(
        product_id="product:negative-result-no-leakage",
        treatment_value=1.0,
        control_value=0.0,
        late_treatment_observed_result=True,
    )
    treatment_outcome = request.evidence[0].treatment_outcome
    assert treatment_outcome is not None
    outcome_record = await store.load_record(
        treatment_outcome.storage_id,
        product_id=treatment_outcome.product_id,
        record_space=treatment_outcome.record_space,
        record_kind=treatment_outcome.record_kind,
    )
    assert outcome_record is not None
    outcome = OutcomeV1Alpha1.model_validate(outcome_record.payload)
    measures = ImpactOutcomeMeasuresV1Alpha1.model_validate_json(outcome.intent.value_json)
    assert measures.observed_result is not None
    future_result_id = measures.observed_result.storage_id
    loaded_storage_ids: list[str] = []
    load_record = store.load_record

    async def tracked_load_record(storage_id, **scope):
        loaded_storage_ids.append(storage_id)
        return await load_record(storage_id, **scope)

    store.load_record = tracked_load_record
    admission = await service.evaluate(request)

    assert admission.evaluation.classification is ImpactClassification.UNPROVEN
    assert "evidence_after_cutoff" in {reason for item in admission.evaluation.exclusions for reason in item.reasons}
    assert future_result_id not in loaded_storage_ids


@pytest.mark.asyncio
async def test_observed_result_cannot_cross_product_scope() -> None:
    _, service, request, _ = await _scenario(
        product_id="product:negative-result-scope",
        treatment_value=1.0,
        control_value=0.0,
        foreign_treatment_observed_result=True,
    )
    with pytest.raises(MeasuredImpactError, match="observed result crossed exact product scope"):
        await service.evaluate(request)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", [ImpactGovernanceAction.REJECT, ImpactGovernanceAction.RETIRE])
async def test_product_policy_can_propose_rejection_or_retirement_without_applying(action) -> None:
    _, service, request, _ = await _scenario(
        product_id=f"product:{action.value}",
        treatment_value=0.0,
        control_value=1.0,
        harmful_action=action,
    )
    admission = await service.evaluate(request)
    assert admission.evaluation.classification is ImpactClassification.HARMFUL
    assert admission.proposal is not None
    assert admission.proposal.action is action
    assert admission.proposal.live_effect is False
    assert admission.proposal.selectable is False
    assert admission.proposal.requires_human_review is True


@pytest.mark.asyncio
async def test_same_public_slice_evaluates_an_exact_cognition_revision() -> None:
    _, service, request, _ = await _scenario(
        product_id="product:cognition-revision",
        treatment_value=1.0,
        control_value=0.0,
        target_kind=ImpactTargetKind.COGNITION_REVISION,
    )
    admission = await service.evaluate(request)
    assert request.target.record_kind == request.control.record_kind == "cognition_revision"
    assert admission.evaluation.classification is ImpactClassification.USEFUL
    assert admission.proposal is not None
    assert admission.proposal.action is ImpactGovernanceAction.PROMOTE


@pytest.mark.asyncio
async def test_duplicate_replay_restart_and_divergent_material_are_fail_closed() -> None:
    store, service, request, operation_head = await _scenario(
        product_id="product:replay",
        treatment_value=1.0,
        control_value=0.0,
    )
    with pytest.raises(ValidationError, match="duplicate impact evidence identity"):
        ImpactEvaluationRequestV1Alpha1(
            **request.model_dump(mode="python", exclude={"evidence", "request_digest"}),
            evidence=(request.evidence[0], request.evidence[0]),
        )
    relabelled = ImpactEvidenceV1Alpha1.model_validate(
        request.evidence[0]
        .model_copy(update={"evidence_key": "evidence:relabelled", "evidence_id": None, "evidence_digest": None})
        .model_dump(mode="python")
    )
    with pytest.raises(ValidationError, match="duplicate exact impact evidence coordinate"):
        ImpactEvaluationRequestV1Alpha1(
            **request.model_dump(mode="python", exclude={"evidence", "request_digest"}),
            evidence=(request.evidence[0], relabelled),
        )
    first = await service.evaluate(request)
    exact = await service.evaluate(request)
    restarted = await MeasuredImpactService(
        store=store,
        authorizer=_Authorizer(deny=True),
        operation_binding=_binding(request.product_id, operation_head),
    ).evaluate(request)
    assert first.replayed is False
    assert exact.replayed is restarted.replayed is True
    assert first.evaluation == exact.evaluation == restarted.evaluation
    assert first.proposal == exact.proposal == restarted.proposal
    assert first.transaction_receipt == exact.transaction_receipt == restarted.transaction_receipt

    changed_criterion = ImpactCriterionV1Alpha1.model_validate(
        request.criterion.model_copy(update={"useful_effect_threshold": 0.9, "criterion_digest": None}).model_dump(
            mode="python"
        )
    )
    divergent = ImpactEvaluationRequestV1Alpha1.model_validate(
        request.model_copy(update={"criterion": changed_criterion, "request_digest": None}).model_dump(mode="python")
    )
    with pytest.raises(MeasuredImpactReplayConflict, match="different exact request"):
        await service.evaluate(divergent)


@pytest.mark.asyncio
async def test_authority_may_add_stricter_heads_without_changing_frozen_heads() -> None:
    store, _, request, operation_head = await _scenario(
        product_id="product:expanded-authority",
        treatment_value=1.0,
        control_value=0.0,
    )
    store.set_governed_state_head(
        GovernedStateHeadV1(
            state_kind="authority_grant",
            product_id=request.product_id,
            state_id="authority_grant:append-measured-impact",
            sequence=1,
            revision_id="authority_grant_revision:1",
            commit_receipt_id="governed_state_commit:authority-grant-1",
            updated_at=BASE,
        )
    )
    service = MeasuredImpactService(
        store=store,
        authorizer=_Authorizer(expand=True),
        operation_binding=_binding(request.product_id, operation_head),
    )

    admission = await service.evaluate(request)

    assert admission.evaluation.classification is ImpactClassification.USEFUL
    assert len(admission.transaction_receipt.governed_state_preconditions) == 3


@pytest.mark.asyncio
async def test_authority_cannot_replace_a_frozen_head() -> None:
    store, _, request, operation_head = await _scenario(
        product_id="product:changed-authority-head",
        treatment_value=1.0,
        control_value=0.0,
    )
    service = MeasuredImpactService(
        store=store,
        authorizer=_Authorizer(change_head=True),
        operation_binding=_binding(request.product_id, operation_head),
    )

    with pytest.raises(MeasuredImpactError, match="changed the frozen governed heads"):
        await service.evaluate(request)
    assert not any(record.record_space == MEASURED_IMPACT_RECORD_SPACE for record in store.records.values())


@pytest.mark.asyncio
async def test_denied_authority_cannot_append_or_turn_a_proposal_into_effective_state() -> None:
    store, _, request, operation_head = await _scenario(
        product_id="product:denied",
        treatment_value=1.0,
        control_value=0.0,
    )
    denied = MeasuredImpactService(
        store=store,
        authorizer=_Authorizer(deny=True),
        operation_binding=_binding(request.product_id, operation_head),
    )
    with pytest.raises(MeasuredImpactError, match="denied"):
        await denied.evaluate(request)
    assert (
        await store.load_transaction_receipt(
            product_id=request.product_id,
            record_space=MEASURED_IMPACT_RECORD_SPACE,
            transaction_key=_transaction_key(request.evaluation_key),
        )
        is None
    )
    with pytest.raises(ValidationError):
        ImpactGovernanceProposalV1Alpha1(
            product_id=request.product_id,
            evaluation_id="impact_evaluation:fixture",
            evaluation_digest="sha256:" + "1" * 64,
            target=request.target,
            action=ImpactGovernanceAction.PROMOTE,
            rationale="Attempt to bypass review.",
            live_effect=True,
            proposed_at=AUTHORIZED,
        )


@pytest.mark.asyncio
async def test_authorization_after_authentication_expiry_cannot_append() -> None:
    store, service, request, _ = await _scenario(
        product_id="product:expired-authority",
        treatment_value=1.0,
        control_value=0.0,
    )
    expiring_context = AuthenticatedRuntimeContextV1Alpha1.model_validate(
        request.authenticated_context.model_copy(update={"expires_at": REQUESTED + timedelta(seconds=30)}).model_dump(
            mode="python"
        )
    )
    expiring_request = ImpactEvaluationRequestV1Alpha1.model_validate(
        request.model_copy(update={"authenticated_context": expiring_context, "request_digest": None}).model_dump(
            mode="python"
        )
    )

    with pytest.raises(MeasuredImpactError, match="outside the authenticated request window"):
        await service.evaluate(expiring_request)
    assert not any(record.record_space == MEASURED_IMPACT_RECORD_SPACE for record in store.records.values())


@pytest.mark.asyncio
async def test_interrupted_evaluation_and_proposal_append_leaves_no_partial_history() -> None:
    store, service, request, _ = await _scenario(
        product_id="product:atomic-impact",
        treatment_value=1.0,
        control_value=0.0,
    )
    store.fail_after_records = 1

    with pytest.raises(MeasuredImpactError, match="atomic measured-impact append failed"):
        await service.evaluate(request)

    assert not any(record.record_space == MEASURED_IMPACT_RECORD_SPACE for record in store.records.values())
    assert (
        await store.load_transaction_receipt(
            product_id=request.product_id,
            record_space=MEASURED_IMPACT_RECORD_SPACE,
            transaction_key=_transaction_key(request.evaluation_key),
        )
        is None
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_store_fresh_service_reopens_exact_impact_without_reclassification(db_pool) -> None:
    from ace.core import GovernedStateCommitRequestV1, GovernedStateRevisionV1, ResolvedApprovalReceiptV1
    from core.engine.core.governed_state import SurrealGovernedStateStore
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    product_id = f"product:impact-restart-{uuid4().hex}"
    governed = SurrealGovernedStateStore(db_pool)

    async def commit(state_kind: str, state_id: str, index: int) -> GovernedStateHeadV1:
        revision = GovernedStateRevisionV1(
            state_kind=state_kind,
            product_id=product_id,
            state_id=state_id,
            sequence=1,
            revision_id=f"{state_kind}_revision:{uuid4().hex}",
            material_hash=f"{index}" * 64,
            prior_revision_id=None,
            approval_subject_ref=f"{state_kind}:approval-subject",
            payload_contract=f"example.{state_kind}/v1",
            payload={"state_id": state_id},
        )
        await governed.commit(
            GovernedStateCommitRequestV1(
                revision=revision,
                expected_head_revision_id=None,
                actor_ref="principal:operator",
                approval=ResolvedApprovalReceiptV1(
                    receipt_ref=f"approval:{state_kind}",
                    product_id=product_id,
                    subject_ref=revision.approval_subject_ref,
                    actor_ref="principal:operator",
                    receipt_hash="8" * 64,
                    approved_at=BASE,
                ),
                committed_at=BASE + timedelta(minutes=index),
            )
        )
        head = await governed.load_head(state_kind=state_kind, product_id=product_id, state_id=state_id)
        assert head is not None
        return head

    criterion_head = await commit("impact_criterion", "impact_criterion:quality", 1)
    operation_head = await commit(
        "governed_operation_configuration",
        "operation_configuration:measured-impact",
        2,
    )
    durable = SurrealImmutableRecordStore(db_pool)
    _, service, request, _ = await _scenario(
        product_id=product_id,
        treatment_value=1.0,
        control_value=0.0,
        store=durable,
        criterion_head=criterion_head,
        operation_head=operation_head,
    )
    first = await service.evaluate(request)
    reopened = await MeasuredImpactService(
        store=SurrealImmutableRecordStore(db_pool),
        authorizer=_Authorizer(deny=True),
        operation_binding=_binding(product_id, operation_head),
    ).evaluate(request)
    assert reopened.replayed is True
    assert reopened.evaluation == first.evaluation
    assert reopened.proposal == first.proposal
    assert reopened.transaction_receipt == first.transaction_receipt

    script = Path(__file__).with_name("measured_impact_restart_process.py")
    process = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        input=json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "operation_binding": _binding(product_id, operation_head).model_dump(mode="json"),
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stderr or process.stdout
    fresh_process = json.loads(process.stdout.strip().splitlines()[-1])
    assert fresh_process == {
        "evaluation": first.evaluation.model_dump(mode="json"),
        "proposal": first.proposal.model_dump(mode="json") if first.proposal else None,
        "transaction": first.transaction_receipt.model_dump(mode="json"),
    }
