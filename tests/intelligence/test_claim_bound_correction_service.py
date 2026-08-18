from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.claim_bound_correction import (
    ClaimBoundCorrectionError,
    ClaimBoundCorrectionNotFound,
    ClaimBoundCorrectionService,
)
from ace.application.intelligence_resource_feedback import IntelligenceResourceFeedbackService
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.claim_correction import ClaimCorrectionRequestV1Alpha1
from ace.intelligence.contracts.resource_feedback import IntelligenceResourceCorrectionIntent
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    BriefV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    CitationV1Alpha1,
    EvidenceAcquisitionMode,
    GroundedClaimV1Alpha1,
    IntelligenceResourceMode,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

PRODUCT = "product:claim-bound-correction"
ACTOR = "principal:corrector"
GRANT = "authority_grant:claim-bound-correction"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _store() -> InMemoryImmutableRecordStore:
    return InMemoryImmutableRecordStore(
        governed_state_heads={
            ("authority_grant", PRODUCT, GRANT): GovernedStateHeadV1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:claim-bound-correction",
                commit_receipt_id="authority_receipt:claim-bound-correction",
                updated_at=NOW - timedelta(minutes=10),
            )
        }
    )


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:claim-bound-correction",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )


def _activation() -> ActivationRevisionReferenceV1Alpha1:
    return ActivationRevisionReferenceV1Alpha1(
        product_id=PRODUCT,
        activation_key="generic_intelligence",
        activation_id=f"domain_activation:{canonical_hash([PRODUCT, 'generic_intelligence'])[:32]}",
        revision=1,
        revision_id="activation_revision:" + "a" * 32,
        revision_digest="sha256:" + "a" * 64,
    )


def _brief() -> BriefV1Alpha1:
    citation = CitationV1Alpha1(
        source_ref="evidence:filing",
        source_digest="sha256:" + "b" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:filing",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=NOW - timedelta(days=2),
        retrieved_at=NOW - timedelta(days=2),
    )
    claim = GroundedClaimV1Alpha1(
        statement="Revenue grew year over year.", citation_ids=(citation.citation_id,), confidence=0.9
    )
    return BriefV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=_activation(),
        as_of=NOW - timedelta(hours=2),
        brief_type_ref="briefing:revenue",
        title="Revenue briefing",
        executive_summary="Revenue grew year over year.",
        body_markdown="# Revenue\n\n- Revenue grew year over year.",
        generated_at=NOW - timedelta(hours=1, minutes=30),
        citations=(citation,),
        claims=(claim,),
    )


def _target_reference(brief: BriefV1Alpha1) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=PRODUCT,
        resource_kind=IntelligenceResourceKind.BRIEF,
        resource_id="brief:revenue",
        resource_digest=str(brief.resource_digest),
        resource_contract=brief.contract,
        revision=1,
        as_of=brief.as_of,
        available_at=NOW - timedelta(hours=1),
    )


def _target_record(brief: BriefV1Alpha1) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=_target_reference(brief),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=brief.title,
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(brief.model_dump(mode="json"))),
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
                revision_id="authority_revision:claim-bound-correction",
                commit_receipt_id="authority_receipt:claim-bound-correction",
            ),
        )


def _request(brief: BriefV1Alpha1, **overrides) -> ClaimCorrectionRequestV1Alpha1:
    claim = brief.claims[0]
    fields = {
        "authenticated_context": _context(),
        "product_id": PRODUCT,
        "authority_grant_ref": GRANT,
        "request_key": "claim-correction:stable-1",
        "target": _target_reference(brief),
        "claim_id": str(claim.claim_id),
        "citation_id": str(claim.citation_ids[0]),
        "correction_intent": IntelligenceResourceCorrectionIntent.OUTDATED,
        "note": "The cited filing was later restated.",
        "requested_at": NOW,
    }
    fields.update(overrides)
    return ClaimCorrectionRequestV1Alpha1(**fields)


def _service(*records: IntelligenceResourceRecordV1Alpha1) -> ClaimBoundCorrectionService:
    targets = _Targets(*records)
    return ClaimBoundCorrectionService(
        targets=targets,
        feedback=IntelligenceResourceFeedbackService(records=_store(), targets=targets, authority=_Authority()),
    )


@pytest.mark.asyncio
async def test_binds_a_correction_to_the_exact_claim_and_citation() -> None:
    brief = _brief()
    admission = await _service(_target_record(brief)).correct(_request(brief), evaluated_at=NOW)

    assert admission.request.claim_id == str(brief.claims[0].claim_id)
    assert admission.feedback.feedback.request.note.startswith(f"[claim:{brief.claims[0].claim_id}]")
    assert admission.feedback.feedback.disposition == "recorded_proposal_only"
    assert admission.feedback.feedback.changes_target is False


@pytest.mark.asyncio
async def test_fails_closed_when_claim_id_is_not_on_the_target_brief() -> None:
    brief = _brief()
    with pytest.raises(ClaimBoundCorrectionNotFound, match="claim_id is not present"):
        await _service(_target_record(brief)).correct(
            _request(brief, claim_id="grounded_claim:" + "9" * 32), evaluated_at=NOW
        )


@pytest.mark.asyncio
async def test_fails_closed_when_citation_id_is_not_bound_to_the_claim() -> None:
    brief = _brief()
    with pytest.raises(ClaimBoundCorrectionNotFound, match="citation_id is not bound"):
        await _service(_target_record(brief)).correct(
            _request(brief, citation_id="citation:" + "9" * 32), evaluated_at=NOW
        )


@pytest.mark.asyncio
async def test_fails_closed_when_target_brief_is_unavailable() -> None:
    brief = _brief()
    with pytest.raises(ClaimBoundCorrectionError, match="unavailable"):
        await _service().correct(_request(brief), evaluated_at=NOW)


@pytest.mark.asyncio
async def test_never_mutates_the_target_and_stays_proposal_only() -> None:
    brief = _brief()
    admission = await _service(_target_record(brief)).correct(_request(brief), evaluated_at=NOW)

    assert admission.feedback.feedback.changes_source_trust is False
    assert admission.feedback.feedback.changes_ranking is False
    assert admission.feedback.feedback.triggers_recalculation is False
