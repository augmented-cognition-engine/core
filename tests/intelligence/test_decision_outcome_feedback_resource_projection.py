from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application import DecisionOutcomeFeedbackResourceProjectionReader
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    DecisionActionDisposition,
    DecisionDisposition,
    DecisionIntentV1Alpha1,
    DecisionV1Alpha1,
    GovernedActionAuthorizationProjection,
    GovernedStateHeadPreconditionV1Alpha1,
    ImmutableRecordV1,
    OutcomeIntentV1Alpha1,
    OutcomeV1Alpha1,
    ReceiptReferenceV1Alpha1,
)
from ace.core.contracts import canonical_hash
from ace.intelligence import (
    ActivationRevisionReferenceV1Alpha1,
    BriefV1Alpha1,
    CitationV1Alpha1,
    CompiledPackRefV1,
    EvidenceAcquisitionMode,
    FeedbackProposalIntentV1Alpha1,
    FeedbackProposalV1Alpha1,
    GroundedClaimV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourceMode,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader

pytestmark = pytest.mark.unit

PRODUCT = "product:decision-loop-projection"
NOW = datetime(2026, 8, 13, 1, 0, tzinfo=UTC)


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref="principal:executive",
        authentication_receipt_ref="authentication:decision-loop",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW,
        expires_at=NOW + timedelta(hours=2),
    )


def _authorization(minutes: int) -> GovernedActionAuthorizationProjection:
    return GovernedActionAuthorizationProjection(
        authorization_ref=ReceiptReferenceV1Alpha1(
            receipt_id=f"authorization:decision-loop:{minutes}",
            receipt_digest="sha256:" + f"{minutes % 10}" * 64,
        ),
        authorized_at=NOW + timedelta(minutes=minutes),
        state_preconditions=(
            GovernedStateHeadPreconditionV1Alpha1(
                state_kind="capability_state",
                product_id=PRODUCT,
                state_id="capability_state:decision-loop",
                sequence=1,
                revision_id="revision:capability:1",
                commit_receipt_id="commit:capability:1",
            ),
            GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id="authority_grant:decision-loop",
                sequence=1,
                revision_id="revision:authority:1",
                commit_receipt_id="commit:authority:1",
            ),
        ),
    )


def _brief() -> ImmutableRecordV1:
    activation_key = "ai_command_center"
    activation = ActivationRevisionReferenceV1Alpha1(
        product_id=PRODUCT,
        activation_key=activation_key,
        activation_id=f"domain_activation:{canonical_hash([PRODUCT, activation_key])[:32]}",
        revision=1,
        revision_id="activation_revision:" + "b" * 32,
        revision_digest="sha256:" + "b" * 64,
    )
    citation = CitationV1Alpha1(
        source_ref="source:public-ai-economics",
        source_digest="sha256:" + "e" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="source_acquisition:ai-economics",
        acquisition_receipt_digest="sha256:" + "f" * 64,
        source_as_of=NOW,
        retrieved_at=NOW,
        locator="section:token-economics",
        excerpt="The observed economics changed.",
    )
    brief = BriefV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=activation,
        as_of=NOW,
        brief_type_ref="brief_type:executive-intelligence",
        title="AI economics changed",
        executive_summary="A material AI economics change merits executive review.",
        body_markdown="## What changed\n\nAI economics changed.",
        generated_at=NOW,
        citations=(citation,),
        claims=(
            GroundedClaimV1Alpha1(
                statement="AI economics changed.",
                citation_ids=(str(citation.citation_id),),
                confidence=0.9,
            ),
        ),
    )
    return ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="prepared",
        record_kind="brief",
        record_key=str(brief.resource_id),
        payload_contract=brief.contract,
        payload=brief.model_dump(mode="python"),
        as_of=brief.as_of,
        available_at=brief.generated_at,
        processing_order=0,
    )


def _decision() -> tuple[DecisionV1Alpha1, ImmutableRecordV1]:
    value = DecisionV1Alpha1(
        intent=DecisionIntentV1Alpha1(
            product_id=PRODUCT,
            authenticated_context=_context(),
            subject=_brief().reference(),
            actor_role_ref="persona:executive",
            decision_type="investment_review",
            disposition=DecisionDisposition.ACCEPT,
            action_disposition=DecisionActionDisposition.NO_ACTION,
            rationale="Use the evidence in the next investment review.",
            decided_at=NOW + timedelta(minutes=1),
        ),
        authorization=_authorization(2),
    )
    record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="prepared",
        record_kind="decision",
        record_key=str(value.decision_id),
        payload_contract=value.contract,
        payload=value.model_dump(mode="python"),
        as_of=value.intent.decided_at,
        available_at=value.authorization.authorized_at,
        processing_order=0,
    )
    return value, record


