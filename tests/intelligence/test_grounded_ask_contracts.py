from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.grounded_ask import (
    AskAnswerV1Alpha1,
    AskNoAnswerV1Alpha1,
    AskQuestionV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceKind,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import (
    CitationV1Alpha1,
    ClaimGroundingKind,
    EvidenceAcquisitionMode,
    GroundedClaimV1Alpha1,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:grounded-ask"
ACTOR = "principal:asker"
GRANT = "authority_grant:grounded-ask"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:ask",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )


def _authority_use(subject: str, digest: str) -> AuthorityUseReceiptV1Alpha1:
    return AuthorityUseReceiptV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authenticated_context=_context(),
        use_subject_ref=subject,
        use_subject_digest=digest,
        operation="query_intelligence_resources",
        authority="observe_read",
        grant_ref=GRANT,
        grant_hash="f" * 64,
        evaluated_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
            state_kind="authority_grant",
            product_id=PRODUCT,
            state_id=GRANT,
            sequence=1,
            revision_id="authority_revision:ask",
            commit_receipt_id="authority_receipt:ask",
        ),
    )


def _citation() -> CitationV1Alpha1:
    return CitationV1Alpha1(
        source_ref="evidence:public-snapshot",
        source_digest="sha256:" + "b" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:public-snapshot-acquisition",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=NOW - timedelta(days=1),
        retrieved_at=NOW - timedelta(days=1),
        locator="section:1",
        excerpt="Revenue grew year over year.",
    )


def _claim(citation: CitationV1Alpha1) -> GroundedClaimV1Alpha1:
    return GroundedClaimV1Alpha1(
        statement="Revenue grew year over year.",
        citation_ids=(citation.citation_id,),
        confidence=0.9,
    )


def _brief_reference() -> IntelligenceResourceReferenceV1Alpha1:
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


def test_ask_question_requires_matching_context_and_product_scope() -> None:
    with pytest.raises(ValidationError, match="crossed authenticated product scope"):
        AskQuestionV1Alpha1(
            authenticated_context=_context(),
            product_id="product:other",
            authority_grant_ref=GRANT,
            question="Did revenue grow?",
            as_of=NOW,
            available_at=NOW,
        )


def test_ask_answer_requires_every_claim_citation_to_resolve() -> None:
    citation = _citation()
    claim = _claim(citation)
    unrelated = CitationV1Alpha1(
        source_ref="evidence:unrelated",
        source_digest="sha256:" + "e" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:unrelated",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=NOW - timedelta(days=1),
        retrieved_at=NOW - timedelta(days=1),
    )
    with pytest.raises(ValidationError, match="missing citations"):
        AskAnswerV1Alpha1(
            question="Did revenue grow?",
            product_id=PRODUCT,
            actor_ref=ACTOR,
            claims=(claim,),
            citations=(unrelated,),
            source_briefs=(_brief_reference(),),
            answered_at=NOW,
            authority_use=_authority_use(claim.claim_id, claim.claim_digest),
        )


def test_ask_answer_rejects_unused_citations() -> None:
    citation = _citation()
    claim = _claim(citation)
    other = CitationV1Alpha1(
        source_ref="evidence:unused",
        source_digest="sha256:" + "d" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:unused",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=NOW - timedelta(days=1),
        retrieved_at=NOW - timedelta(days=1),
    )
    with pytest.raises(ValidationError, match="unused citations"):
        AskAnswerV1Alpha1(
            question="Did revenue grow?",
            product_id=PRODUCT,
            actor_ref=ACTOR,
            claims=(claim,),
            citations=(citation, other),
            source_briefs=(_brief_reference(),),
            answered_at=NOW,
            authority_use=_authority_use(claim.claim_id, claim.claim_digest),
        )


def test_ask_answer_rejects_inference_claims() -> None:
    basis_citation = _citation()
    inference = GroundedClaimV1Alpha1(
        statement="Revenue likely grew.",
        grounding_kind=ClaimGroundingKind.INFERENCE,
        inference_basis_refs=("observation:x",),
        confidence=0.4,
        uncertainty="Based on partial data.",
    )
    with pytest.raises(ValidationError, match="only surface cited claims"):
        AskAnswerV1Alpha1(
            question="Did revenue grow?",
            product_id=PRODUCT,
            actor_ref=ACTOR,
            claims=(inference,),
            citations=(basis_citation,),
            source_briefs=(_brief_reference(),),
            answered_at=NOW,
            authority_use=_authority_use(inference.claim_id, inference.claim_digest),
        )


def test_ask_answer_accepts_one_grounded_claim_and_its_citation() -> None:
    citation = _citation()
    claim = _claim(citation)
    answer = AskAnswerV1Alpha1(
        question="Did revenue grow?",
        product_id=PRODUCT,
        actor_ref=ACTOR,
        claims=(claim,),
        citations=(citation,),
        source_briefs=(_brief_reference(),),
        answered_at=NOW,
        authority_use=_authority_use(claim.claim_id, claim.claim_digest),
    )
    assert answer.claims == (claim,)
    assert answer.citations == (citation,)


def test_no_answer_requires_at_least_one_missing_coverage_reason() -> None:
    with pytest.raises(ValidationError):
        AskNoAnswerV1Alpha1(
            question="Did revenue grow?",
            product_id=PRODUCT,
            actor_ref=ACTOR,
            missing_coverage=(),
            evaluated_at=NOW,
            authority_use=_authority_use("ask:none", "sha256:" + "0" * 64),
        )


def test_no_answer_accepts_a_named_missing_coverage_reason() -> None:
    no_answer = AskNoAnswerV1Alpha1(
        question="Did revenue grow?",
        product_id=PRODUCT,
        actor_ref=ACTOR,
        missing_coverage=("missing_coverage:no_claims_matched_question_terms",),
        evaluated_at=NOW,
        authority_use=_authority_use("ask:none", "sha256:" + "0" * 64),
    )
    assert no_answer.missing_coverage == ("missing_coverage:no_claims_matched_question_terms",)
