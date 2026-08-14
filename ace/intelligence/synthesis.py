"""Pure validation and canonical rendering for structured Brief drafts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ace.intelligence.contracts.ledger import resource_reference
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    BriefV1Alpha1,
    CitationV1Alpha1,
    ClaimGroundingKind,
    GroundedClaimV1Alpha1,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageRelation,
    LineageResourceKind,
    ObservationV1Alpha1,
)
from ace.intelligence.contracts.synthesis import (
    BRIEF_SYNTHESIS_DRAFT_V1ALPHA2_VERSION,
    BRIEF_SYNTHESIS_DRAFT_VERSION,
    BriefCitationSupportBindingV1Alpha1,
    BriefClaimSupportBindingV1Alpha1,
    BriefSectionClaimBindingV1Alpha1,
    BriefSelectedContextBindingV1Alpha1,
    BriefSynthesisDraftV1Alpha1,
    BriefSynthesisDraftV1Alpha2,
    BriefTemplateV1,
    BriefTemplateV1Alpha2,
)
from ace.intelligence.packs.runtime import ResolvedBriefSynthesisPolicy

#: Draft contracts this validator understands. ``v1alpha2`` differs from
#: ``v1alpha1`` only by carrying a per-claim epistemic status binding, so both
#: share every structural, routing, and support rule below.
_DRAFT_MODELS = {
    BRIEF_SYNTHESIS_DRAFT_VERSION: BriefSynthesisDraftV1Alpha1,
    BRIEF_SYNTHESIS_DRAFT_V1ALPHA2_VERSION: BriefSynthesisDraftV1Alpha2,
}


class BriefDraftValidationError(ValueError):
    """Structured output does not satisfy exact template and support policy."""


@dataclass(frozen=True, slots=True)
class CanonicalBriefAssembly:
    """Purely derived Brief and content-free synthesis semantics."""

    brief: BriefV1Alpha1
    selected_context: tuple[BriefSelectedContextBindingV1Alpha1, ...]
    required_section_ids: tuple[str, ...]
    actual_section_ids: tuple[str, ...]
    section_claims: tuple[BriefSectionClaimBindingV1Alpha1, ...]
    recommendation_claim_id: str | None
    claim_supports: tuple[BriefClaimSupportBindingV1Alpha1, ...]


def validate_brief_synthesis_draft(
    *,
    draft: BriefSynthesisDraftV1Alpha1 | BriefSynthesisDraftV1Alpha2,
    policy: ResolvedBriefSynthesisPolicy,
    support_ids: tuple[str, ...],
    observation_ids: tuple[str, ...],
) -> BriefSynthesisDraftV1Alpha1 | BriefSynthesisDraftV1Alpha2:
    """Enforce exact structure, route policy, and support attribution."""

    model = _DRAFT_MODELS.get(getattr(draft, "contract", None))
    if model is None:
        raise BriefDraftValidationError("structured Brief draft uses an unsupported draft contract")
    try:
        validated = model.model_validate(draft.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise BriefDraftValidationError("structured Brief draft failed exact revalidation") from exc
    if validated.brief_type != policy.template.brief_type:
        raise BriefDraftValidationError("draft brief type does not match the exact routed template")
    if validated.persona_ids != tuple(item.persona_id for item in policy.personas):
        raise BriefDraftValidationError("draft personas do not match the exact routed personas")
    section_ids = tuple(item.section_id for item in validated.sections)
    if section_ids != policy.template.required_sections:
        raise BriefDraftValidationError("draft section IDs and order must exactly match the routed template")
    if policy.template.recommendation_required and validated.recommendation_claim_id is None:
        raise BriefDraftValidationError("routed template requires an explicit recommendation")
    if not policy.template.recommendation_required and validated.recommendation_claim_id is not None:
        raise BriefDraftValidationError("routed template does not permit a recommendation")
    claims_by_id = {str(claim.claim_id): claim for section in validated.sections for claim in section.claims}
    if validated.recommendation_claim_id is not None:
        recommendation = claims_by_id.get(validated.recommendation_claim_id)
        if recommendation is None:
            raise BriefDraftValidationError("recommendation claim ID is missing from ordered sections")
        if recommendation.grounding_kind is not ClaimGroundingKind.INFERENCE:
            raise BriefDraftValidationError("recommendation must identify an explicit inference claim")

    expected = set(support_ids)
    observations = set(observation_ids)
    used: set[str] = set()
    for section in validated.sections:
        for claim in section.claims:
            references = set(claim.support_refs)
            unknown = references - expected
            if unknown:
                raise BriefDraftValidationError(f"draft claim names unknown exact supports: {sorted(unknown)}")
            if claim.grounding_kind is ClaimGroundingKind.CITED:
                non_observations = references - observations
                if non_observations:
                    raise BriefDraftValidationError(
                        "cited draft claims may reference only exact persisted Observations"
                    )
            elif claim.uncertainty is None:
                raise BriefDraftValidationError("inference claims require explicit uncertainty")
            used.update(references)
    missing = expected - used
    if missing:
        raise BriefDraftValidationError(f"structured output left exact selected supports unused: {sorted(missing)}")
    return validated


_MARKDOWN = re.compile(r"([\\`*_{}\[\]()<>#+.!|~-])")


def _plain_text(value: str) -> str:
    """Render provider text as escaped plain text inside canonical Markdown."""

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(_MARKDOWN.sub(r"\\\1", line) for line in normalized.split("\n"))


def _heading(section_id: str) -> str:
    return section_id.replace("_", " ").replace("-", " ").title()


def render_canonical_brief_body(
    *,
    draft: BriefSynthesisDraftV1Alpha1 | BriefSynthesisDraftV1Alpha2,
    template: BriefTemplateV1 | BriefTemplateV1Alpha2,
) -> str:
    """Deterministically render canonical Markdown from validated structured fields."""

    summary = canonical_executive_summary(draft)
    lines = [f"# {_plain_text(template.display_name)}", "", _plain_text(summary)]
    for section in draft.sections:
        lines.extend(("", f"## {_heading(section.section_id)}", ""))
        for claim in section.claims:
            supports = ", ".join(_plain_text(item) for item in claim.support_refs)
            if claim.grounding_kind is ClaimGroundingKind.CITED:
                attribution = f"cited supports: {supports}"
            else:
                attribution = f"inference supports: {supports}; uncertainty: {_plain_text(str(claim.uncertainty))}"
            lines.append(f"- {_plain_text(claim.statement)} ({attribution})")
    return "\n".join(lines).rstrip() + "\n"


def canonical_executive_summary(draft: BriefSynthesisDraftV1Alpha1 | BriefSynthesisDraftV1Alpha2) -> str:
    """Derive summary prose only from validated grounded claim statements."""

    statements = [claim.statement for section in draft.sections for claim in section.claims]
    summary = " ".join(statements)
    if not summary or len(summary) > 8_000:
        raise BriefDraftValidationError("claim-derived executive summary exceeds Brief bounds")
    return summary


def _lineage(resource) -> LineageReferenceV1Alpha1:
    reference = resource_reference(resource)
    return LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind(reference.resource_kind.value),
        relation=LineageRelation.SUPPORTS,
        resource_id=reference.resource_id,
        resource_digest=reference.resource_digest,
        resource_as_of=reference.as_of,
        resource_available_at=reference.available_at,
    )


def _citation(observation: ObservationV1Alpha1) -> CitationV1Alpha1:
    source_as_of = observation.event_effective_at or observation.source_published_at or observation.observed_at
    return CitationV1Alpha1(
        source_ref=observation.source_ref,
        source_digest=observation.source_digest,
        acquisition_mode=observation.acquisition_mode,
        acquisition_receipt_ref=observation.acquisition_receipt_ref,
        acquisition_receipt_digest=observation.acquisition_receipt_digest,
        source_as_of=source_as_of,
        retrieved_at=observation.ingested_at,
        locator=None,
        excerpt=None,
    )


def assemble_canonical_brief(
    *,
    product_id: str,
    activation_revision: ActivationRevisionReferenceV1Alpha1,
    brief_as_of: datetime,
    generated_at: datetime,
    draft: BriefSynthesisDraftV1Alpha1 | BriefSynthesisDraftV1Alpha2,
    policy: ResolvedBriefSynthesisPolicy,
    closure: tuple,
    observations: tuple[ObservationV1Alpha1, ...],
    selected_context: tuple[BriefSelectedContextBindingV1Alpha1, ...],
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED,
) -> CanonicalBriefAssembly:
    """Derive all canonical Brief semantics from one validated Core draft."""

    validated = validate_brief_synthesis_draft(
        draft=draft,
        policy=policy,
        support_ids=tuple(str(item.resource_id) for item in closure),
        observation_ids=tuple(str(item.resource_id) for item in observations),
    )
    observations_by_id = {str(item.resource_id): item for item in observations}
    ordered_draft_claims = tuple(claim for section in validated.sections for claim in section.claims)
    cited_ids = {
        support
        for claim in ordered_draft_claims
        if claim.grounding_kind is ClaimGroundingKind.CITED
        for support in claim.support_refs
    }
    citations_by_support = {support: _citation(observations_by_id[support]) for support in sorted(cited_ids)}
    final_claims = tuple(
        GroundedClaimV1Alpha1(
            statement=claim.statement,
            grounding_kind=claim.grounding_kind,
            citation_ids=(
                tuple(sorted({str(citations_by_support[item].citation_id) for item in claim.support_refs}))
                if claim.grounding_kind is ClaimGroundingKind.CITED
                else ()
            ),
            inference_basis_refs=(claim.support_refs if claim.grounding_kind is ClaimGroundingKind.INFERENCE else ()),
            confidence=claim.confidence,
            uncertainty=claim.uncertainty,
        )
        for claim in ordered_draft_claims
    )
    final_claim_id_by_draft = {
        str(draft_claim.claim_id): str(final_claim.claim_id)
        for draft_claim, final_claim in zip(ordered_draft_claims, final_claims, strict=True)
    }
    brief = BriefV1Alpha1(
        product_id=product_id,
        mode=mode,
        activation_revision=activation_revision,
        as_of=brief_as_of,
        lineage=tuple(_lineage(item) for item in closure),
        brief_type_ref=policy.template.brief_type,
        title=policy.template.display_name,
        executive_summary=canonical_executive_summary(validated),
        body_markdown=render_canonical_brief_body(draft=validated, template=policy.template),
        generated_at=generated_at,
        citations=tuple({str(citation.citation_id): citation for citation in citations_by_support.values()}.values()),
        claims=final_claims,
    )
    return CanonicalBriefAssembly(
        brief=brief,
        selected_context=selected_context,
        required_section_ids=policy.template.required_sections,
        actual_section_ids=tuple(item.section_id for item in validated.sections),
        section_claims=tuple(
            BriefSectionClaimBindingV1Alpha1(
                section_id=section.section_id,
                claim_ids=tuple(final_claim_id_by_draft[str(claim.claim_id)] for claim in section.claims),
            )
            for section in validated.sections
        ),
        recommendation_claim_id=(
            final_claim_id_by_draft[validated.recommendation_claim_id]
            if validated.recommendation_claim_id is not None
            else None
        ),
        claim_supports=tuple(
            BriefClaimSupportBindingV1Alpha1(
                claim_id=str(final_claim.claim_id),
                grounding_kind=final_claim.grounding_kind,
                support_record_ids=draft_claim.support_refs,
                citation_ids=final_claim.citation_ids,
                citation_supports=(
                    tuple(
                        BriefCitationSupportBindingV1Alpha1(
                            support_record_id=support,
                            citation_id=str(citations_by_support[support].citation_id),
                        )
                        for support in draft_claim.support_refs
                    )
                    if final_claim.grounding_kind is ClaimGroundingKind.CITED
                    else ()
                ),
                inference_basis_refs=final_claim.inference_basis_refs,
            )
            for draft_claim, final_claim in zip(
                ordered_draft_claims,
                final_claims,
                strict=True,
            )
        ),
    )


__all__ = [
    "BriefDraftValidationError",
    "CanonicalBriefAssembly",
    "assemble_canonical_brief",
    "canonical_executive_summary",
    "render_canonical_brief_body",
    "validate_brief_synthesis_draft",
]
