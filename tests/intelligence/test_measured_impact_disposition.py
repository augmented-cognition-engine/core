"""Reviewed, non-applying disposition of one exact measured-impact proposal."""

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
    IMPACT_PROPOSAL_DISPOSITION_DECISION_TYPE,
    MEASURED_IMPACT_RECORD_SPACE,
    MeasuredImpactDispositionError,
    MeasuredImpactDispositionReplayConflict,
    MeasuredImpactDispositionRequestV1Alpha1,
    MeasuredImpactDispositionService,
)
from ace.application.measured_impact_disposition import _transaction_key
from ace.core import (
    AppendOnlyTransactionRequestV1,
    AuthenticatedRuntimeContextV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    DecisionActionDisposition,
    DecisionDisposition,
    GovernedActionAuthorizationProjection,
    GovernedOperationBindingV1Alpha1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    ImmutableRecordV1,
    ReceiptReferenceV1Alpha1,
)
from ace.intelligence import (
    ImpactClassification,
    ImpactCriterionV1Alpha1,
    ImpactEvaluationV1Alpha1,
    ImpactGovernanceAction,
    ImpactGovernanceProposalV1Alpha1,
    ImpactMetricDirection,
    ImpactTargetKind,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

BASE = datetime(2026, 8, 10, 12, tzinfo=UTC)
CUTOFF = BASE + timedelta(days=2)
EVALUATED = BASE + timedelta(days=3)
DECIDED = BASE + timedelta(days=4)
AUTHORIZED = DECIDED + timedelta(minutes=1)


def _context(product_id: str) -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref="principal:impact-reviewer",
        authentication_receipt_ref="authentication:impact-reviewer",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=BASE - timedelta(days=1),
        expires_at=BASE + timedelta(days=30),
    )


def _heads(product_id: str) -> tuple[GovernedStateHeadV1, GovernedStateHeadV1]:
    criterion = GovernedStateHeadV1(
        state_kind="impact_criterion",
        product_id=product_id,
        state_id="impact_criterion:reviewed-quality",
        sequence=1,
        revision_id="impact_criterion_revision:1",
        commit_receipt_id="governed_state_commit:impact-criterion-1",
        updated_at=BASE,
    )
    operation = GovernedStateHeadV1(
        state_kind="governed_operation_configuration",
        product_id=product_id,
        state_id="operation_configuration:measured-impact-disposition",
        sequence=1,
        revision_id="operation_configuration_revision:disposition-1",
        commit_receipt_id="governed_state_commit:disposition-operation-1",
        updated_at=BASE,
    )
    return criterion, operation


def _binding(product_id: str, operation: GovernedStateHeadV1) -> GovernedOperationBindingV1Alpha1:
    return GovernedOperationBindingV1Alpha1(
        product_id=product_id,
        artifact=CapabilityArtifactIdentityV1Alpha1(
            capability="measured_impact_proposal_disposition",
            contract="ace.application.measured-impact-disposition-service/v1alpha1",
            implementation_id="core_measured_impact_disposition",
            implementation_version="0.1.0",
            artifact_digest="sha256:" + "b" * 64,
        ),
        configuration_ref=operation.state_id,
        authority="append_measured_impact_disposition",
        grant_ref="authority_grant:append-measured-impact-disposition",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(operation),
    )


class _Authorizer:
    def __init__(
        self,
        *,
        deny: bool = False,
        change_head: bool = False,
        expand: bool = False,
        authorized_at: datetime = AUTHORIZED,
    ) -> None:
        self.deny = deny
        self.change_head = change_head
        self.expand = expand
        self.authorized_at = authorized_at
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
                    state_id="authority_grant:append-measured-impact-disposition",
                    sequence=1,
                    revision_id="authority_grant_revision:1",
                    commit_receipt_id="governed_state_commit:authority-grant-1",
                )
            )
        return GovernedActionAuthorizationProjection(
            authorization_ref=ReceiptReferenceV1Alpha1(
                receipt_id="authorization:impact-proposal-disposition",
                receipt_digest="sha256:" + "9" * 64,
            ),
            authorized_at=self.authorized_at,
            state_preconditions=tuple(preconditions),
        )


