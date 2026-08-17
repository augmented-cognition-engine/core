from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.intelligence_resource_feedback import (
    RESOURCE_FEEDBACK_AUTHORITY,
    RESOURCE_FEEDBACK_OPERATION,
    IntelligenceResourceFeedbackError,
    IntelligenceResourceFeedbackReplayConflict,
    IntelligenceResourceFeedbackService,
)
from ace.application.intelligence_resource_projection import DecisionOutcomeFeedbackResourceProjectionReader
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.resource_feedback import (
    IntelligenceResourceCorrectionIntent,
    IntelligenceResourceFeedbackRequestV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

PRODUCT = "product:resource-feedback"
ACTOR = "principal:analyst"
GRANT = "authority_grant:resource-feedback"
NOW = datetime(2026, 8, 15, 18, 0, tzinfo=UTC)


def _store() -> InMemoryImmutableRecordStore:
    return InMemoryImmutableRecordStore(
        governed_state_heads={
            ("authority_grant", PRODUCT, GRANT): GovernedStateHeadV1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:feedback",
                commit_receipt_id="authority_receipt:feedback",
                updated_at=NOW - timedelta(minutes=10),
            )
        }
    )


def _context(suffix: str = "a") -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref=f"authentication_receipt:{suffix}",
        authentication_receipt_digest="sha256:" + suffix[0] * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )


def _reference(kind: IntelligenceResourceKind, suffix: str) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=PRODUCT,
        resource_kind=kind,
        resource_id=f"{kind.value}:{suffix}",
        resource_digest="sha256:" + suffix[0] * 64,
        resource_contract=f"ace.intelligence.{kind.value}/v1alpha1",
        revision=2,
        as_of=NOW - timedelta(days=1),
        available_at=NOW - timedelta(hours=1),
    )


def _record(reference: IntelligenceResourceReferenceV1Alpha1) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=reference,
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title="Exact assessment",
        subject_refs=("entity:subject",),
    )


class _Targets:
    def __init__(self, *records: IntelligenceResourceRecordV1Alpha1) -> None:
        self.records = {item.reference: item for item in records}
        self.calls: list[IntelligenceResourceReferenceV1Alpha1] = []

    async def load_exact(self, reference, *, evaluated_at):
        self.calls.append(reference)
        return self.records.get(reference)


class _Authority:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
        self.calls.append(kwargs)
        return AuthorityUseReceiptV1Alpha1(
            product_id=kwargs["context"].product_id,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref=kwargs["grant_ref"],
            grant_hash="f" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:feedback",
                commit_receipt_id="authority_receipt:feedback",
            ),
        )


def _request(
    target: IntelligenceResourceReferenceV1Alpha1,
    *,
    context: AuthenticatedRuntimeContextV1Alpha1 | None = None,
    note: str = "The assessment predates the newly published filing.",
    evidence: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = (),
) -> IntelligenceResourceFeedbackRequestV1Alpha1:
    return IntelligenceResourceFeedbackRequestV1Alpha1(
        authenticated_context=context or _context(),
        product_id=PRODUCT,
        authority_grant_ref=GRANT,
        request_key="feedback-request:stable-1",
        target=target,
        correction_intent=IntelligenceResourceCorrectionIntent.OUTDATED,
        note=note,
        evidence=evidence,
        requested_at=NOW,
    )


@pytest.mark.asyncio
async def test_records_attributed_exact_feedback_without_claiming_effects() -> None:
    target = _reference(IntelligenceResourceKind.SHIFT, "a")
    evidence = _reference(IntelligenceResourceKind.OBSERVATION, "b")
    records = _store()
    authority = _Authority()
    service = IntelligenceResourceFeedbackService(
        records=records,
        targets=_Targets(_record(target), _record(evidence)),
        authority=authority,
    )

    admitted = await service.submit(_request(target, evidence=(evidence,)), evaluated_at=NOW)

    feedback = admitted.feedback
    assert feedback.request.target == target
    assert feedback.request.evidence == (evidence,)
    assert feedback.request.authenticated_context.actor_ref == ACTOR
    assert feedback.disposition == "recorded_proposal_only"
    assert feedback.changes_target is False
    assert feedback.changes_source_trust is False
    assert feedback.changes_ranking is False
    assert feedback.triggers_recalculation is False
    assert admitted.record.record_kind == "resource_feedback"
    assert admitted.transaction.governed_state_preconditions == (feedback.authority_use.state_head_precondition,)
    assert authority.calls[0]["operation"] == RESOURCE_FEEDBACK_OPERATION
    assert authority.calls[0]["authority"] == RESOURCE_FEEDBACK_AUTHORITY


@pytest.mark.asyncio
async def test_reauthenticates_idempotent_replay_and_rejects_changed_material() -> None:
    target = _reference(IntelligenceResourceKind.BRIEF, "c")
    records = _store()
    authority = _Authority()
    service = IntelligenceResourceFeedbackService(
        records=records,
        targets=_Targets(_record(target)),
        authority=authority,
    )
    first = await service.submit(_request(target), evaluated_at=NOW)
    replay = await service.submit(_request(target, context=_context("d")), evaluated_at=NOW)

    assert replay == first
    assert len(authority.calls) == 2

    with pytest.raises(IntelligenceResourceFeedbackReplayConflict, match="different correction material"):
        await service.submit(_request(target, note="Different material under the same request key."), evaluated_at=NOW)


@pytest.mark.asyncio
async def test_fails_closed_when_exact_target_or_evidence_is_not_loaded() -> None:
    target = _reference(IntelligenceResourceKind.ENTITY, "e")
    missing = _reference(IntelligenceResourceKind.OBSERVATION, "f")
    records = _store()
    service = IntelligenceResourceFeedbackService(
        records=records,
        targets=_Targets(_record(target)),
        authority=_Authority(),
    )
    with pytest.raises(IntelligenceResourceFeedbackError, match="evidence exact revision is unavailable"):
        await service.submit(_request(target, evidence=(missing,)), evaluated_at=NOW)
    assert records.records == {}


@pytest.mark.asyncio
async def test_projects_recorded_resource_feedback_as_non_effective_feedback() -> None:
    target = _reference(IntelligenceResourceKind.SIGNAL, "a")
    records = _store()
    admitted = await IntelligenceResourceFeedbackService(
        records=records,
        targets=_Targets(_record(target)),
        authority=_Authority(),
    ).submit(_request(target), evaluated_at=NOW)
    query = IntelligenceResourceQueryV1Alpha1(
        authenticated_context=_context(),
        product_id=PRODUCT,
        authority_grant_ref=GRANT,
        resource_kinds=(IntelligenceResourceKind.FEEDBACK,),
        subject_refs=(),
        as_of=NOW,
        available_at=NOW,
        page_size=20,
    )

    batch = await DecisionOutcomeFeedbackResourceProjectionReader(store=records).read(
        query=query,
        after=None,
        limit=20,
    )

    assert batch.degraded_reason_refs == ()
    assert len(batch.records) == 1
    projected = batch.records[0]
    assert projected.reference.resource_kind is IntelligenceResourceKind.FEEDBACK
    assert projected.provenance == (target,)
    assert projected.summary == admitted.feedback.request.note
    assert projected.title == "Correction proposal: outdated"