def _outcome() -> tuple[OutcomeV1Alpha1, ImmutableRecordV1]:
    _, decision_record = _decision()
    value = OutcomeV1Alpha1(
        intent=OutcomeIntentV1Alpha1(
            product_id=PRODUCT,
            authenticated_context=_context(),
            decision=decision_record.reference(),
            outcome_type="decision_usefulness",
            measure_id="executive_usefulness",
            value_json='"useful"',
            observed_at=NOW + timedelta(minutes=3),
            recorded_at=NOW + timedelta(minutes=4),
        ),
        authorization=_authorization(5),
    )
    record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="prepared",
        record_kind="outcome",
        record_key=str(value.outcome_id),
        payload_contract=value.contract,
        payload=value.model_dump(mode="python"),
        as_of=value.intent.observed_at,
        available_at=value.authorization.authorized_at,
        processing_order=0,
    )
    return value, record


def _feedback() -> tuple[FeedbackProposalV1Alpha1, ImmutableRecordV1]:
    _, decision_record = _decision()
    _, outcome_record = _outcome()
    activation_key = "ai_command_center"
    activation = ActivationRevisionReferenceV1Alpha1(
        product_id=PRODUCT,
        activation_key=activation_key,
        activation_id=f"domain_activation:{canonical_hash([PRODUCT, activation_key])[:32]}",
        revision=1,
        revision_id="activation_revision:" + "b" * 32,
        revision_digest="sha256:" + "b" * 64,
    )
    value = FeedbackProposalV1Alpha1(
        intent=FeedbackProposalIntentV1Alpha1(
            product_id=PRODUCT,
            activation_revision=activation,
            pack=CompiledPackRefV1(
                pack_id="ai_command_center",
                pack_version="0.1.0",
                compiled_pack_id="pack_ir:" + "c" * 32,
                pack_digest="sha256:" + "c" * 64,
            ),
            policy_id="executive_usefulness",
            policy_digest="sha256:" + "d" * 64,
            decision=decision_record.reference(),
            outcome=outcome_record.reference(),
            prior_value=0.5,
            outcome_value_json='"useful"',
            adjustment=0.05,
            proposed_value=0.55,
            proposed_at=NOW + timedelta(minutes=6),
        ),
        authorization=_authorization(7),
    )
    record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="prepared",
        record_kind="feedback_proposal",
        record_key=str(value.proposal_id),
        payload_contract=value.contract,
        payload=value.model_dump(mode="python"),
        as_of=outcome_record.as_of,
        available_at=value.authorization.authorized_at,
        processing_order=0,
    )
    return value, record


def _store(*records: ImmutableRecordV1) -> InMemoryImmutableRecordStore:
    store = InMemoryImmutableRecordStore()
    store.records.update({str(record.storage_id): record for record in records})
    return store


def _query(*kinds: IntelligenceResourceKind, subject_refs: tuple[str, ...] = ()) -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=_context(),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:decision-loop-read",
        resource_kinds=kinds,
        subject_refs=subject_refs,
        as_of=NOW + timedelta(minutes=10),
        available_at=NOW + timedelta(minutes=10),
        page_size=20,
    )


