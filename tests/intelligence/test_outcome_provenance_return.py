from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from ace.application.decision_feedback import (
    PREPARED_FEEDBACK_RECORD_SPACE,
    PreparedDecisionFeedbackError,
    PreparedDecisionFeedbackService,
)
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    DecisionActionDisposition,
    DecisionDisposition,
    DecisionIntentV1Alpha1,
    DecisionV1Alpha1,
    GovernedActionAuthorizationProjection,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    ImmutableRecordV1,
    OutcomeIntentV1Alpha1,
    ReceiptReferenceV1Alpha1,
)
from ace.intelligence import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
    OutcomeProvenanceReturnV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

PRODUCT = "product:consumer-provenance"
NOW = datetime(2026, 8, 15, 16, tzinfo=UTC)


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref="principal:consumer",
        authentication_receipt_ref="authentication:consumer",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _precondition(kind: str) -> GovernedStateHeadPreconditionV1Alpha1:
    return GovernedStateHeadPreconditionV1Alpha1(
        state_kind=kind,
        product_id=PRODUCT,
        state_id=f"{kind}:consumer-provenance",
        sequence=1,
        revision_id=f"revision:{kind}:1",
        commit_receipt_id=f"commit:{kind}:1",
    )


def _authorization(at: datetime) -> GovernedActionAuthorizationProjection:
    return GovernedActionAuthorizationProjection(
        authorization_ref=ReceiptReferenceV1Alpha1(
            receipt_id="authorization:consumer-outcome",
            receipt_digest="sha256:" + "b" * 64,
        ),
        authorized_at=at,
        state_preconditions=(_precondition("activation"), _precondition("authority_grant")),
    )


def _consumed_reference(*, product_id: str = PRODUCT) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=product_id,
        resource_kind=IntelligenceResourceKind.BRIEF,
        resource_id="brief:" + "c" * 32,
        resource_digest="sha256:" + "c" * 64,
        resource_contract="ace.intelligence.brief/v1alpha1",
        revision=3,
        as_of=NOW + timedelta(minutes=1),
        available_at=NOW + timedelta(minutes=2),
    )


def _subject_record() -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=PRODUCT,
        record_space=PREPARED_FEEDBACK_RECORD_SPACE,
        record_kind="brief",
        record_key="brief:" + "c" * 32,
        payload_contract="ace.intelligence.brief/v1alpha1",
        payload={"contract": "ace.intelligence.brief/v1alpha1"},
        as_of=NOW + timedelta(minutes=1),
        available_at=NOW + timedelta(minutes=2),
        processing_order=0,
    )


def _decision_record() -> ImmutableRecordV1:
    decision = DecisionV1Alpha1(
        intent=DecisionIntentV1Alpha1(
            product_id=PRODUCT,
            authenticated_context=_context(),
            subject=_subject_record().reference(),
            actor_role_ref="consumer_persona",
            decision_type="consumer_review",
            disposition=DecisionDisposition.ACCEPT,
            action_disposition=DecisionActionDisposition.NO_ACTION,
            rationale="The cited intelligence supported this bounded review.",
            decided_at=NOW + timedelta(minutes=5),
        ),
        authorization=_authorization(NOW + timedelta(minutes=6)),
    )
    return ImmutableRecordV1(
        product_id=PRODUCT,
        record_space=PREPARED_FEEDBACK_RECORD_SPACE,
        record_kind="decision",
        record_key=str(decision.decision_id),
        payload_contract=decision.contract,
        payload=decision.model_dump(mode="python"),
        as_of=decision.intent.decided_at,
        available_at=decision.authorization.authorized_at,
        processing_order=0,
    )


def _outcome_intent(decision: ImmutableRecordV1) -> OutcomeIntentV1Alpha1:
    return OutcomeIntentV1Alpha1(
        product_id=PRODUCT,
        authenticated_context=_context(),
        decision=decision.reference(),
        outcome_type="consumer_usefulness",
        measure_id="usefulness",
        value_json='"useful"',
        observed_at=NOW + timedelta(minutes=7),
        recorded_at=NOW + timedelta(minutes=8),
    )


class _Resources:
    def __init__(self, record: IntelligenceResourceRecordV1Alpha1) -> None:
        self.record = record

    async def load_exact(self, reference, *, evaluated_at):
        if evaluated_at < self.record.reference.available_at or reference != self.record.reference:
            return None
        return self.record


