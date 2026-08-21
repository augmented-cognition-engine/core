from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.grounded_ask import ASK_MAX_CANDIDATE_BRIEFS, GroundedAskError, GroundedAskService
from ace.application.intelligence_resource_plane import (
    IntelligenceResourcePlaneService,
    IntelligenceResourceProjectionBatch,
)
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.grounded_ask import AskAnswerV1Alpha1, AskNoAnswerV1Alpha1, AskQuestionV1Alpha1
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

pytestmark = pytest.mark.unit

PRODUCT = "product:grounded-ask-service"
ACTOR = "principal:asker"
GRANT = "authority_grant:grounded-ask-service"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:ask-service",
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


def _citation(suffix: str, *, excerpt: str) -> CitationV1Alpha1:
    return CitationV1Alpha1(
        source_ref=f"evidence:{suffix}",
        source_digest="sha256:" + "b" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref=f"receipt:{suffix}",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=NOW - timedelta(days=2),
        retrieved_at=NOW - timedelta(days=2),
        locator="section:1",
        excerpt=excerpt,
    )


def _brief(*, resource_id_hex: str, statement: str, excerpt: str, confidence: float = 0.9) -> BriefV1Alpha1:
    citation = _citation(resource_id_hex, excerpt=excerpt)
    claim = GroundedClaimV1Alpha1(statement=statement, citation_ids=(citation.citation_id,), confidence=confidence)
    return BriefV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=_activation(),
        as_of=NOW - timedelta(hours=2),
        brief_type_ref="briefing:revenue",
        title="Revenue briefing",
        executive_summary=statement,
        body_markdown=f"# Revenue\n\n- {statement}",
        generated_at=NOW - timedelta(hours=1, minutes=30),
        citations=(citation,),
        claims=(claim,),
    )


def _brief_record(
    brief: BriefV1Alpha1, *, resource_id: str, available_at: datetime = NOW - timedelta(hours=1)
) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=IntelligenceResourceReferenceV1Alpha1(
            product_id=PRODUCT,
            resource_kind=IntelligenceResourceKind.BRIEF,
            resource_id=resource_id,
            resource_digest=str(brief.resource_digest),
            resource_contract=brief.contract,
            revision=1,
            as_of=brief.as_of,
            available_at=available_at,
        ),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=brief.title,
        summary=brief.executive_summary,
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(brief.model_dump(mode="json"))),
    )


class _Reader:
    def __init__(self, *records: IntelligenceResourceRecordV1Alpha1) -> None:
        self.records = records

    async def read(self, **kwargs) -> IntelligenceResourceProjectionBatch:
        return IntelligenceResourceProjectionBatch(records=self.records)


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
                revision_id="authority_revision:ask-service",
                commit_receipt_id="authority_receipt:ask-service",
            ),
        )


class _MismatchedAuthority:
    """Returns a receipt for a different grant than the one requested."""

    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
        return AuthorityUseReceiptV1Alpha1(
            product_id=kwargs["context"].product_id,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref="authority_grant:different-grant",
            grant_hash="f" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id="authority_grant:different-grant",
                sequence=1,
                revision_id="authority_revision:ask-service",
                commit_receipt_id="authority_receipt:ask-service",
            ),
        )


def _question(*, question: str = "Did revenue grow?", max_claims: int = 5) -> AskQuestionV1Alpha1:
    return AskQuestionV1Alpha1(
        authenticated_context=_context(),
        product_id=PRODUCT,
        authority_grant_ref=GRANT,
        question=question,
        as_of=NOW,
        available_at=NOW,
        max_claims=max_claims,
    )


@pytest.mark.asyncio
async def test_answers_with_the_exact_persisted_claim_and_citation() -> None:
    brief = _brief(resource_id_hex="a", statement="Revenue grew year over year.", excerpt="Revenue rose 12%.")
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_Reader(_brief_record(brief, resource_id="brief:revenue")),
            authority=_Authority(),
        )
    )

    result = await service.ask(_question(), evaluated_at=NOW)

    assert isinstance(result, AskAnswerV1Alpha1)
    assert result.claims == brief.claims
    assert result.citations == brief.citations
    assert result.source_briefs[0].resource_id == "brief:revenue"


