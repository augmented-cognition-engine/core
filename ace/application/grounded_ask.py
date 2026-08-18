"""GroundedAskService — J7: answer questions only from authorized Brief claims."""

from __future__ import annotations

import re
from datetime import datetime

from ace.application.intelligence_resource_plane import (
    IntelligenceResourcePlaneError,
    IntelligenceResourcePlaneService,
)
from ace.intelligence.contracts.grounded_ask import AskAnswerV1Alpha1, AskNoAnswerV1Alpha1, AskQuestionV1Alpha1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import BriefV1Alpha1, ClaimGroundingKind, GroundedClaimV1Alpha1

ASK_MAX_CANDIDATE_BRIEFS = 50

_WORD = re.compile(r"[a-z0-9]+")


class GroundedAskError(RuntimeError):
    """A grounded Ask failed closed before exposing an unauthorized or uncited answer."""


def _exact_question(value: AskQuestionV1Alpha1) -> AskQuestionV1Alpha1:
    try:
        return AskQuestionV1Alpha1.model_validate(value.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise GroundedAskError("ask question failed exact revalidation") from exc


def _terms(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class GroundedAskService:
    """Answer one question from a principal's authorized Brief claims, or refuse honestly."""

    def __init__(self, *, resource_plane: IntelligenceResourcePlaneService) -> None:
        self.resource_plane = resource_plane

    async def ask(
        self,
        value: AskQuestionV1Alpha1,
        *,
        evaluated_at: datetime,
    ) -> AskAnswerV1Alpha1 | AskNoAnswerV1Alpha1:
        request = _exact_question(value)
        question_terms = _terms(request.question)

        query = IntelligenceResourceQueryV1Alpha1(
            authenticated_context=request.authenticated_context,
            product_id=request.product_id,
            authority_grant_ref=request.authority_grant_ref,
            resource_kinds=(IntelligenceResourceKind.BRIEF,),
            subject_refs=request.subject_refs,
            as_of=request.as_of,
            available_at=request.available_at,
            page_size=ASK_MAX_CANDIDATE_BRIEFS,
        )
        try:
            page = await self.resource_plane.query(query, evaluated_at=evaluated_at)
        except IntelligenceResourcePlaneError as exc:
            raise GroundedAskError("authorized Brief retrieval failed closed") from exc

        considered: list[IntelligenceResourceReferenceV1Alpha1] = []
        scored: list[tuple[int, GroundedClaimV1Alpha1, BriefV1Alpha1, IntelligenceResourceReferenceV1Alpha1]] = []
        for item in page.items:
            if item.availability is not IntelligenceResourceAvailability.AVAILABLE or item.payload is None:
                continue
            considered.append(item.reference)
            try:
                brief = BriefV1Alpha1.model_validate_json(item.payload.value_json)
            except (TypeError, ValueError):
                continue
            for claim in brief.claims:
                if claim.grounding_kind is not ClaimGroundingKind.CITED:
                    continue
                score = len(question_terms & _terms(claim.statement))
                if score > 0:
                    scored.append((score, claim, brief, item.reference))

        scored.sort(key=lambda entry: (-entry[0], -entry[1].confidence, str(entry[1].claim_id)))
        selected = scored[: request.max_claims]

        if not selected:
            missing_coverage = (
                ("missing_coverage:no_authorized_brief_resources_available",)
                if not considered
                else ("missing_coverage:no_claims_matched_question_terms",)
            )
            return AskNoAnswerV1Alpha1(
                question=request.question,
                product_id=request.product_id,
                actor_ref=request.authenticated_context.actor_ref,
                missing_coverage=missing_coverage,
                considered_briefs=tuple(considered),
                evaluated_at=evaluated_at,
                authority_use=page.authority_use,
            )

        selected_claims = tuple(entry[1] for entry in selected)
        citations_by_id = {
            citation.citation_id: citation for _, _, brief, _ in selected for citation in brief.citations
        }
        used_citation_ids = {citation_id for claim in selected_claims for citation_id in claim.citation_ids}
        selected_citations = tuple(
            citations_by_id[citation_id] for citation_id in used_citation_ids if citation_id in citations_by_id
        )
        if len(selected_citations) != len(used_citation_ids):
            raise GroundedAskError("selected claim citations could not be resolved on their source Brief")
        source_briefs = tuple({entry[3] for entry in selected})

        return AskAnswerV1Alpha1(
            question=request.question,
            product_id=request.product_id,
            actor_ref=request.authenticated_context.actor_ref,
            claims=selected_claims,
            citations=selected_citations,
            source_briefs=source_briefs,
            answered_at=evaluated_at,
            authority_use=page.authority_use,
        )


__all__ = [
    "ASK_MAX_CANDIDATE_BRIEFS",
    "GroundedAskError",
    "GroundedAskService",
]