@pytest.mark.asyncio
async def test_projects_exact_decision_outcome_feedback_chain_with_public_provenance() -> None:
    _, decision_record = _decision()
    _, outcome_record = _outcome()
    _, feedback_record = _feedback()
    batch = await DecisionOutcomeFeedbackResourceProjectionReader(
        store=_store(_brief(), decision_record, outcome_record, feedback_record)
    ).read(
        query=_query(
            IntelligenceResourceKind.DECISION,
            IntelligenceResourceKind.OUTCOME,
            IntelligenceResourceKind.FEEDBACK,
        ),
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert [item.reference.resource_kind for item in batch.records] == [
        IntelligenceResourceKind.DECISION,
        IntelligenceResourceKind.OUTCOME,
        IntelligenceResourceKind.FEEDBACK,
    ]
    decision, outcome, feedback = batch.records
    assert decision.provenance[0].resource_kind is IntelligenceResourceKind.BRIEF
    assert decision.provenance[0].resource_digest == _brief().payload["resource_digest"]
    assert decision.provenance[0].resource_digest != _brief().material_hash
    assert outcome.provenance[0].resource_id == decision.reference.resource_id
    assert [item.resource_kind for item in feedback.provenance] == [
        IntelligenceResourceKind.DECISION,
        IntelligenceResourceKind.OUTCOME,
    ]
    assert feedback.payload is not None
    assert feedback.payload.parsed_value()["intent"]["proposed_value"] == 0.55


def test_supported_host_composition_includes_the_complete_current_resource_plane() -> None:
    reader = intelligence_resource_projection_reader(InMemoryImmutableRecordStore())
    assert {
        IntelligenceResourceKind.OBSERVATION,
        IntelligenceResourceKind.MONITOR,
        IntelligenceResourceKind.SUBSCRIPTION,
        IntelligenceResourceKind.DECISION,
        IntelligenceResourceKind.OUTCOME,
        IntelligenceResourceKind.FEEDBACK,
    } <= reader.supported_kinds


@pytest.mark.asyncio
async def test_subject_filter_and_historical_cutoff_preserve_exact_visibility() -> None:
    _, decision_record = _decision()
    _, outcome_record = _outcome()
    reader = DecisionOutcomeFeedbackResourceProjectionReader(store=_store(decision_record, outcome_record))
    filtered = await reader.read(
        query=_query(IntelligenceResourceKind.OUTCOME, subject_refs=("principal:executive",)),
        after=None,
        limit=20,
    )
    assert len(filtered.records) == 1

    query = _query(IntelligenceResourceKind.OUTCOME)
    historical = query.model_copy(update={"as_of": NOW + timedelta(minutes=2)})
    hidden = await reader.read(query=historical, after=None, limit=20)
    assert hidden.records == ()


@pytest.mark.asyncio
async def test_invalid_envelope_degrades_without_exposing_payload() -> None:
    value, record = _decision()
    invalid = ImmutableRecordV1(
        **record.model_dump(mode="python", exclude={"storage_id", "material_hash", "record_key"}),
        record_key="decision:wrong-envelope",
    )
    batch = await DecisionOutcomeFeedbackResourceProjectionReader(store=_store(invalid)).read(
        query=_query(IntelligenceResourceKind.DECISION),
        after=None,
        limit=20,
    )
    assert value.decision_id != invalid.record_key
    assert batch.records == ()
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.degraded_reason_refs == ("degraded_reason:invalid-prepared-decision",)


@pytest.mark.asyncio
async def test_unknown_decision_subject_is_visible_but_never_mislabeled_as_lineage() -> None:
    subject = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="prepared",
        record_kind="opaque_orientation",
        record_key="orientation:one",
        payload_contract="example.orientation/v1",
        payload={"orientation": "opaque"},
        as_of=NOW,
        available_at=NOW,
        processing_order=0,
    )
    value = DecisionV1Alpha1(
        intent=DecisionIntentV1Alpha1(
            product_id=PRODUCT,
            authenticated_context=_context(),
            subject=subject.reference(),
            actor_role_ref="persona:executive",
            decision_type="orientation_review",
            disposition=DecisionDisposition.ACCEPT,
            action_disposition=DecisionActionDisposition.NO_ACTION,
            rationale="Retain the decision without inventing a public subject type.",
            decided_at=NOW + timedelta(minutes=1),
        ),
        authorization=_authorization(2),
    )
    record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="prepared",
        record_kind="decision",
        record_key=str(value.decision_id),
        payload_contract=value.contract,
        payload=value.model_dump(mode="python"),
        as_of=value.intent.decided_at,
        available_at=value.authorization.authorized_at,
        processing_order=0,
    )
    batch = await DecisionOutcomeFeedbackResourceProjectionReader(store=_store(record)).read(
        query=_query(IntelligenceResourceKind.DECISION),
        after=None,
        limit=20,
    )
    assert len(batch.records) == 1
    assert batch.records[0].provenance == ()
    assert batch.records[0].availability.value == "degraded"
    assert batch.degraded_reason_refs == ("degraded_reason:unsupported-decision-subject",)