@pytest.mark.asyncio
async def test_refuses_honestly_when_no_claim_matches_the_question() -> None:
    brief = _brief(resource_id_hex="a", statement="Headcount stayed flat.", excerpt="No hiring this quarter.")
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_Reader(_brief_record(brief, resource_id="brief:headcount")),
            authority=_Authority(),
        )
    )

    result = await service.ask(_question(question="Did revenue grow?"), evaluated_at=NOW)

    assert isinstance(result, AskNoAnswerV1Alpha1)
    assert result.missing_coverage == ("missing_coverage:no_claims_matched_question_terms",)
    assert result.considered_briefs[0].resource_id == "brief:headcount"


@pytest.mark.asyncio
async def test_refuses_honestly_when_no_brief_resources_are_visible() -> None:
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(reader=_Reader(), authority=_Authority())
    )

    result = await service.ask(_question(), evaluated_at=NOW)

    assert isinstance(result, AskNoAnswerV1Alpha1)
    assert result.missing_coverage == ("missing_coverage:no_authorized_brief_resources_available",)
    assert result.considered_briefs == ()


@pytest.mark.asyncio
async def test_fails_closed_when_authority_resolver_does_not_preserve_the_exact_query() -> None:
    brief = _brief(resource_id_hex="a", statement="Revenue grew year over year.", excerpt="Revenue rose 12%.")
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_Reader(_brief_record(brief, resource_id="brief:revenue")),
            authority=_MismatchedAuthority(),
        )
    )

    with pytest.raises(GroundedAskError, match="authorized Brief retrieval failed closed"):
        await service.ask(_question(), evaluated_at=NOW)


@pytest.mark.asyncio
async def test_bounds_candidate_briefs_by_the_ordinary_budget() -> None:
    brief = _brief(resource_id_hex="a", statement="Revenue grew year over year.", excerpt="Revenue rose 12%.")
    captured: dict = {}

    class _CapturingReader(_Reader):
        async def read(self, **kwargs):
            captured.update(kwargs)
            return await super().read(**kwargs)

    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_CapturingReader(_brief_record(brief, resource_id="brief:revenue")),
            authority=_Authority(),
        )
    )
    await service.ask(_question(), evaluated_at=NOW)

    assert captured["query"].page_size == ASK_MAX_CANDIDATE_BRIEFS
    assert captured["query"].resource_kinds == (IntelligenceResourceKind.BRIEF,)


@pytest.mark.asyncio
async def test_refuses_when_a_question_shares_only_common_words_with_a_claim() -> None:
    """Sharing "the" is not coverage.

    Scoring on raw token overlap meant one stopword answered anything, so the
    honest no-answer guarantee held only while a corpus was empty. A question
    about something the corpus never mentions must still be refused when it
    happens to share ordinary English words with a claim.
    """

    brief = _brief(
        resource_id_hex="a",
        statement="The vault note records the current grind setting for the espresso routine.",
        excerpt="Grind setting is 14.",
    )
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_Reader(_brief_record(brief, resource_id="brief:vault")),
            authority=_Authority(),
        )
    )

    result = await service.ask(
        _question(question="Which harbour did the schooner depart from in the storm?"),
        evaluated_at=NOW,
    )

    assert isinstance(result, AskNoAnswerV1Alpha1)
    assert result.missing_coverage == ("missing_coverage:no_claims_matched_question_terms",)


@pytest.mark.asyncio
async def test_refuses_a_question_carrying_no_meaningful_terms_at_all() -> None:
    brief = _brief(resource_id_hex="a", statement="The vault note records the grind setting.", excerpt="14.")
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_Reader(_brief_record(brief, resource_id="brief:vault")),
            authority=_Authority(),
        )
    )

    result = await service.ask(_question(question="What about it, then?"), evaluated_at=NOW)

    assert isinstance(result, AskNoAnswerV1Alpha1)
    assert result.missing_coverage == ("missing_coverage:no_claims_matched_question_terms",)


@pytest.mark.asyncio
async def test_still_answers_when_the_question_shares_a_real_term() -> None:
    """The narrowing must not silence genuine coverage."""

    brief = _brief(
        resource_id_hex="a",
        statement="The vault note records the current grind setting for the espresso routine.",
        excerpt="Grind setting is 14.",
    )
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_Reader(_brief_record(brief, resource_id="brief:vault")),
            authority=_Authority(),
        )
    )

    result = await service.ask(_question(question="What grind setting am I using?"), evaluated_at=NOW)

    assert isinstance(result, AskAnswerV1Alpha1)
    assert result.claims == brief.claims
