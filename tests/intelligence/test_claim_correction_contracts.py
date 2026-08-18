from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application.intelligence_resource_feedback import IntelligenceResourceFeedbackService
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.claim_correction import ClaimCorrectionAdmissionV1Alpha1, ClaimCorrectionRequestV1Alpha1
from ace.intelligence.contracts.resource_feedback import (
    IntelligenceResourceCorrectionIntent,
    IntelligenceResourceFeedbackRequestV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

PRODUCT = "product:claim-correction"
ACTOR = "principal:corrector"
GRANT = "authority_grant:claim-correction"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _store() -> InMemoryImmutableRecordStore:
    return InMemoryImmutableRecordStore(
        governed_state_heads={
            ("authority_grant", PRODUCT, GRANT): GovernedStateHeadV1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:claim-correction",
                commit_receipt_id="authority_receipt:claim-correction",
                updated_at=NOW - timedelta(minutes=10),
            )
        }
    )


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:correction",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )


def _target() -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=PRODUCT,
        resource_kind=IntelligenceResourceKind.BRIEF,
        resource_id="brief:revenue",
        resource_digest="sha256:" + "c" * 64,
        resource_contract="ace.intelligence.brief/v1alpha1",
        revision=1,
        as_of=NOW - timedelta(hours=2),
        available_at=NOW - timedelta(hours=1),
    )


def _target_record() -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=_target(),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title="Revenue briefing",
    )


class _Targets:
    def __init__(self, *records: IntelligenceResourceRecordV1Alpha1) -> None:
        self.records = {item.reference: item for item in records}

    async def load_exact(self, reference, *, evaluated_at):
        return self.records.get(reference)


class _Authority:
    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
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
                revision_id="authority_revision:claim-correction",
                commit_receipt_id="authority_receipt:claim-correction",
            ),
        )


def _request(**overrides) -> ClaimCorrectionRequestV1Alpha1:
    fields = {
        "authenticated_context": _context(),
        "product_id": PRODUCT,
        "authority_grant_ref": GRANT,
        "request_key": "claim-correction:stable-1",
        "target": _target(),
        "claim_id": "grounded_claim:" + "1" * 32,
        "citation_id": "citation:" + "2" * 32,
        "correction_intent": IntelligenceResourceCorrectionIntent.OUTDATED,
        "note": "The cited filing was later restated.",
        "requested_at": NOW,
    }
    fields.update(overrides)
    return ClaimCorrectionRequestV1Alpha1(**fields)


def test_rejects_a_target_that_is_not_a_brief() -> None:
    non_brief = IntelligenceResourceReferenceV1Alpha1(
        product_id=PRODUCT,
        resource_kind=IntelligenceResourceKind.SIGNAL,
        resource_id="signal:x",
        resource_digest="sha256:" + "d" * 64,
        resource_contract="ace.intelligence.signal/v1alpha1",
        revision=1,
        as_of=NOW - timedelta(hours=2),
        available_at=NOW - timedelta(hours=1),
    )
    with pytest.raises(ValidationError, match="only target a Brief"):
        _request(target=non_brief)


def test_feedback_note_embeds_the_exact_claim_and_citation_identity() -> None:
    request = _request()
    assert request.feedback_note == (f"[claim:{request.claim_id}][citation:{request.citation_id}] {request.note}")


@pytest.mark.asyncio
async def test_admission_rejects_a_feedback_record_scoped_to_a_different_claim() -> None:
    request = _request()
    feedback_service = IntelligenceResourceFeedbackService(
        records=_store(),
        targets=_Targets(_target_record()),
        authority=_Authority(),
    )

    underlying = IntelligenceResourceFeedbackRequestV1Alpha1(
        authenticated_context=request.authenticated_context,
        product_id=request.product_id,
        authority_grant_ref=request.authority_grant_ref,
        request_key=request.request_key,
        target=request.target,
        correction_intent=request.correction_intent,
        note="Some other unbound note.",
        requested_at=request.requested_at,
    )
    admission = await feedback_service.submit(underlying, evaluated_at=NOW)

    with pytest.raises(ValidationError, match="exact claim/citation-bound proposal"):
        ClaimCorrectionAdmissionV1Alpha1(request=request, feedback=admission)


@pytest.mark.asyncio
async def test_admission_accepts_a_feedback_record_bound_to_the_exact_claim() -> None:
    request = _request()
    feedback_service = IntelligenceResourceFeedbackService(
        records=_store(),
        targets=_Targets(_target_record()),
        authority=_Authority(),
    )

    underlying = IntelligenceResourceFeedbackRequestV1Alpha1(
        authenticated_context=request.authenticated_context,
        product_id=request.product_id,
        authority_grant_ref=request.authority_grant_ref,
        request_key=request.request_key,
        target=request.target,
        correction_intent=request.correction_intent,
        note=request.feedback_note,
        requested_at=request.requested_at,
    )
    admission = await feedback_service.submit(underlying, evaluated_at=NOW)

    bound = ClaimCorrectionAdmissionV1Alpha1(request=request, feedback=admission)
    assert bound.request.claim_id == request.claim_id