class _Harness(PreparedDecisionFeedbackService):
    def __init__(self, *, store, resources) -> None:
        self.record_store = store
        self.intelligence_resources = resources

    @property
    def product_id(self) -> str:
        return PRODUCT

    def _policy(self, policy_id: str):
        assert policy_id == "consumer_usefulness"
        return SimpleNamespace(
            policy=SimpleNamespace(
                persona_id="consumer_persona",
                decision_type="consumer_review",
                eligible_decision_dispositions=(DecisionDisposition.ACCEPT,),
                eligible_action_dispositions=(DecisionActionDisposition.NO_ACTION,),
                outcome_type="consumer_usefulness",
                measure_id="usefulness",
            )
        )

    async def _authorize(self, **kwargs):
        assert kwargs["operation"] == "record_outcome"
        return _authorization(NOW + timedelta(minutes=9))


def _store(decision: ImmutableRecordV1) -> InMemoryImmutableRecordStore:
    heads = {}
    for item in _authorization(NOW + timedelta(minutes=9)).state_preconditions:
        heads[(item.state_kind, item.product_id, item.state_id)] = GovernedStateHeadV1(
            state_kind=item.state_kind,
            product_id=item.product_id,
            state_id=item.state_id,
            sequence=item.sequence,
            revision_id=item.revision_id,
            commit_receipt_id=item.commit_receipt_id,
            updated_at=NOW,
        )
    store = InMemoryImmutableRecordStore(governed_state_heads=heads)
    store.records[str(decision.storage_id)] = decision
    return store


@pytest.mark.asyncio
async def test_outcome_atomically_returns_exact_consumed_intelligence_and_replays() -> None:
    consumed = _consumed_reference()
    projected = IntelligenceResourceRecordV1Alpha1(
        reference=consumed,
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title="Executive intelligence brief",
    )
    decision = _decision_record()
    service = _Harness(store=_store(decision), resources=_Resources(projected))
    intent = _outcome_intent(decision)

    admitted = await service.record_outcome(
        intent,
        policy_id="consumer_usefulness",
        consumed_intelligence=(consumed,),
    )

    assert isinstance(admitted.provenance_return, OutcomeProvenanceReturnV1Alpha1)
    assert admitted.provenance_return.actor_ref == "principal:consumer"
    assert admitted.provenance_return.decision == decision.reference()
    assert admitted.provenance_return.outcome == admitted.record
    assert admitted.provenance_return.consumed_intelligence == (consumed,)
    assert admitted.provenance_record in admitted.transaction_receipt.records
    assert admitted.record in admitted.transaction_receipt.records
    assert len(admitted.transaction_receipt.records) == 2

    replay = await service.record_outcome(
        intent,
        policy_id="consumer_usefulness",
        consumed_intelligence=(consumed,),
    )
    assert replay == admitted


@pytest.mark.asyncio
async def test_outcome_provenance_fails_closed_on_altered_or_cross_product_reference() -> None:
    consumed = _consumed_reference()
    projected = IntelligenceResourceRecordV1Alpha1(
        reference=consumed,
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title="Executive intelligence brief",
    )
    decision = _decision_record()
    service = _Harness(store=_store(decision), resources=_Resources(projected))
    intent = _outcome_intent(decision)

    altered = consumed.model_copy(update={"resource_digest": "sha256:" + "d" * 64})
    with pytest.raises(PreparedDecisionFeedbackError, match="exact revision"):
        await service.record_outcome(
            intent,
            policy_id="consumer_usefulness",
            consumed_intelligence=(altered,),
        )

    crossed = _consumed_reference(product_id="product:other")
    with pytest.raises(PreparedDecisionFeedbackError, match="crossed product scope"):
        await service.record_outcome(
            intent,
            policy_id="consumer_usefulness",
            consumed_intelligence=(crossed,),
        )


@pytest.mark.asyncio
async def test_outcome_provenance_requires_at_least_one_exact_consumed_resource() -> None:
    consumed = _consumed_reference()
    projected = IntelligenceResourceRecordV1Alpha1(
        reference=consumed,
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title="Executive intelligence brief",
    )
    decision = _decision_record()
    service = _Harness(store=_store(decision), resources=_Resources(projected))

    with pytest.raises(PreparedDecisionFeedbackError, match="requires consumed Intelligence"):
        await service.record_outcome(
            _outcome_intent(decision),
            policy_id="consumer_usefulness",
            consumed_intelligence=(),
        )