async def _persist(store, *records: ImmutableRecordV1, key: str) -> tuple:
    append = AppendOnlyTransactionRequestV1(
        product_id=records[0].product_id,
        record_space=records[0].record_space,
        transaction_key=key,
        records=records,
        submitted_at=max(item.available_at for item in records),
    )
    assert await store.append(append) == append.receipt()
    return append.receipt().records


async def _scenario(
    *,
    product_id: str = "product:impact-disposition",
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
    target_record = ImmutableRecordV1(
        product_id=product_id,
        record_space="live",
        record_kind="brief",
        record_key="brief:measured-target",
        payload_contract="example.brief/v1",
        payload={"title": "Measured target"},
        as_of=BASE,
        available_at=BASE,
        processing_order=0,
    )
    control_record = ImmutableRecordV1(
        product_id=product_id,
        record_space="live",
        record_kind="brief_control",
        record_key="brief_control:measured-target",
        payload_contract="example.brief-control/v1",
        payload={"title": "Measured control"},
        as_of=BASE,
        available_at=BASE,
        processing_order=0,
    )
    (target,) = await _persist(store, target_record, key="seed:target")
    (control,) = await _persist(store, control_record, key="seed:control")
    criterion = ImpactCriterionV1Alpha1(
        product_id=product_id,
        criterion_id=criterion_head.state_id,
        criterion_version="candidate-1",
        target_kind=ImpactTargetKind.INTELLIGENCE_ARTIFACT,
        outcome_type="review_artifact_quality",
        measure_id="structural_coverage",
        metric_direction=ImpactMetricDirection.HIGHER_IS_BETTER,
        useful_effect_threshold=0.5,
        harmful_effect_threshold=0.5,
        minimum_matched_pairs=2,
        harmful_action=ImpactGovernanceAction.ROLLBACK,
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(criterion_head),
        frozen_at=BASE,
    )
    evaluation = ImpactEvaluationV1Alpha1(
        evaluation_key="measured-impact:reviewed-target",
        request_digest="sha256:" + "c" * 64,
        product_id=product_id,
        criterion=criterion,
        target=target,
        control=control,
        cutoff_at=CUTOFF,
        evaluated_at=EVALUATED,
        classification=ImpactClassification.USEFUL,
        included_evidence_ids=("impact_evidence:1", "impact_evidence:2"),
        exclusions=(),
        matched_pair_count=2,
        mean_effect=1.0,
        confidence_low=1.0,
        confidence_high=1.0,
        treatment_mean=1.0,
        control_mean=0.0,
        treatment_mean_latency_ms=5.0,
        control_mean_latency_ms=5.0,
        treatment_cost_usd=0.0,
        control_cost_usd=0.0,
        treatment_failure_count=0,
        control_failure_count=0,
        treatment_degraded_count=0,
        control_degraded_count=0,
        evidence_hash="sha256:" + "d" * 64,
        reasons=("paired_interval_meets_product_useful_threshold",),
        limitations=("structural_measure_does_not_establish_general_benefit",),
    )
    proposal = ImpactGovernanceProposalV1Alpha1(
        product_id=product_id,
        evaluation_id=str(evaluation.evaluation_id),
        evaluation_digest=str(evaluation.evaluation_digest),
        target=target,
        action=ImpactGovernanceAction.PROMOTE,
        rationale="The exact useful classification maps to promote; separate review is required.",
        proposed_at=EVALUATED,
    )
    evaluation_record = ImmutableRecordV1(
        product_id=product_id,
        record_space=MEASURED_IMPACT_RECORD_SPACE,
        record_kind="impact_evaluation",
        record_key=str(evaluation.evaluation_id),
        payload_contract=evaluation.contract,
        payload=evaluation.model_dump(mode="python"),
        as_of=CUTOFF,
        available_at=EVALUATED,
        processing_order=0,
    )
    proposal_record = ImmutableRecordV1(
        product_id=product_id,
        record_space=MEASURED_IMPACT_RECORD_SPACE,
        record_kind="impact_governance_proposal",
        record_key=str(proposal.proposal_id),
        payload_contract=proposal.contract,
        payload=proposal.model_dump(mode="python"),
        as_of=CUTOFF,
        available_at=EVALUATED,
        processing_order=1,
    )
    evaluation_ref, proposal_ref = await _persist(
        store,
        evaluation_record,
        proposal_record,
        key="seed:measured-impact",
    )
    request = MeasuredImpactDispositionRequestV1Alpha1(
        product_id=product_id,
        authenticated_context=_context(product_id),
        evaluation=evaluation_ref,
        proposal=proposal_ref,
        reviewer_role_ref="role:measured-impact-governor",
        disposition=DecisionDisposition.REJECT,
        rationale=(
            "Reject broader promotion: this useful classification proves only exact structural "
            "coverage under the frozen criterion, not general human benefit."
        ),
        decided_at=DECIDED,
    )
    binding = _binding(product_id, operation_head)
    return store, request, binding, criterion_head, operation_head, evaluation


@pytest.mark.asyncio
@pytest.mark.parametrize("disposition", [DecisionDisposition.ACCEPT, DecisionDisposition.REJECT])
async def test_reviewed_disposition_is_an_exact_no_action_decision(disposition: DecisionDisposition) -> None:
    store, request, binding, _, _, _ = await _scenario(product_id=f"product:review-{disposition.value}")
    request = MeasuredImpactDispositionRequestV1Alpha1.model_validate(
        request.model_copy(update={"disposition": disposition}).model_dump(mode="python")
    )
    heads_before = dict(store.governed_state_heads)

    admission = await MeasuredImpactDispositionService(
        store=store,
        authorizer=_Authorizer(),
        operation_binding=binding,
    ).decide(request)

    assert admission.replayed is False
    assert admission.decision.intent.subject == request.proposal
    assert admission.decision.intent.decision_type == IMPACT_PROPOSAL_DISPOSITION_DECISION_TYPE
    assert admission.decision.intent.disposition is disposition
    assert admission.decision.intent.action_disposition is DecisionActionDisposition.NO_ACTION
    assert admission.decision.intent.action_type is None
    assert store.governed_state_heads == heads_before


@pytest.mark.asyncio
async def test_exact_replay_survives_head_advance_without_reauthorization() -> None:
    store, request, binding, criterion_head, _, _ = await _scenario()
    first = await MeasuredImpactDispositionService(
        store=store,
        authorizer=_Authorizer(),
        operation_binding=binding,
    ).decide(request)
    store.set_governed_state_head(
        criterion_head.model_copy(
            update={
                "sequence": 2,
                "revision_id": "impact_criterion_revision:2",
                "commit_receipt_id": "governed_state_commit:impact-criterion-2",
                "updated_at": DECIDED,
            }
        )
    )
    denied = _Authorizer(deny=True)

    replay = await MeasuredImpactDispositionService(
        store=store,
        authorizer=denied,
        operation_binding=binding,
    ).decide(request)

    assert replay.replayed is True
    assert replay.decision == first.decision
    assert replay.transaction_receipt == first.transaction_receipt
    assert denied.requests == []


@pytest.mark.asyncio
async def test_contradictory_second_disposition_conflicts_instead_of_rewriting_history() -> None:
    store, request, binding, _, _, _ = await _scenario()
    service = MeasuredImpactDispositionService(
        store=store,
        authorizer=_Authorizer(),
        operation_binding=binding,
    )
    await service.decide(request)
    contradictory = MeasuredImpactDispositionRequestV1Alpha1.model_validate(
        request.model_copy(
            update={
                "disposition": DecisionDisposition.ACCEPT,
                "rationale": "Attempt to replace the exact rejected disposition.",
            }
        ).model_dump(mode="python")
    )

    with pytest.raises(MeasuredImpactDispositionReplayConflict, match="different disposition"):
        await service.decide(contradictory)


@pytest.mark.asyncio
async def test_mismatched_evaluation_and_proposal_fail_before_authorization() -> None:
    store, request, binding, _, _, evaluation = await _scenario()
    changed_evaluation = ImpactEvaluationV1Alpha1.model_validate(
        evaluation.model_copy(
            update={
                "evaluation_key": "measured-impact:different-evaluation",
                "request_digest": "sha256:" + "e" * 64,
                "evaluation_id": None,
                "evaluation_digest": None,
            }
        ).model_dump(mode="python")
    )
    changed_record = ImmutableRecordV1(
        product_id=request.product_id,
        record_space=MEASURED_IMPACT_RECORD_SPACE,
        record_kind="impact_evaluation",
        record_key=str(changed_evaluation.evaluation_id),
        payload_contract=changed_evaluation.contract,
        payload=changed_evaluation.model_dump(mode="python"),
        as_of=CUTOFF,
        available_at=EVALUATED,
        processing_order=0,
    )
    (changed_ref,) = await _persist(store, changed_record, key="seed:different-evaluation")
    mismatched = MeasuredImpactDispositionRequestV1Alpha1.model_validate(
        request.model_copy(update={"evaluation": changed_ref}).model_dump(mode="python")
    )
    authorizer = _Authorizer()

    with pytest.raises(MeasuredImpactDispositionError, match="did not bind the exact evaluation"):
        await MeasuredImpactDispositionService(
            store=store,
            authorizer=authorizer,
            operation_binding=binding,
        ).decide(mismatched)
    assert authorizer.requests == []


@pytest.mark.asyncio
async def test_denied_or_changed_authority_appends_no_disposition() -> None:
    for suffix, authorizer, error in (
        ("denied", _Authorizer(deny=True), "denied"),
        ("changed", _Authorizer(change_head=True), "changed the frozen governed heads"),
    ):
        store, request, binding, _, _, _ = await _scenario(product_id=f"product:{suffix}")
        with pytest.raises(MeasuredImpactDispositionError, match=error):
            await MeasuredImpactDispositionService(
                store=store,
                authorizer=authorizer,
                operation_binding=binding,
            ).decide(request)
        assert (
            await store.load_transaction_receipt(
                product_id=request.product_id,
                record_space=MEASURED_IMPACT_RECORD_SPACE,
                transaction_key=_transaction_key(request.proposal),
            )
            is None
        )


@pytest.mark.asyncio
async def test_stale_criterion_head_fails_at_atomic_append() -> None:
    store, request, binding, criterion_head, _, _ = await _scenario()
    store.set_governed_state_head(
        criterion_head.model_copy(
            update={
                "sequence": 2,
                "revision_id": "impact_criterion_revision:2",
                "commit_receipt_id": "governed_state_commit:impact-criterion-2",
                "updated_at": DECIDED,
            }
        )
    )

    with pytest.raises(MeasuredImpactDispositionError, match="append failed closed"):
        await MeasuredImpactDispositionService(
            store=store,
            authorizer=_Authorizer(),
            operation_binding=binding,
        ).decide(request)


@pytest.mark.asyncio
async def test_stricter_authority_closure_is_preserved_when_current() -> None:
    store, request, binding, _, _, _ = await _scenario()
    authority_head = GovernedStateHeadV1(
        state_kind="authority_grant",
        product_id=request.product_id,
        state_id="authority_grant:append-measured-impact-disposition",
        sequence=1,
        revision_id="authority_grant_revision:1",
        commit_receipt_id="governed_state_commit:authority-grant-1",
        updated_at=BASE,
    )
    store.set_governed_state_head(authority_head)

    admission = await MeasuredImpactDispositionService(
        store=store,
        authorizer=_Authorizer(expand=True),
        operation_binding=binding,
    ).decide(request)

    assert len(admission.transaction_receipt.governed_state_preconditions) == 3


def test_cross_product_or_revise_disposition_fails_contract_validation() -> None:
    # Build valid material synchronously from immutable references is covered by
    # every async scenario; these copies isolate request-level fail-closed rules.
    product_id = "product:validation"
    context = _context(product_id)
    target = ImmutableRecordV1(
        product_id=product_id,
        record_space=MEASURED_IMPACT_RECORD_SPACE,
        record_kind="impact_evaluation",
        record_key="impact_evaluation:fixture",
        payload_contract="ace.intelligence.impact-evaluation/v1alpha1",
        payload={"fixture": True},
        as_of=CUTOFF,
        available_at=EVALUATED,
        processing_order=0,
    ).reference()
    proposal = ImmutableRecordV1(
        product_id=product_id,
        record_space=MEASURED_IMPACT_RECORD_SPACE,
        record_kind="impact_governance_proposal",
        record_key="impact_governance_proposal:fixture",
        payload_contract="ace.intelligence.impact-governance-proposal/v1alpha1",
        payload={"fixture": True},
        as_of=CUTOFF,
        available_at=EVALUATED,
        processing_order=1,
    ).reference()
    with pytest.raises(ValidationError, match="accept or reject"):
        MeasuredImpactDispositionRequestV1Alpha1(
            product_id=product_id,
            authenticated_context=context,
            evaluation=target,
            proposal=proposal,
            reviewer_role_ref="role:reviewer",
            disposition=DecisionDisposition.REVISE,
            rationale="Revision is not a final proposal disposition.",
            decided_at=DECIDED,
        )
    with pytest.raises(ValidationError, match="product scope"):
        MeasuredImpactDispositionRequestV1Alpha1(
            product_id="product:other",
            authenticated_context=context,
            evaluation=target,
            proposal=proposal,
            reviewer_role_ref="role:reviewer",
            disposition=DecisionDisposition.REJECT,
            rationale="Cross-product review is forbidden.",
            decided_at=DECIDED,
        )


@pytest.mark.asyncio
async def test_interrupted_disposition_append_leaves_no_partial_decision() -> None:
    store, request, binding, _, _, _ = await _scenario()
    store.fail_after_records = 1

    with pytest.raises(MeasuredImpactDispositionError, match="append failed closed"):
        await MeasuredImpactDispositionService(
            store=store,
            authorizer=_Authorizer(),
            operation_binding=binding,
        ).decide(request)
    assert not any(record.record_kind == "decision" for record in store.records.values())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_store_and_fresh_process_reopen_exact_disposition_without_authority(db_pool) -> None:
    from ace.core import GovernedStateCommitRequestV1, GovernedStateRevisionV1, ResolvedApprovalReceiptV1
    from core.engine.core.governed_state import SurrealGovernedStateStore
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    product_id = f"product:impact-disposition-restart-{uuid4().hex}"
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

    criterion_head = await commit("impact_criterion", "impact_criterion:reviewed-quality", 1)
    operation_head = await commit(
        "governed_operation_configuration",
        "operation_configuration:measured-impact-disposition",
        2,
    )
    durable = SurrealImmutableRecordStore(db_pool)
    _, request, binding, _, _, _ = await _scenario(
        product_id=product_id,
        store=durable,
        criterion_head=criterion_head,
        operation_head=operation_head,
    )
    first = await MeasuredImpactDispositionService(
        store=durable,
        authorizer=_Authorizer(),
        operation_binding=binding,
    ).decide(request)
    reopened = await MeasuredImpactDispositionService(
        store=SurrealImmutableRecordStore(db_pool),
        authorizer=_Authorizer(deny=True),
        operation_binding=binding,
    ).decide(request)
    assert reopened.replayed is True
    assert reopened.decision == first.decision
    assert reopened.transaction_receipt == first.transaction_receipt

    script = Path(__file__).with_name("measured_impact_disposition_restart_process.py")
    process = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        input=json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "operation_binding": binding.model_dump(mode="json"),
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stderr or process.stdout
    assert json.loads(process.stdout.strip().splitlines()[-1]) == {
        "decision": first.decision.model_dump(mode="json"),
        "transaction": first.transaction_receipt.model_dump(mode="json"),
    }
