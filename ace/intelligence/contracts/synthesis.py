"""Declarative Brief policy and structured PREPARED synthesis contracts."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.reasoning import (
    ContextBindingV1Alpha1,
    ReceiptReferenceV1Alpha1,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    normalized_strings,
    sorted_unique,
    validate_slug,
)
from ace.intelligence.contracts.epistemic import (
    BriefDraftClaimStatusBindingV1Alpha1,
    BriefEpistemicStatusProjectionV1Alpha1,
    BriefEpistemicStatusProjectionV1Alpha2,
)
from ace.intelligence.contracts.ledger import (
    IntelligenceRecordKind,
    IntelligenceRecordReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    BriefV1Alpha1,
    ClaimGroundingKind,
    IntelligenceResourceMode,
)

SYNTHESIS_MODULE_VERSION = "ace.intelligence.synthesis/v1alpha1"
SYNTHESIS_MODULE_V1ALPHA2_VERSION = "ace.intelligence.synthesis/v1alpha2"
BRIEF_SYNTHESIS_REQUEST_VERSION = "ace.intelligence.brief-synthesis-request/v1alpha1"
BRIEF_DRAFT_CLAIM_VERSION = "ace.intelligence.brief-draft-claim/v1alpha1"
BRIEF_DRAFT_SECTION_VERSION = "ace.intelligence.brief-draft-section/v1alpha1"
BRIEF_SYNTHESIS_DRAFT_VERSION = "ace.intelligence.brief-synthesis-draft/v1alpha1"
BRIEF_CITATION_SUPPORT_BINDING_VERSION = "ace.intelligence.brief-citation-support-binding/v1alpha1"
BRIEF_CLAIM_SUPPORT_BINDING_VERSION = "ace.intelligence.brief-claim-support-binding/v1alpha1"
BRIEF_SELECTED_CONTEXT_BINDING_VERSION = "ace.intelligence.brief-selected-context-binding/v1alpha1"
BRIEF_SECTION_CLAIM_BINDING_VERSION = "ace.intelligence.brief-section-claim-binding/v1alpha1"
BRIEF_SYNTHESIS_RECEIPT_VERSION = "ace.intelligence.brief-synthesis-receipt/v1alpha1"
PREPARED_BRIEF_APPEND_VERSION = "ace.intelligence.prepared-brief-append/v1alpha1"
PREPARED_BRIEF_APPEND_INTENT_VERSION = "ace.intelligence.prepared-brief-append-intent/v1alpha1"
PREPARED_BRIEF_APPEND_RECIPE_VERSION = "ace.intelligence.prepared-brief-append-recipe/v1alpha1"
CASE_MEMBER_ATTENTION_BINDING_VERSION = "ace.intelligence.case-member-attention-binding/v1alpha1"
CASE_BRIEF_SYNTHESIS_REQUEST_VERSION = "ace.intelligence.case-brief-synthesis-request/v1alpha1"
CASE_BRIEF_SYNTHESIS_RECEIPT_VERSION = "ace.intelligence.case-brief-synthesis-receipt/v1alpha1"
PREPARED_CASE_BRIEF_APPEND_VERSION = "ace.intelligence.prepared-case-brief-append/v1alpha1"
PREPARED_CASE_BRIEF_APPEND_INTENT_VERSION = "ace.intelligence.prepared-case-brief-append-intent/v1alpha1"
PREPARED_CASE_BRIEF_APPEND_RECIPE_VERSION = "ace.intelligence.prepared-case-brief-append-recipe/v1alpha1"
INITIAL_CORPUS_BRIEF_SYNTHESIS_REQUEST_VERSION = "ace.intelligence.initial-corpus-brief-synthesis-request/v1alpha1"
INITIAL_CORPUS_BRIEF_SYNTHESIS_RECEIPT_VERSION = "ace.intelligence.initial-corpus-brief-synthesis-receipt/v1alpha1"
PREPARED_INITIAL_CORPUS_BRIEF_APPEND_VERSION = "ace.intelligence.prepared-initial-corpus-brief-append/v1alpha1"
PREPARED_INITIAL_CORPUS_BRIEF_APPEND_INTENT_VERSION = (
    "ace.intelligence.prepared-initial-corpus-brief-append-intent/v1alpha1"
)
PREPARED_INITIAL_CORPUS_BRIEF_APPEND_RECIPE_VERSION = (
    "ace.intelligence.prepared-initial-corpus-brief-append-recipe/v1alpha1"
)
BRIEF_SYNTHESIS_DRAFT_V1ALPHA2_VERSION = "ace.intelligence.brief-synthesis-draft/v1alpha2"
PREPARED_STATUS_CASE_BRIEF_APPEND_VERSION = "ace.intelligence.prepared-status-case-brief-append/v1alpha1"
PREPARED_STATUS_CASE_BRIEF_APPEND_INTENT_VERSION = "ace.intelligence.prepared-status-case-brief-append-intent/v1alpha1"
PREPARED_STATUS_CASE_BRIEF_APPEND_RECIPE_VERSION = "ace.intelligence.prepared-status-case-brief-append-recipe/v1alpha1"
PREPARED_FAMILY_STATUS_CASE_BRIEF_APPEND_VERSION = "ace.intelligence.prepared-family-status-case-brief-append/v1alpha1"
PREPARED_FAMILY_STATUS_CASE_BRIEF_APPEND_INTENT_VERSION = (
    "ace.intelligence.prepared-family-status-case-brief-append-intent/v1alpha1"
)
PREPARED_FAMILY_STATUS_CASE_BRIEF_APPEND_RECIPE_VERSION = (
    "ace.intelligence.prepared-family-status-case-brief-append-recipe/v1alpha1"
)


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _reference(value: str, *, name: str) -> str:
    if not value or value != value.strip() or len(value) > 240:
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def _digest(value: str, *, name: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:") or value != value.lower():
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax") from exc
    return value


def _derive_identity(instance: _StrictFrozenContract, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact synthesis material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact synthesis material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class BriefTemplateV1(FrozenContract):
    """Legacy structural Brief policy with lexically canonicalized sections.

    ``ace.intelligence.synthesis/v1alpha1`` historically treated
    ``required_sections`` as a set-like declaration.  Its lexical normalization
    is therefore part of the immutable contract identity and must not be
    reinterpreted as declaration order.
    """

    template_id: str
    brief_type: str
    display_name: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=2_000)
    required_sections: tuple[str, ...] = Field(min_length=1, max_length=32)
    recommendation_required: StrictBool = True
    claim_policy: Literal["citation_or_explicit_inference"] = "citation_or_explicit_inference"

    @field_validator("template_id", "brief_type")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("required_sections", mode="before")
    @classmethod
    def normalize_sections(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="required section")
            for item in normalized_strings(
                value,
                label="required sections",
                maximum=32,
            )
        )


class BriefTemplateV1Alpha2(FrozenContract):
    """Ordered structural Brief policy for synthesis ``v1alpha2``."""

    template_id: str
    brief_type: str
    display_name: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=2_000)
    required_sections: tuple[str, ...] = Field(min_length=1, max_length=32)
    recommendation_required: StrictBool = True
    claim_policy: Literal["citation_or_explicit_inference"] = "citation_or_explicit_inference"

    @field_validator("template_id", "brief_type")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("required_sections", mode="before")
    @classmethod
    def normalize_sections(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("required sections must be an ordered collection")
        if not value or len(value) > 32:
            raise ValueError("required sections must contain between 1 and 32 items")
        validated = tuple(validate_slug(item, name="required section") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("required sections must be unique")
        return validated


class SynthesisModuleV1(FrozenContract):
    """One immutable legacy module of domain-owned Brief structures."""

    contract: Literal["ace.intelligence.synthesis/v1alpha1"] = SYNTHESIS_MODULE_VERSION
    module_id: str
    brief_templates: tuple[BriefTemplateV1, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("brief_templates")
    @classmethod
    def normalize_templates(
        cls,
        value: tuple[BriefTemplateV1, ...],
    ) -> tuple[BriefTemplateV1, ...]:
        return sorted_unique(value, key=lambda item: item.template_id, label="Brief templates")


class SynthesisModuleV1Alpha2(FrozenContract):
    """One immutable ordered-section module of domain-owned Brief structures."""

    contract: Literal["ace.intelligence.synthesis/v1alpha2"] = SYNTHESIS_MODULE_V1ALPHA2_VERSION
    module_id: str
    brief_templates: tuple[BriefTemplateV1Alpha2, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("brief_templates")
    @classmethod
    def normalize_templates(
        cls,
        value: tuple[BriefTemplateV1Alpha2, ...],
    ) -> tuple[BriefTemplateV1Alpha2, ...]:
        return sorted_unique(value, key=lambda item: item.template_id, label="Brief templates")


class BriefSynthesisRequestV1Alpha1(_StrictFrozenContract):
    """One exact mode-bound route-triggered Brief request."""

    contract: Literal["ace.intelligence.brief-synthesis-request/v1alpha1"] = BRIEF_SYNTHESIS_REQUEST_VERSION
    synthesis_key: str
    reasoning_attempt_key: str
    derivation_key: str
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    activation_revision: ActivationRevisionReferenceV1Alpha1
    pack: CompiledPackRefV1
    attention_receipt_id: str
    attention_receipt_digest: str
    brief_as_of: datetime
    context_cutoff_at: datetime
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator(
        "synthesis_key",
        "reasoning_attempt_key",
        "derivation_key",
        "product_id",
        "attention_receipt_id",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("attention_receipt_digest", "request_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("brief_as_of", "context_cutoff_at", "requested_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        return _reference(value, name="request_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or self.activation_revision.product_id != self.product_id
        ):
            raise ValueError("Brief synthesis request crossed exact product scope")
        if self.brief_as_of != self.context_cutoff_at:
            raise ValueError("Brief as_of must equal its frozen analysis and evidence cutoff")
        if self.context_cutoff_at > self.requested_at:
            raise ValueError("Brief analysis and evidence cutoff cannot follow request time")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("Brief synthesis request must occur inside the authenticated window")
        _derive_identity(
            self,
            prefix="brief_synthesis_request",
            id_field="request_id",
            digest_field="request_digest",
        )
        return self


class BriefDraftClaimV1Alpha1(_StrictFrozenContract):
    """One structured draft claim with exact selected-support attribution."""

    contract: Literal["ace.intelligence.brief-draft-claim/v1alpha1"] = BRIEF_DRAFT_CLAIM_VERSION
    statement: str = Field(min_length=1, max_length=4_000)
    grounding_kind: ClaimGroundingKind
    support_refs: tuple[str, ...] = Field(min_length=1, max_length=64)
    confidence: float
    uncertainty: str | None = Field(default=None, min_length=1, max_length=2_000)
    claim_id: str | None = None
    claim_digest: str | None = None

    @field_validator("support_refs")
    @classmethod
    def normalize_support_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_reference(item, name="support_ref") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("draft claim support references must be unique")
        return tuple(sorted(validated))

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float:
        if type(value) is not float or not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("draft claim confidence must be a finite float between 0.0 and 1.0")
        return value

    @field_validator("claim_id")
    @classmethod
    def validate_claim_id(cls, value: str | None) -> str | None:
        return _reference(value, name="claim_id") if value is not None else None

    @field_validator("claim_digest")
    @classmethod
    def validate_claim_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="claim_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_grounding_and_identity(self) -> Self:
        if self.grounding_kind is ClaimGroundingKind.INFERENCE and self.uncertainty is None:
            raise ValueError("an inference draft claim requires explicit uncertainty")
        _derive_identity(
            self,
            prefix="brief_draft_claim",
            id_field="claim_id",
            digest_field="claim_digest",
        )
        return self


class BriefDraftSectionV1Alpha1(_StrictFrozenContract):
    """One ordered template section from structured provider output."""

    contract: Literal["ace.intelligence.brief-draft-section/v1alpha1"] = BRIEF_DRAFT_SECTION_VERSION
    section_id: str
    claims: tuple[BriefDraftClaimV1Alpha1, ...] = Field(min_length=1, max_length=128)

    @field_validator("section_id")
    @classmethod
    def validate_section_id(cls, value: str) -> str:
        return validate_slug(value, name="section_id")

    @field_validator("claims")
    @classmethod
    def validate_claims(
        cls,
        value: tuple[BriefDraftClaimV1Alpha1, ...],
    ) -> tuple[BriefDraftClaimV1Alpha1, ...]:
        ids = [item.claim_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("section draft claims must use unique identities")
        return value


class BriefSynthesisDraftV1Alpha1(_StrictFrozenContract):
    """Provider-neutral structured draft; canonical Markdown is not accepted here."""

    contract: Literal["ace.intelligence.brief-synthesis-draft/v1alpha1"] = BRIEF_SYNTHESIS_DRAFT_VERSION
    brief_type: str
    persona_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    sections: tuple[BriefDraftSectionV1Alpha1, ...] = Field(min_length=1, max_length=32)
    recommendation_claim_id: str | None = None
    draft_id: str | None = None
    draft_digest: str | None = None

    @field_validator("brief_type")
    @classmethod
    def validate_brief_type(cls, value: str) -> str:
        return validate_slug(value, name="brief_type")

    @field_validator("persona_ids")
    @classmethod
    def normalize_personas(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name="persona_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("draft personas must be unique")
        return tuple(sorted(validated))

    @field_validator("sections")
    @classmethod
    def validate_sections(
        cls,
        value: tuple[BriefDraftSectionV1Alpha1, ...],
    ) -> tuple[BriefDraftSectionV1Alpha1, ...]:
        ids = [item.section_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("draft section IDs must be unique")
        claim_ids = [claim.claim_id for section in value for claim in section.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("draft claim identities must be unique across sections")
        return value

    @field_validator("draft_id")
    @classmethod
    def validate_draft_id(cls, value: str | None) -> str | None:
        return _reference(value, name="draft_id") if value is not None else None

    @field_validator("draft_digest")
    @classmethod
    def validate_draft_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="draft_digest") if value is not None else None

    @field_validator("recommendation_claim_id")
    @classmethod
    def validate_recommendation_claim_id(cls, value: str | None) -> str | None:
        return _reference(value, name="recommendation_claim_id") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive_identity(
            self,
            prefix="brief_synthesis_draft",
            id_field="draft_id",
            digest_field="draft_digest",
        )
        return self


class BriefSynthesisDraftV1Alpha2(_StrictFrozenContract):
    """Status-aware structured draft: one declared status per ordered draft claim.

    This is the additive sibling of :class:`BriefSynthesisDraftV1Alpha1`. It
    reuses ``BriefDraftSectionV1Alpha1``/``BriefDraftClaimV1Alpha1`` verbatim so
    their canonical identities are untouched, and carries status only as a
    separate machine-readable binding keyed by exact draft claim identity.
    Status is therefore never inferred from section placement or Markdown.
    """

    contract: Literal["ace.intelligence.brief-synthesis-draft/v1alpha2"] = BRIEF_SYNTHESIS_DRAFT_V1ALPHA2_VERSION
    brief_type: str
    persona_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    sections: tuple[BriefDraftSectionV1Alpha1, ...] = Field(min_length=1, max_length=32)
    claim_statuses: tuple[BriefDraftClaimStatusBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=1_024,
    )
    recommendation_claim_id: str | None = None
    draft_id: str | None = None
    draft_digest: str | None = None

    @field_validator("brief_type")
    @classmethod
    def validate_brief_type(cls, value: str) -> str:
        return validate_slug(value, name="brief_type")

    @field_validator("persona_ids")
    @classmethod
    def normalize_personas(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name="persona_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("draft personas must be unique")
        return tuple(sorted(validated))

    @field_validator("sections")
    @classmethod
    def validate_sections(
        cls,
        value: tuple[BriefDraftSectionV1Alpha1, ...],
    ) -> tuple[BriefDraftSectionV1Alpha1, ...]:
        ids = [item.section_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("draft section IDs must be unique")
        claim_ids = [claim.claim_id for section in value for claim in section.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("draft claim identities must be unique across sections")
        return value

    @field_validator("claim_statuses")
    @classmethod
    def normalize_claim_statuses(
        cls,
        value: tuple[BriefDraftClaimStatusBindingV1Alpha1, ...],
    ) -> tuple[BriefDraftClaimStatusBindingV1Alpha1, ...]:
        ids = [item.draft_claim_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("a draft claim must not be bound to more than one status")
        return tuple(sorted(value, key=lambda item: item.draft_claim_id))

    @field_validator("draft_id")
    @classmethod
    def validate_draft_id(cls, value: str | None) -> str | None:
        return _reference(value, name="draft_id") if value is not None else None

    @field_validator("draft_digest")
    @classmethod
    def validate_draft_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="draft_digest") if value is not None else None

    @field_validator("recommendation_claim_id")
    @classmethod
    def validate_recommendation_claim_id(cls, value: str | None) -> str | None:
        return _reference(value, name="recommendation_claim_id") if value is not None else None

    @model_validator(mode="after")
    def validate_status_coverage_and_identity(self) -> Self:
        claim_ids = {str(claim.claim_id) for section in self.sections for claim in section.claims}
        bound = {item.draft_claim_id for item in self.claim_statuses}
        if bound != claim_ids:
            raise ValueError("a status-aware draft must bind exactly one declared status to every ordered draft claim")
        _derive_identity(
            self,
            prefix="brief_synthesis_draft_v1alpha2",
            id_field="draft_id",
            digest_field="draft_digest",
        )
        return self


class BriefCitationSupportBindingV1Alpha1(_StrictFrozenContract):
    """One exact selected Observation record to its derived citation identity."""

    contract: Literal["ace.intelligence.brief-citation-support-binding/v1alpha1"] = (
        BRIEF_CITATION_SUPPORT_BINDING_VERSION
    )
    support_record_id: str
    citation_id: str

    @field_validator("support_record_id", "citation_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)


class BriefClaimSupportBindingV1Alpha1(_StrictFrozenContract):
    """Content-free final claim grounding coordinates for synthesis audit."""

    contract: Literal["ace.intelligence.brief-claim-support-binding/v1alpha1"] = BRIEF_CLAIM_SUPPORT_BINDING_VERSION
    claim_id: str
    grounding_kind: ClaimGroundingKind
    support_record_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    citation_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    citation_supports: tuple[BriefCitationSupportBindingV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=64,
    )
    inference_basis_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=64)

    @field_validator("claim_id")
    @classmethod
    def validate_claim_id(cls, value: str) -> str:
        return _reference(value, name="claim_id")

    @field_validator("support_record_ids", "citation_ids", "inference_basis_refs")
    @classmethod
    def normalize_supports(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        validated = tuple(_reference(item, name=info.field_name) for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError(f"{info.field_name} must use unique exact identities")
        return tuple(sorted(validated))

    @model_validator(mode="after")
    def validate_grounding_shape(self) -> Self:
        mapped_supports = tuple(item.support_record_id for item in self.citation_supports)
        mapped_citations = tuple(sorted({item.citation_id for item in self.citation_supports}))
        if len(mapped_supports) != len(set(mapped_supports)):
            raise ValueError("citation support mappings must bind each Observation once")
        if self.grounding_kind is ClaimGroundingKind.CITED:
            if (
                not self.citation_ids
                or self.inference_basis_refs
                or tuple(sorted(mapped_supports)) != self.support_record_ids
                or mapped_citations != self.citation_ids
            ):
                raise ValueError("cited claim binding requires only exact citation identities")
        elif (
            not self.inference_basis_refs
            or self.citation_ids
            or self.citation_supports
            or self.inference_basis_refs != self.support_record_ids
        ):
            raise ValueError("inference claim binding requires only exact basis resource identities")
        return self


class BriefSelectedContextBindingV1Alpha1(_StrictFrozenContract):
    """Exact Intelligence record to opaque Core context identity mapping."""

    contract: Literal["ace.intelligence.brief-selected-context-binding/v1alpha1"] = (
        BRIEF_SELECTED_CONTEXT_BINDING_VERSION
    )
    record: IntelligenceRecordReferenceV1Alpha1
    context: ContextBindingV1Alpha1

    @model_validator(mode="after")
    def validate_times(self) -> Self:
        if self.record.as_of != self.context.as_of or self.record.available_at != self.context.available_at:
            raise ValueError("selected record and Core context binding must preserve exact times")
        return self


class BriefSectionClaimBindingV1Alpha1(_StrictFrozenContract):
    """Ordered content-free claim membership for one required section."""

    contract: Literal["ace.intelligence.brief-section-claim-binding/v1alpha1"] = BRIEF_SECTION_CLAIM_BINDING_VERSION
    section_id: str
    claim_ids: tuple[str, ...] = Field(min_length=1, max_length=128)

    @field_validator("section_id")
    @classmethod
    def validate_section_id(cls, value: str) -> str:
        return validate_slug(value, name="section_id")

    @field_validator("claim_ids")
    @classmethod
    def validate_claim_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_reference(item, name="claim_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("section claim identities must be unique")
        return validated


class BriefSynthesisReceiptV1Alpha1(_StrictFrozenContract):
    """Durable semantic correlation for one canonical mode-bound Brief."""

    contract: Literal["ace.intelligence.brief-synthesis-receipt/v1alpha1"] = BRIEF_SYNTHESIS_RECEIPT_VERSION
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    synthesis_key: str
    reasoning_attempt_key: str
    request_id: str
    request_digest: str
    reasoning_request_id: str
    reasoning_request_digest: str
    activation_revision: ActivationRevisionReferenceV1Alpha1
    activation_commit: ReceiptReferenceV1Alpha1
    pack: CompiledPackRefV1
    derivation_key: str
    attention_receipt_id: str
    attention_receipt_digest: str
    module_id: str
    module_digest: str
    template_id: str
    template_digest: str
    persona_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    required_section_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    actual_section_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    section_claims: tuple[BriefSectionClaimBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=32,
    )
    recommendation_claim_id: str | None = None
    claim_supports: tuple[BriefClaimSupportBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=256,
    )
    selected_context: tuple[BriefSelectedContextBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=256,
    )
    write_intent_id: str
    write_intent_digest: str
    write_authorization: ReceiptReferenceV1Alpha1
    reasoning_terminal: ReceiptReferenceV1Alpha1
    reasoning_result_id: str
    reasoning_result_digest: str
    brief_id: str
    brief_digest: str
    created_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "product_id",
        "synthesis_key",
        "reasoning_attempt_key",
        "request_id",
        "reasoning_request_id",
        "derivation_key",
        "attention_receipt_id",
        "reasoning_result_id",
        "brief_id",
        "write_intent_id",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("module_id", "template_id")
    @classmethod
    def validate_slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator(
        "request_digest",
        "reasoning_request_digest",
        "attention_receipt_digest",
        "module_digest",
        "template_digest",
        "reasoning_result_digest",
        "brief_digest",
        "write_intent_digest",
        "receipt_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("persona_ids")
    @classmethod
    def normalize_personas(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name="persona_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("synthesis receipt personas must be unique")
        return tuple(sorted(validated))

    @field_validator("required_section_ids", "actual_section_ids")
    @classmethod
    def validate_section_ids(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name=info.field_name) for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError(f"{info.field_name} must be unique")
        return validated

    @field_validator("claim_supports")
    @classmethod
    def validate_claim_supports(
        cls,
        value: tuple[BriefClaimSupportBindingV1Alpha1, ...],
    ) -> tuple[BriefClaimSupportBindingV1Alpha1, ...]:
        ids = [item.claim_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("synthesis receipt claim support bindings must be unique")
        return value

    @field_validator("section_claims")
    @classmethod
    def validate_section_claims(
        cls,
        value: tuple[BriefSectionClaimBindingV1Alpha1, ...],
    ) -> tuple[BriefSectionClaimBindingV1Alpha1, ...]:
        ids = [item.section_id for item in value]
        claim_ids = [claim_id for item in value for claim_id in item.claim_ids]
        if len(ids) != len(set(ids)) or len(claim_ids) != len(set(claim_ids)):
            raise ValueError("section and claim membership must be unique")
        return value

    @field_validator("recommendation_claim_id")
    @classmethod
    def validate_recommendation_claim_id(cls, value: str | None) -> str | None:
        return _reference(value, name="recommendation_claim_id") if value is not None else None

    @field_validator("selected_context")
    @classmethod
    def normalize_context_bindings(
        cls,
        value: tuple[BriefSelectedContextBindingV1Alpha1, ...],
    ) -> tuple[BriefSelectedContextBindingV1Alpha1, ...]:
        record_ids = [item.record.resource_id for item in value]
        context_ids = [item.context.context_id for item in value]
        if len(record_ids) != len(set(record_ids)) or len(context_ids) != len(set(context_ids)):
            raise ValueError("synthesis receipt record and context mappings must be one-to-one")
        return tuple(sorted(value, key=lambda item: (item.record.resource_kind.value, item.record.resource_id)))

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware(value, name="created_at")

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return _reference(value, name="receipt_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("synthesis receipt activation crossed exact product scope")
        if self.actual_section_ids != self.required_section_ids:
            raise ValueError("synthesis receipt section order must exactly conform to required policy")
        if tuple(item.section_id for item in self.section_claims) != self.actual_section_ids:
            raise ValueError("synthesis receipt section claim membership crossed exact section order")
        bound_claim_ids = tuple(item.claim_id for item in self.claim_supports)
        section_claim_ids = tuple(claim_id for item in self.section_claims for claim_id in item.claim_ids)
        if bound_claim_ids != section_claim_ids:
            raise ValueError("synthesis receipt must bind every ordered section claim exactly once")
        if self.recommendation_claim_id is not None and self.recommendation_claim_id not in bound_claim_ids:
            raise ValueError("recommendation claim must identify one exact ordered section claim")
        selected_ids = {item.record.resource_id for item in self.selected_context}
        if any(
            item.record.product_id != self.product_id or item.record.mode is not self.mode
            for item in self.selected_context
        ):
            raise ValueError("selected context records crossed product or mode scope")
        support_ids = {support for item in self.claim_supports for support in item.support_record_ids}
        if support_ids != selected_ids:
            raise ValueError("claim support bindings must use every exact selected context record")
        if not self.brief_id.startswith("brief:"):
            raise ValueError("synthesis receipt must bind one exact Brief identity")
        _derive_identity(
            self,
            prefix="brief_synthesis_receipt",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


class PreparedBriefAppendRecordRecipeV1Alpha1(_StrictFrozenContract):
    """One ordered record in the authorization-reference/time derivation recipe."""

    record_kind: Literal["brief", "brief_synthesis_receipt"]
    payload_contract: str
    record_key_derivation: str
    payload_digest_derivation: str
    as_of_derivation: str
    available_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    processing_order: int = Field(ge=0, le=1)

    @field_validator(
        "payload_contract",
        "record_key_derivation",
        "payload_digest_derivation",
        "as_of_derivation",
    )
    @classmethod
    def validate_recipe_values(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)


class PreparedBriefAppendIntentV1Alpha1(_StrictFrozenContract):
    """Exact pre-authorization recipe that explicitly breaks the auth-ref/time cycle."""

    contract: Literal["ace.intelligence.prepared-brief-append-intent/v1alpha1"] = PREPARED_BRIEF_APPEND_INTENT_VERSION
    recipe_contract: Literal["ace.intelligence.prepared-brief-append-recipe/v1alpha1"] = (
        PREPARED_BRIEF_APPEND_RECIPE_VERSION
    )
    product_id: str
    record_space: Literal["prepared"] = "prepared"
    transaction_key: str
    semantic_input_digest: str
    authorization_operation: Literal["append_immutable_records"] = "append_immutable_records"
    authorization_reference_insertion: Literal["synthesis_receipt.write_authorization"] = (
        "synthesis_receipt.write_authorization"
    )
    timestamp_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    submitted_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    records: tuple[PreparedBriefAppendRecordRecipeV1Alpha1, ...] = Field(
        min_length=2,
        max_length=2,
    )
    governed_state_identities: tuple[str, ...] = Field(min_length=4, max_length=64)
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator("product_id", "transaction_key", "governed_state_identities")
    @classmethod
    def validate_references(cls, value, info):
        if info.field_name == "governed_state_identities":
            validated = tuple(_reference(item, name="governed_state_identity") for item in value)
            if len(validated) != len(set(validated)):
                raise ValueError("governed state identities must be unique")
            return tuple(sorted(validated))
        return _reference(value, name=info.field_name)

    @field_validator("semantic_input_digest", "intent_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("intent_id")
    @classmethod
    def validate_intent_id(cls, value: str | None) -> str | None:
        return _reference(value, name="intent_id") if value is not None else None

    @model_validator(mode="after")
    def validate_recipe_and_identity(self) -> Self:
        actual = tuple(
            (
                item.record_kind,
                item.payload_contract,
                item.record_key_derivation,
                item.payload_digest_derivation,
                item.as_of_derivation,
                item.available_at_derivation,
                item.processing_order,
            )
            for item in self.records
        )
        expected = (
            (
                "brief",
                "ace.intelligence.brief/v1alpha1",
                "brief.resource_id_from_authorized_at",
                "brief.canonical_payload_from_intent_and_authorized_at",
                "request.brief_as_of",
                "authorization.authorized_at",
                0,
            ),
            (
                "brief_synthesis_receipt",
                "ace.intelligence.brief-synthesis-receipt/v1alpha1",
                "receipt.receipt_id_from_authorization_reference_and_authorized_at",
                "receipt.canonical_payload_from_intent_authorization_and_authorized_at",
                "authorization.authorized_at",
                "authorization.authorized_at",
                1,
            ),
        )
        if actual != expected:
            raise ValueError("prepared Brief append recipe must contain exactly two ordered records")
        _derive_identity(
            self,
            prefix="prepared_brief_append_intent",
            id_field="intent_id",
            digest_field="intent_digest",
        )
        return self


class PreparedBriefAppendV1Alpha1(_StrictFrozenContract):
    """Separate second-phase append containing exactly one Brief and receipt."""

    contract: Literal["ace.intelligence.prepared-brief-append/v1alpha1"] = PREPARED_BRIEF_APPEND_VERSION
    synthesis_key: str
    request_id: str
    request_digest: str
    brief: BriefV1Alpha1
    synthesis_receipt: BriefSynthesisReceiptV1Alpha1
    submitted_at: datetime
    append_id: str | None = None
    append_digest: str | None = None

    @field_validator("synthesis_key", "request_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("request_digest", "append_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, value: datetime) -> datetime:
        return _aware(value, name="submitted_at")

    @field_validator("append_id")
    @classmethod
    def validate_append_id(cls, value: str | None) -> str | None:
        return _reference(value, name="append_id") if value is not None else None

    @model_validator(mode="after")
    def validate_exact_pair_and_identity(self) -> Self:
        receipt = self.synthesis_receipt
        if (
            self.brief.mode is not IntelligenceResourceMode.PREPARED
            or self.brief.product_id != receipt.product_id
            or self.brief.activation_revision != receipt.activation_revision
            or self.brief.resource_id != receipt.brief_id
            or self.brief.resource_digest != receipt.brief_digest
            or self.synthesis_key != receipt.synthesis_key
            or self.request_id != receipt.request_id
            or self.request_digest != receipt.request_digest
            or self.submitted_at != receipt.created_at
            or self.brief.generated_at != self.submitted_at
        ):
            raise ValueError("prepared Brief append does not bind its exact synthesis receipt")
        _derive_identity(
            self,
            prefix="prepared_brief_append",
            id_field="append_id",
            digest_field="append_digest",
        )
        return self


class CaseMemberAttentionBindingV1Alpha1(_StrictFrozenContract):
    """One exact Case Signal member bound to its exact routed attention receipt.

    Case-bound synthesis never re-evaluates routing. Each Signal member of the
    frozen Case must be presented with the exact durable derivation and
    attention receipt that admitted it, so the caller cannot silently swap a
    suppressed Signal for a routed one or attach an unrelated route.
    """

    contract: Literal["ace.intelligence.case-member-attention-binding/v1alpha1"] = CASE_MEMBER_ATTENTION_BINDING_VERSION
    signal_resource_id: str
    derivation_key: str
    attention_receipt_id: str
    attention_receipt_digest: str

    @field_validator("signal_resource_id", "derivation_key", "attention_receipt_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("attention_receipt_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _digest(value, name="attention_receipt_digest")

    @model_validator(mode="after")
    def validate_member_kind(self) -> Self:
        if not self.signal_resource_id.startswith(f"{IntelligenceRecordKind.SIGNAL.value}:"):
            raise ValueError("case member attention binding must name one exact Signal member")
        return self


def _member_attention(
    value: tuple[CaseMemberAttentionBindingV1Alpha1, ...],
) -> tuple[CaseMemberAttentionBindingV1Alpha1, ...]:
    signal_ids = [item.signal_resource_id for item in value]
    receipt_ids = [item.attention_receipt_id for item in value]
    if len(signal_ids) != len(set(signal_ids)) or len(receipt_ids) != len(set(receipt_ids)):
        raise ValueError("case member attention bindings must be one-to-one on Signal and receipt")
    return tuple(sorted(value, key=lambda item: item.signal_resource_id))


class CaseBriefSynthesisRequestV1Alpha1(_StrictFrozenContract):
    """One exact mode-bound Case-triggered Brief request.

    This is the additive sibling of ``BriefSynthesisRequestV1Alpha1``. It binds
    one exact PREPARED Case instead of one routed derivation and carries the
    exact attention receipt for every Signal member of that Case.
    """

    contract: Literal["ace.intelligence.case-brief-synthesis-request/v1alpha1"] = CASE_BRIEF_SYNTHESIS_REQUEST_VERSION
    synthesis_key: str
    reasoning_attempt_key: str
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    activation_revision: ActivationRevisionReferenceV1Alpha1
    pack: CompiledPackRefV1
    case: IntelligenceRecordReferenceV1Alpha1
    member_attention: tuple[CaseMemberAttentionBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=64,
    )
    brief_as_of: datetime
    context_cutoff_at: datetime
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("synthesis_key", "reasoning_attempt_key", "product_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("request_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("member_attention")
    @classmethod
    def normalize_member_attention(
        cls,
        value: tuple[CaseMemberAttentionBindingV1Alpha1, ...],
    ) -> tuple[CaseMemberAttentionBindingV1Alpha1, ...]:
        return _member_attention(value)

    @field_validator("brief_as_of", "context_cutoff_at", "requested_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        return _reference(value, name="request_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or self.activation_revision.product_id != self.product_id
            or self.case.product_id != self.product_id
        ):
            raise ValueError("Case Brief synthesis request crossed exact product scope")
        if self.case.resource_kind is not IntelligenceRecordKind.CASE or self.case.mode is not self.mode:
            raise ValueError("Case Brief synthesis request must bind one exact PREPARED Case")
        if self.case.as_of > self.brief_as_of:
            raise ValueError("the bound Case semantic as_of cannot follow the Brief cutoff")
        if self.case.available_at > self.brief_as_of:
            raise ValueError("the bound Case must be available by the context cutoff")
        if self.brief_as_of != self.context_cutoff_at:
            raise ValueError("Brief as_of must equal its frozen analysis and evidence cutoff")
        if self.context_cutoff_at > self.requested_at:
            raise ValueError("Brief analysis and evidence cutoff cannot follow request time")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("Case Brief synthesis request must occur inside the authenticated window")
        _derive_identity(
            self,
            prefix="case_brief_synthesis_request",
            id_field="request_id",
            digest_field="request_digest",
        )
        return self


class CaseBriefSynthesisReceiptV1Alpha1(_StrictFrozenContract):
    """Durable semantic correlation for one canonical Case-bound Brief."""

    contract: Literal["ace.intelligence.case-brief-synthesis-receipt/v1alpha1"] = CASE_BRIEF_SYNTHESIS_RECEIPT_VERSION
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    synthesis_key: str
    reasoning_attempt_key: str
    request_id: str
    request_digest: str
    reasoning_request_id: str
    reasoning_request_digest: str
    activation_revision: ActivationRevisionReferenceV1Alpha1
    activation_commit: ReceiptReferenceV1Alpha1
    pack: CompiledPackRefV1
    case: IntelligenceRecordReferenceV1Alpha1
    case_member_ids: tuple[str, ...] = Field(min_length=2, max_length=256)
    member_attention: tuple[CaseMemberAttentionBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=64,
    )
    module_id: str
    module_digest: str
    template_id: str
    template_digest: str
    persona_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    required_section_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    actual_section_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    section_claims: tuple[BriefSectionClaimBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=32,
    )
    recommendation_claim_id: str | None = None
    claim_supports: tuple[BriefClaimSupportBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=1_024,
    )
    selected_context: tuple[BriefSelectedContextBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=1_024,
    )
    write_intent_id: str
    write_intent_digest: str
    write_authorization: ReceiptReferenceV1Alpha1
    reasoning_terminal: ReceiptReferenceV1Alpha1
    reasoning_result_id: str
    reasoning_result_digest: str
    brief_id: str
    brief_digest: str
    created_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "product_id",
        "synthesis_key",
        "reasoning_attempt_key",
        "request_id",
        "reasoning_request_id",
        "reasoning_result_id",
        "brief_id",
        "write_intent_id",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("module_id", "template_id")
    @classmethod
    def validate_slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator(
        "request_digest",
        "reasoning_request_digest",
        "module_digest",
        "template_digest",
        "reasoning_result_digest",
        "brief_digest",
        "write_intent_digest",
        "receipt_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("case_member_ids")
    @classmethod
    def normalize_member_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_reference(item, name="case_member_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("Case member identities must be unique")
        return tuple(sorted(validated))

    @field_validator("member_attention")
    @classmethod
    def normalize_member_attention(
        cls,
        value: tuple[CaseMemberAttentionBindingV1Alpha1, ...],
    ) -> tuple[CaseMemberAttentionBindingV1Alpha1, ...]:
        return _member_attention(value)

    @field_validator("persona_ids")
    @classmethod
    def normalize_personas(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name="persona_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("synthesis receipt personas must be unique")
        return tuple(sorted(validated))

    @field_validator("required_section_ids", "actual_section_ids")
    @classmethod
    def validate_section_ids(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name=info.field_name) for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError(f"{info.field_name} must be unique")
        return validated

    @field_validator("claim_supports")
    @classmethod
    def validate_claim_supports(
        cls,
        value: tuple[BriefClaimSupportBindingV1Alpha1, ...],
    ) -> tuple[BriefClaimSupportBindingV1Alpha1, ...]:
        ids = [item.claim_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("synthesis receipt claim support bindings must be unique")
        return value

    @field_validator("section_claims")
    @classmethod
    def validate_section_claims(
        cls,
        value: tuple[BriefSectionClaimBindingV1Alpha1, ...],
    ) -> tuple[BriefSectionClaimBindingV1Alpha1, ...]:
        ids = [item.section_id for item in value]
        claim_ids = [claim_id for item in value for claim_id in item.claim_ids]
        if len(ids) != len(set(ids)) or len(claim_ids) != len(set(claim_ids)):
            raise ValueError("section and claim membership must be unique")
        return value

    @field_validator("recommendation_claim_id")
    @classmethod
    def validate_recommendation_claim_id(cls, value: str | None) -> str | None:
        return _reference(value, name="recommendation_claim_id") if value is not None else None

    @field_validator("selected_context")
    @classmethod
    def normalize_context_bindings(
        cls,
        value: tuple[BriefSelectedContextBindingV1Alpha1, ...],
    ) -> tuple[BriefSelectedContextBindingV1Alpha1, ...]:
        record_ids = [item.record.resource_id for item in value]
        context_ids = [item.context.context_id for item in value]
        if len(record_ids) != len(set(record_ids)) or len(context_ids) != len(set(context_ids)):
            raise ValueError("synthesis receipt record and context mappings must be one-to-one")
        return tuple(sorted(value, key=lambda item: (item.record.resource_kind.value, item.record.resource_id)))

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware(value, name="created_at")

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return _reference(value, name="receipt_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id or self.case.product_id != self.product_id:
            raise ValueError("Case synthesis receipt crossed exact product scope")
        if self.case.resource_kind is not IntelligenceRecordKind.CASE or self.case.mode is not self.mode:
            raise ValueError("Case synthesis receipt must bind one exact PREPARED Case")
        if self.actual_section_ids != self.required_section_ids:
            raise ValueError("synthesis receipt section order must exactly conform to required policy")
        if tuple(item.section_id for item in self.section_claims) != self.actual_section_ids:
            raise ValueError("synthesis receipt section claim membership crossed exact section order")
        bound_claim_ids = tuple(item.claim_id for item in self.claim_supports)
        section_claim_ids = tuple(claim_id for item in self.section_claims for claim_id in item.claim_ids)
        if bound_claim_ids != section_claim_ids:
            raise ValueError("synthesis receipt must bind every ordered section claim exactly once")
        if self.recommendation_claim_id is not None and self.recommendation_claim_id not in bound_claim_ids:
            raise ValueError("recommendation claim must identify one exact ordered section claim")
        selected_ids = {item.record.resource_id for item in self.selected_context}
        if any(
            item.record.product_id != self.product_id or item.record.mode is not self.mode
            for item in self.selected_context
        ):
            raise ValueError("selected context records crossed product or mode scope")
        support_ids = {support for item in self.claim_supports for support in item.support_record_ids}
        if support_ids != selected_ids:
            raise ValueError("claim support bindings must use every exact selected context record")
        if self.case.resource_id not in selected_ids:
            raise ValueError("Case-bound synthesis must select the exact bound Case as frozen context")
        if not set(self.case_member_ids) <= selected_ids:
            raise ValueError("every exact Case member must appear in the selected context")
        routed = {item.signal_resource_id for item in self.member_attention}
        if not routed <= set(self.case_member_ids):
            raise ValueError("routed attention bindings must name exact direct Case members")
        if not self.brief_id.startswith("brief:"):
            raise ValueError("synthesis receipt must bind one exact Brief identity")
        _derive_identity(
            self,
            prefix="case_brief_synthesis_receipt",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


class PreparedCaseBriefAppendRecordRecipeV1Alpha1(_StrictFrozenContract):
    """One ordered record in the Case-bound authorization-reference/time recipe."""

    record_kind: Literal["brief", "case_brief_synthesis_receipt"]
    payload_contract: str
    record_key_derivation: str
    payload_digest_derivation: str
    as_of_derivation: str
    available_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    processing_order: int = Field(ge=0, le=1)

    @field_validator(
        "payload_contract",
        "record_key_derivation",
        "payload_digest_derivation",
        "as_of_derivation",
    )
    @classmethod
    def validate_recipe_values(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)


class PreparedCaseBriefAppendIntentV1Alpha1(_StrictFrozenContract):
    """Exact pre-authorization recipe for the Case-bound second-phase append."""

    contract: Literal["ace.intelligence.prepared-case-brief-append-intent/v1alpha1"] = (
        PREPARED_CASE_BRIEF_APPEND_INTENT_VERSION
    )
    recipe_contract: Literal["ace.intelligence.prepared-case-brief-append-recipe/v1alpha1"] = (
        PREPARED_CASE_BRIEF_APPEND_RECIPE_VERSION
    )
    product_id: str
    record_space: Literal["prepared"] = "prepared"
    transaction_key: str
    case_id: str
    semantic_input_digest: str
    authorization_operation: Literal["append_immutable_records"] = "append_immutable_records"
    authorization_reference_insertion: Literal["synthesis_receipt.write_authorization"] = (
        "synthesis_receipt.write_authorization"
    )
    timestamp_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    submitted_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    records: tuple[PreparedCaseBriefAppendRecordRecipeV1Alpha1, ...] = Field(
        min_length=2,
        max_length=2,
    )
    governed_state_identities: tuple[str, ...] = Field(min_length=4, max_length=64)
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator("product_id", "transaction_key", "case_id", "governed_state_identities")
    @classmethod
    def validate_references(cls, value, info):
        if info.field_name == "governed_state_identities":
            validated = tuple(_reference(item, name="governed_state_identity") for item in value)
            if len(validated) != len(set(validated)):
                raise ValueError("governed state identities must be unique")
            return tuple(sorted(validated))
        return _reference(value, name=info.field_name)

    @field_validator("semantic_input_digest", "intent_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("intent_id")
    @classmethod
    def validate_intent_id(cls, value: str | None) -> str | None:
        return _reference(value, name="intent_id") if value is not None else None

    @model_validator(mode="after")
    def validate_recipe_and_identity(self) -> Self:
        if not self.case_id.startswith(f"{IntelligenceRecordKind.CASE.value}:"):
            raise ValueError("Case-bound append intent must name one exact Case identity")
        actual = tuple(
            (
                item.record_kind,
                item.payload_contract,
                item.record_key_derivation,
                item.payload_digest_derivation,
                item.as_of_derivation,
                item.available_at_derivation,
                item.processing_order,
            )
            for item in self.records
        )
        expected = (
            (
                "brief",
                "ace.intelligence.brief/v1alpha1",
                "brief.resource_id_from_authorized_at",
                "brief.canonical_payload_from_intent_and_authorized_at",
                "request.brief_as_of",
                "authorization.authorized_at",
                0,
            ),
            (
                "case_brief_synthesis_receipt",
                "ace.intelligence.case-brief-synthesis-receipt/v1alpha1",
                "receipt.receipt_id_from_authorization_reference_and_authorized_at",
                "receipt.canonical_payload_from_intent_authorization_and_authorized_at",
                "authorization.authorized_at",
                "authorization.authorized_at",
                1,
            ),
        )
        if actual != expected:
            raise ValueError("prepared Case Brief append recipe must contain exactly two ordered records")
        _derive_identity(
            self,
            prefix="prepared_case_brief_append_intent",
            id_field="intent_id",
            digest_field="intent_digest",
        )
        return self


class PreparedCaseBriefAppendV1Alpha1(_StrictFrozenContract):
    """Separate second-phase append containing one Case-bound Brief and receipt."""

    contract: Literal["ace.intelligence.prepared-case-brief-append/v1alpha1"] = PREPARED_CASE_BRIEF_APPEND_VERSION
    synthesis_key: str
    request_id: str
    request_digest: str
    brief: BriefV1Alpha1
    synthesis_receipt: CaseBriefSynthesisReceiptV1Alpha1
    submitted_at: datetime
    append_id: str | None = None
    append_digest: str | None = None

    @field_validator("synthesis_key", "request_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("request_digest", "append_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, value: datetime) -> datetime:
        return _aware(value, name="submitted_at")

    @field_validator("append_id")
    @classmethod
    def validate_append_id(cls, value: str | None) -> str | None:
        return _reference(value, name="append_id") if value is not None else None

    @model_validator(mode="after")
    def validate_exact_pair_and_identity(self) -> Self:
        receipt = self.synthesis_receipt
        if (
            self.brief.mode is not IntelligenceResourceMode.PREPARED
            or self.brief.product_id != receipt.product_id
            or self.brief.activation_revision != receipt.activation_revision
            or self.brief.resource_id != receipt.brief_id
            or self.brief.resource_digest != receipt.brief_digest
            or self.synthesis_key != receipt.synthesis_key
            or self.request_id != receipt.request_id
            or self.request_digest != receipt.request_digest
            or self.submitted_at != receipt.created_at
            or self.brief.generated_at != self.submitted_at
        ):
            raise ValueError("prepared Case Brief append does not bind its exact synthesis receipt")
        if not any(item.resource_id == receipt.case.resource_id for item in self.brief.lineage):
            raise ValueError("a Case-bound Brief must carry its exact Case in lineage")
        _derive_identity(
            self,
            prefix="prepared_case_brief_append",
            id_field="append_id",
            digest_field="append_digest",
        )
        return self


class InitialCorpusBriefSynthesisRequestV1Alpha1(_StrictFrozenContract):
    """One exact orientation-policy-bound first Brief over the admitted corpus.

    This is the additive sibling of ``BriefSynthesisRequestV1Alpha1``. It binds
    no routed derivation, no attention receipt, and no Signal: the first Brief
    is an orientation over the already admitted Observation and Entity Snapshot
    records at one exact ``corpus_as_of``/``corpus_available_at``, selected by a
    declared Pack orientation policy. It is not a change event.
    """

    contract: Literal["ace.intelligence.initial-corpus-brief-synthesis-request/v1alpha1"] = (
        INITIAL_CORPUS_BRIEF_SYNTHESIS_REQUEST_VERSION
    )
    synthesis_key: str
    reasoning_attempt_key: str
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    activation_revision: ActivationRevisionReferenceV1Alpha1
    pack: CompiledPackRefV1
    orientation_policy_id: str
    corpus_as_of: datetime
    corpus_available_at: datetime
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("synthesis_key", "reasoning_attempt_key", "product_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("orientation_policy_id")
    @classmethod
    def validate_orientation_policy_id(cls, value: str) -> str:
        return validate_slug(value, name="orientation_policy_id")

    @field_validator("request_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("corpus_as_of", "corpus_available_at", "requested_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        return _reference(value, name="request_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or self.activation_revision.product_id != self.product_id
        ):
            raise ValueError("initial-corpus Brief synthesis request crossed exact product scope")
        if self.corpus_as_of > self.corpus_available_at:
            raise ValueError("the exact corpus as_of cannot follow its availability instant")
        if self.corpus_available_at > self.requested_at:
            raise ValueError("the exact corpus availability instant cannot follow request time")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("initial-corpus Brief synthesis request must occur inside the authenticated window")
        _derive_identity(
            self,
            prefix="initial_corpus_brief_synthesis_request",
            id_field="request_id",
            digest_field="request_digest",
        )
        return self


class InitialCorpusBriefSynthesisReceiptV1Alpha1(_StrictFrozenContract):
    """Durable semantic correlation for one canonical initial-corpus first Brief."""

    contract: Literal["ace.intelligence.initial-corpus-brief-synthesis-receipt/v1alpha1"] = (
        INITIAL_CORPUS_BRIEF_SYNTHESIS_RECEIPT_VERSION
    )
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    synthesis_key: str
    reasoning_attempt_key: str
    request_id: str
    request_digest: str
    reasoning_request_id: str
    reasoning_request_digest: str
    activation_revision: ActivationRevisionReferenceV1Alpha1
    activation_commit: ReceiptReferenceV1Alpha1
    pack: CompiledPackRefV1
    orientation_module_id: str
    orientation_module_digest: str
    orientation_policy_id: str
    orientation_policy_digest: str
    corpus_as_of: datetime
    corpus_available_at: datetime
    corpus_observation_ids: tuple[str, ...] = Field(min_length=1, max_length=1_024)
    corpus_entity_snapshot_ids: tuple[str, ...] = Field(min_length=1, max_length=1_024)
    module_id: str
    module_digest: str
    template_id: str
    template_digest: str
    persona_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    required_section_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    actual_section_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    section_claims: tuple[BriefSectionClaimBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=32,
    )
    recommendation_claim_id: str | None = None
    claim_supports: tuple[BriefClaimSupportBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=1_024,
    )
    selected_context: tuple[BriefSelectedContextBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=1_024,
    )
    write_intent_id: str
    write_intent_digest: str
    write_authorization: ReceiptReferenceV1Alpha1
    reasoning_terminal: ReceiptReferenceV1Alpha1
    reasoning_result_id: str
    reasoning_result_digest: str
    brief_id: str
    brief_digest: str
    created_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "product_id",
        "synthesis_key",
        "reasoning_attempt_key",
        "request_id",
        "reasoning_request_id",
        "reasoning_result_id",
        "brief_id",
        "write_intent_id",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("orientation_module_id", "orientation_policy_id", "module_id", "template_id")
    @classmethod
    def validate_slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator(
        "request_digest",
        "reasoning_request_digest",
        "orientation_module_digest",
        "orientation_policy_digest",
        "module_digest",
        "template_digest",
        "reasoning_result_digest",
        "brief_digest",
        "write_intent_digest",
        "receipt_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("corpus_as_of", "corpus_available_at", "created_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("corpus_observation_ids", "corpus_entity_snapshot_ids")
    @classmethod
    def normalize_corpus_ids(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        validated = tuple(_reference(item, name=info.field_name) for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError(f"{info.field_name} must use unique exact identities")
        return tuple(sorted(validated))

    @field_validator("persona_ids")
    @classmethod
    def normalize_personas(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name="persona_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("synthesis receipt personas must be unique")
        return tuple(sorted(validated))

    @field_validator("required_section_ids", "actual_section_ids")
    @classmethod
    def validate_section_ids(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name=info.field_name) for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError(f"{info.field_name} must be unique")
        return validated

    @field_validator("claim_supports")
    @classmethod
    def validate_claim_supports(
        cls,
        value: tuple[BriefClaimSupportBindingV1Alpha1, ...],
    ) -> tuple[BriefClaimSupportBindingV1Alpha1, ...]:
        ids = [item.claim_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("synthesis receipt claim support bindings must be unique")
        return value

    @field_validator("section_claims")
    @classmethod
    def validate_section_claims(
        cls,
        value: tuple[BriefSectionClaimBindingV1Alpha1, ...],
    ) -> tuple[BriefSectionClaimBindingV1Alpha1, ...]:
        ids = [item.section_id for item in value]
        claim_ids = [claim_id for item in value for claim_id in item.claim_ids]
        if len(ids) != len(set(ids)) or len(claim_ids) != len(set(claim_ids)):
            raise ValueError("section and claim membership must be unique")
        return value

    @field_validator("recommendation_claim_id")
    @classmethod
    def validate_recommendation_claim_id(cls, value: str | None) -> str | None:
        return _reference(value, name="recommendation_claim_id") if value is not None else None

    @field_validator("selected_context")
    @classmethod
    def normalize_context_bindings(
        cls,
        value: tuple[BriefSelectedContextBindingV1Alpha1, ...],
    ) -> tuple[BriefSelectedContextBindingV1Alpha1, ...]:
        record_ids = [item.record.resource_id for item in value]
        context_ids = [item.context.context_id for item in value]
        if len(record_ids) != len(set(record_ids)) or len(context_ids) != len(set(context_ids)):
            raise ValueError("synthesis receipt record and context mappings must be one-to-one")
        return tuple(sorted(value, key=lambda item: (item.record.resource_kind.value, item.record.resource_id)))

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return _reference(value, name="receipt_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("synthesis receipt activation crossed exact product scope")
        if self.corpus_as_of > self.corpus_available_at:
            raise ValueError("the exact corpus as_of cannot follow its availability instant")
        if self.actual_section_ids != self.required_section_ids:
            raise ValueError("synthesis receipt section order must exactly conform to required policy")
        if tuple(item.section_id for item in self.section_claims) != self.actual_section_ids:
            raise ValueError("synthesis receipt section claim membership crossed exact section order")
        bound_claim_ids = tuple(item.claim_id for item in self.claim_supports)
        section_claim_ids = tuple(claim_id for item in self.section_claims for claim_id in item.claim_ids)
        if bound_claim_ids != section_claim_ids:
            raise ValueError("synthesis receipt must bind every ordered section claim exactly once")
        if self.recommendation_claim_id is not None and self.recommendation_claim_id not in bound_claim_ids:
            raise ValueError("recommendation claim must identify one exact ordered section claim")
        selected_ids = {item.record.resource_id for item in self.selected_context}
        if any(
            item.record.product_id != self.product_id or item.record.mode is not self.mode
            for item in self.selected_context
        ):
            raise ValueError("selected context records crossed product or mode scope")
        if any(
            item.record.as_of != self.corpus_as_of or item.record.available_at > self.corpus_available_at
            for item in self.selected_context
        ):
            raise ValueError("selected corpus records must share the exact corpus as_of without future leakage")
        corpus_ids = set(self.corpus_observation_ids) | set(self.corpus_entity_snapshot_ids)
        if corpus_ids != selected_ids or len(corpus_ids) != len(self.corpus_observation_ids) + len(
            self.corpus_entity_snapshot_ids
        ):
            raise ValueError("selected context must be exactly the admitted corpus Observations and Entity Snapshots")
        if any(
            item.record.resource_kind is not IntelligenceRecordKind.OBSERVATION
            for item in self.selected_context
            if item.record.resource_id in set(self.corpus_observation_ids)
        ) or any(
            item.record.resource_kind is not IntelligenceRecordKind.ENTITY_SNAPSHOT
            for item in self.selected_context
            if item.record.resource_id in set(self.corpus_entity_snapshot_ids)
        ):
            raise ValueError("corpus identities must name exact Observation and Entity Snapshot records")
        support_ids = {support for item in self.claim_supports for support in item.support_record_ids}
        if support_ids != selected_ids:
            raise ValueError("claim support bindings must use every exact selected context record")
        if not self.brief_id.startswith("brief:"):
            raise ValueError("synthesis receipt must bind one exact Brief identity")
        _derive_identity(
            self,
            prefix="initial_corpus_brief_synthesis_receipt",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


class PreparedInitialCorpusBriefAppendRecordRecipeV1Alpha1(_StrictFrozenContract):
    """One ordered record in the initial-corpus auth-reference/time recipe."""

    record_kind: Literal["brief", "initial_corpus_brief_synthesis_receipt"]
    payload_contract: str
    record_key_derivation: str
    payload_digest_derivation: str
    as_of_derivation: str
    available_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    processing_order: int = Field(ge=0, le=1)

    @field_validator(
        "payload_contract",
        "record_key_derivation",
        "payload_digest_derivation",
        "as_of_derivation",
    )
    @classmethod
    def validate_recipe_values(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)


class PreparedInitialCorpusBriefAppendIntentV1Alpha1(_StrictFrozenContract):
    """Exact pre-authorization recipe for the initial-corpus second-phase append."""

    contract: Literal["ace.intelligence.prepared-initial-corpus-brief-append-intent/v1alpha1"] = (
        PREPARED_INITIAL_CORPUS_BRIEF_APPEND_INTENT_VERSION
    )
    recipe_contract: Literal["ace.intelligence.prepared-initial-corpus-brief-append-recipe/v1alpha1"] = (
        PREPARED_INITIAL_CORPUS_BRIEF_APPEND_RECIPE_VERSION
    )
    product_id: str
    record_space: Literal["prepared"] = "prepared"
    transaction_key: str
    orientation_policy_id: str
    semantic_input_digest: str
    authorization_operation: Literal["append_immutable_records"] = "append_immutable_records"
    authorization_reference_insertion: Literal["synthesis_receipt.write_authorization"] = (
        "synthesis_receipt.write_authorization"
    )
    timestamp_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    submitted_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    records: tuple[PreparedInitialCorpusBriefAppendRecordRecipeV1Alpha1, ...] = Field(
        min_length=2,
        max_length=2,
    )
    governed_state_identities: tuple[str, ...] = Field(min_length=4, max_length=64)
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator("product_id", "transaction_key", "governed_state_identities")
    @classmethod
    def validate_references(cls, value, info):
        if info.field_name == "governed_state_identities":
            validated = tuple(_reference(item, name="governed_state_identity") for item in value)
            if len(validated) != len(set(validated)):
                raise ValueError("governed state identities must be unique")
            return tuple(sorted(validated))
        return _reference(value, name=info.field_name)

    @field_validator("orientation_policy_id")
    @classmethod
    def validate_orientation_policy_id(cls, value: str) -> str:
        return validate_slug(value, name="orientation_policy_id")

    @field_validator("semantic_input_digest", "intent_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("intent_id")
    @classmethod
    def validate_intent_id(cls, value: str | None) -> str | None:
        return _reference(value, name="intent_id") if value is not None else None

    @model_validator(mode="after")
    def validate_recipe_and_identity(self) -> Self:
        actual = tuple(
            (
                item.record_kind,
                item.payload_contract,
                item.record_key_derivation,
                item.payload_digest_derivation,
                item.as_of_derivation,
                item.available_at_derivation,
                item.processing_order,
            )
            for item in self.records
        )
        expected = (
            (
                "brief",
                "ace.intelligence.brief/v1alpha1",
                "brief.resource_id_from_authorized_at",
                "brief.canonical_payload_from_intent_and_authorized_at",
                "request.corpus_as_of",
                "authorization.authorized_at",
                0,
            ),
            (
                "initial_corpus_brief_synthesis_receipt",
                "ace.intelligence.initial-corpus-brief-synthesis-receipt/v1alpha1",
                "receipt.receipt_id_from_authorization_reference_and_authorized_at",
                "receipt.canonical_payload_from_intent_authorization_and_authorized_at",
                "authorization.authorized_at",
                "authorization.authorized_at",
                1,
            ),
        )
        if actual != expected:
            raise ValueError("prepared initial-corpus Brief append recipe must contain exactly two ordered records")
        _derive_identity(
            self,
            prefix="prepared_initial_corpus_brief_append_intent",
            id_field="intent_id",
            digest_field="intent_digest",
        )
        return self


class PreparedInitialCorpusBriefAppendV1Alpha1(_StrictFrozenContract):
    """Second-phase append containing one initial-corpus Brief and its receipt."""

    contract: Literal["ace.intelligence.prepared-initial-corpus-brief-append/v1alpha1"] = (
        PREPARED_INITIAL_CORPUS_BRIEF_APPEND_VERSION
    )
    synthesis_key: str
    request_id: str
    request_digest: str
    brief: BriefV1Alpha1
    synthesis_receipt: InitialCorpusBriefSynthesisReceiptV1Alpha1
    submitted_at: datetime
    append_id: str | None = None
    append_digest: str | None = None

    @field_validator("synthesis_key", "request_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("request_digest", "append_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, value: datetime) -> datetime:
        return _aware(value, name="submitted_at")

    @field_validator("append_id")
    @classmethod
    def validate_append_id(cls, value: str | None) -> str | None:
        return _reference(value, name="append_id") if value is not None else None

    @model_validator(mode="after")
    def validate_exact_pair_and_identity(self) -> Self:
        receipt = self.synthesis_receipt
        if (
            self.brief.mode is not IntelligenceResourceMode.PREPARED
            or self.brief.product_id != receipt.product_id
            or self.brief.activation_revision != receipt.activation_revision
            or self.brief.resource_id != receipt.brief_id
            or self.brief.resource_digest != receipt.brief_digest
            or self.brief.as_of != receipt.corpus_as_of
            or self.synthesis_key != receipt.synthesis_key
            or self.request_id != receipt.request_id
            or self.request_digest != receipt.request_digest
            or self.submitted_at != receipt.created_at
            or self.brief.generated_at != self.submitted_at
        ):
            raise ValueError("prepared initial-corpus Brief append does not bind its exact synthesis receipt")
        _derive_identity(
            self,
            prefix="prepared_initial_corpus_brief_append",
            id_field="append_id",
            digest_field="append_digest",
        )
        return self


class PreparedStatusCaseBriefAppendRecordRecipeV1Alpha1(_StrictFrozenContract):
    """One ordered record in the status-aware auth-reference/time derivation recipe."""

    record_kind: Literal["brief", "case_brief_synthesis_receipt", "brief_epistemic_status_projection"]
    payload_contract: str
    record_key_derivation: str
    payload_digest_derivation: str
    as_of_derivation: str
    available_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    processing_order: int = Field(ge=0, le=2)

    @field_validator(
        "payload_contract",
        "record_key_derivation",
        "payload_digest_derivation",
        "as_of_derivation",
    )
    @classmethod
    def validate_recipe_values(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)


_STATUS_APPEND_RECIPE = (
    (
        "brief",
        "ace.intelligence.brief/v1alpha1",
        "brief.resource_id_from_authorized_at",
        "brief.canonical_payload_from_intent_and_authorized_at",
        "request.brief_as_of",
        "authorization.authorized_at",
        0,
    ),
    (
        "case_brief_synthesis_receipt",
        "ace.intelligence.case-brief-synthesis-receipt/v1alpha1",
        "receipt.receipt_id_from_authorization_reference_and_authorized_at",
        "receipt.canonical_payload_from_intent_authorization_and_authorized_at",
        "authorization.authorized_at",
        "authorization.authorized_at",
        1,
    ),
    (
        "brief_epistemic_status_projection",
        "ace.intelligence.brief-epistemic-status-projection/v1alpha1",
        "projection.projection_id_from_brief_receipt_and_authorized_at",
        "projection.canonical_payload_from_brief_receipt_and_authorized_at",
        "request.brief_as_of",
        "authorization.authorized_at",
        2,
    ),
)


class PreparedStatusCaseBriefAppendIntentV1Alpha1(_StrictFrozenContract):
    """Exact pre-authorization recipe for the status-aware three-record append."""

    contract: Literal["ace.intelligence.prepared-status-case-brief-append-intent/v1alpha1"] = (
        PREPARED_STATUS_CASE_BRIEF_APPEND_INTENT_VERSION
    )
    recipe_contract: Literal["ace.intelligence.prepared-status-case-brief-append-recipe/v1alpha1"] = (
        PREPARED_STATUS_CASE_BRIEF_APPEND_RECIPE_VERSION
    )
    product_id: str
    record_space: Literal["prepared"] = "prepared"
    transaction_key: str
    case_id: str
    status_set_id: str
    status_set_digest: str
    semantic_input_digest: str
    authorization_operation: Literal["append_immutable_records"] = "append_immutable_records"
    authorization_reference_insertion: Literal["synthesis_receipt.write_authorization"] = (
        "synthesis_receipt.write_authorization"
    )
    timestamp_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    submitted_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    records: tuple[PreparedStatusCaseBriefAppendRecordRecipeV1Alpha1, ...] = Field(
        min_length=3,
        max_length=3,
    )
    governed_state_identities: tuple[str, ...] = Field(min_length=4, max_length=64)
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator("product_id", "transaction_key", "case_id", "governed_state_identities")
    @classmethod
    def validate_references(cls, value, info):
        if info.field_name == "governed_state_identities":
            validated = tuple(_reference(item, name="governed_state_identity") for item in value)
            if len(validated) != len(set(validated)):
                raise ValueError("governed state identities must be unique")
            return tuple(sorted(validated))
        return _reference(value, name=info.field_name)

    @field_validator("status_set_id")
    @classmethod
    def validate_status_set_id(cls, value: str) -> str:
        return validate_slug(value, name="status_set_id")

    @field_validator("semantic_input_digest", "status_set_digest", "intent_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("intent_id")
    @classmethod
    def validate_intent_id(cls, value: str | None) -> str | None:
        return _reference(value, name="intent_id") if value is not None else None

    @model_validator(mode="after")
    def validate_recipe_and_identity(self) -> Self:
        if not self.case_id.startswith(f"{IntelligenceRecordKind.CASE.value}:"):
            raise ValueError("status-aware append intent must name one exact Case identity")
        actual = tuple(
            (
                item.record_kind,
                item.payload_contract,
                item.record_key_derivation,
                item.payload_digest_derivation,
                item.as_of_derivation,
                item.available_at_derivation,
                item.processing_order,
            )
            for item in self.records
        )
        if actual != _STATUS_APPEND_RECIPE:
            raise ValueError("prepared status Case Brief append recipe must contain exactly three ordered records")
        _derive_identity(
            self,
            prefix="prepared_status_case_brief_append_intent",
            id_field="intent_id",
            digest_field="intent_digest",
        )
        return self


class PreparedStatusCaseBriefAppendV1Alpha1(_StrictFrozenContract):
    """Second-phase append of one Brief, its Case receipt, and its status projection."""

    contract: Literal["ace.intelligence.prepared-status-case-brief-append/v1alpha1"] = (
        PREPARED_STATUS_CASE_BRIEF_APPEND_VERSION
    )
    synthesis_key: str
    request_id: str
    request_digest: str
    brief: BriefV1Alpha1
    synthesis_receipt: CaseBriefSynthesisReceiptV1Alpha1
    status_projection: BriefEpistemicStatusProjectionV1Alpha1
    submitted_at: datetime
    append_id: str | None = None
    append_digest: str | None = None

    @field_validator("synthesis_key", "request_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("request_digest", "append_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, value: datetime) -> datetime:
        return _aware(value, name="submitted_at")

    @field_validator("append_id")
    @classmethod
    def validate_append_id(cls, value: str | None) -> str | None:
        return _reference(value, name="append_id") if value is not None else None

    @model_validator(mode="after")
    def validate_exact_triple_and_identity(self) -> Self:
        receipt = self.synthesis_receipt
        projection = self.status_projection
        if (
            self.brief.mode is not IntelligenceResourceMode.PREPARED
            or self.brief.product_id != receipt.product_id
            or self.brief.activation_revision != receipt.activation_revision
            or self.brief.resource_id != receipt.brief_id
            or self.brief.resource_digest != receipt.brief_digest
            or self.synthesis_key != receipt.synthesis_key
            or self.request_id != receipt.request_id
            or self.request_digest != receipt.request_digest
            or self.submitted_at != receipt.created_at
            or self.brief.generated_at != self.submitted_at
        ):
            raise ValueError("prepared status Case Brief append does not bind its exact synthesis receipt")
        if not any(item.resource_id == receipt.case.resource_id for item in self.brief.lineage):
            raise ValueError("a Case-bound Brief must carry its exact Case in lineage")
        if (
            projection.product_id != receipt.product_id
            or projection.mode is not receipt.mode
            or projection.activation_revision != receipt.activation_revision
            or projection.brief_id != receipt.brief_id
            or projection.brief_digest != receipt.brief_digest
            or projection.synthesis_receipt_contract != receipt.contract
            or projection.synthesis_receipt_id != receipt.receipt_id
            or projection.synthesis_receipt_digest != receipt.receipt_digest
            or projection.template_id != receipt.template_id
            or projection.as_of != self.brief.as_of
            or projection.generated_at != self.submitted_at
        ):
            raise ValueError("status projection does not bind its exact Brief and synthesis receipt")
        receipted_claim_ids = tuple(item.claim_id for item in receipt.claim_supports)
        projected_claim_ids = tuple(item.claim_id for item in projection.claim_statuses)
        if projected_claim_ids != receipted_claim_ids:
            raise ValueError("status projection must bind every receipted section claim exactly once and in order")
        grounding_by_claim = {item.claim_id: item.grounding_kind for item in receipt.claim_supports}
        supports_by_claim = {item.claim_id: item.support_record_ids for item in receipt.claim_supports}
        for item in projection.claim_statuses:
            if grounding_by_claim[item.claim_id] is not item.grounding_kind:
                raise ValueError("status projection crossed the receipted claim grounding kind")
            if item.support_record_ids != supports_by_claim[item.claim_id]:
                raise ValueError("status projection crossed the receipted claim support identities")
        _derive_identity(
            self,
            prefix="prepared_status_case_brief_append",
            id_field="append_id",
            digest_field="append_digest",
        )
        return self


_FAMILY_STATUS_APPEND_RECIPE = (
    _STATUS_APPEND_RECIPE[0],
    _STATUS_APPEND_RECIPE[1],
    (
        "brief_derivation_family_status_projection",
        "ace.intelligence.brief-epistemic-status-projection/v1alpha2",
        "projection.projection_id_from_brief_receipt_and_authorized_at",
        "projection.canonical_payload_from_brief_receipt_and_authorized_at",
        "request.brief_as_of",
        "authorization.authorized_at",
        2,
    ),
)


class PreparedFamilyStatusCaseBriefAppendRecordRecipeV1Alpha1(_StrictFrozenContract):
    """One ordered record in the family-aware auth-reference/time derivation recipe."""

    record_kind: Literal[
        "brief",
        "case_brief_synthesis_receipt",
        "brief_derivation_family_status_projection",
    ]
    payload_contract: str
    record_key_derivation: str
    payload_digest_derivation: str
    as_of_derivation: str
    available_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    processing_order: int = Field(ge=0, le=2)

    @field_validator(
        "payload_contract",
        "record_key_derivation",
        "payload_digest_derivation",
        "as_of_derivation",
    )
    @classmethod
    def validate_recipe_values(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)


class PreparedFamilyStatusCaseBriefAppendIntentV1Alpha1(_StrictFrozenContract):
    """Pre-authorization recipe for the family-aware three-record append.

    Additive sibling of :class:`PreparedStatusCaseBriefAppendIntentV1Alpha1`; the
    ``v1alpha1`` intent is untouched so the epistemic-status packet already
    written under it keeps its exact ``write_intent_id``.
    """

    contract: Literal["ace.intelligence.prepared-family-status-case-brief-append-intent/v1alpha1"] = (
        PREPARED_FAMILY_STATUS_CASE_BRIEF_APPEND_INTENT_VERSION
    )
    recipe_contract: Literal["ace.intelligence.prepared-family-status-case-brief-append-recipe/v1alpha1"] = (
        PREPARED_FAMILY_STATUS_CASE_BRIEF_APPEND_RECIPE_VERSION
    )
    product_id: str
    record_space: Literal["prepared"] = "prepared"
    transaction_key: str
    case_id: str
    status_set_id: str
    status_set_digest: str
    derivation_family_policy: str
    semantic_input_digest: str
    authorization_operation: Literal["append_immutable_records"] = "append_immutable_records"
    authorization_reference_insertion: Literal["synthesis_receipt.write_authorization"] = (
        "synthesis_receipt.write_authorization"
    )
    timestamp_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    submitted_at_derivation: Literal["authorization.authorized_at"] = "authorization.authorized_at"
    records: tuple[PreparedFamilyStatusCaseBriefAppendRecordRecipeV1Alpha1, ...] = Field(
        min_length=3,
        max_length=3,
    )
    governed_state_identities: tuple[str, ...] = Field(min_length=4, max_length=64)
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator(
        "product_id",
        "transaction_key",
        "case_id",
        "derivation_family_policy",
        "governed_state_identities",
    )
    @classmethod
    def validate_references(cls, value, info):
        if info.field_name == "governed_state_identities":
            validated = tuple(_reference(item, name="governed_state_identity") for item in value)
            if len(validated) != len(set(validated)):
                raise ValueError("governed state identities must be unique")
            return tuple(sorted(validated))
        return _reference(value, name=info.field_name)

    @field_validator("status_set_id")
    @classmethod
    def validate_status_set_id(cls, value: str) -> str:
        return validate_slug(value, name="status_set_id")

    @field_validator("semantic_input_digest", "status_set_digest", "intent_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("intent_id")
    @classmethod
    def validate_intent_id(cls, value: str | None) -> str | None:
        return _reference(value, name="intent_id") if value is not None else None

    @model_validator(mode="after")
    def validate_recipe_and_identity(self) -> Self:
        if not self.case_id.startswith(f"{IntelligenceRecordKind.CASE.value}:"):
            raise ValueError("family-aware append intent must name one exact Case identity")
        actual = tuple(
            (
                item.record_kind,
                item.payload_contract,
                item.record_key_derivation,
                item.payload_digest_derivation,
                item.as_of_derivation,
                item.available_at_derivation,
                item.processing_order,
            )
            for item in self.records
        )
        if actual != _FAMILY_STATUS_APPEND_RECIPE:
            raise ValueError(
                "prepared family-status Case Brief append recipe must contain exactly three ordered records"
            )
        _derive_identity(
            self,
            prefix="prepared_family_status_case_brief_append_intent",
            id_field="intent_id",
            digest_field="intent_digest",
        )
        return self


class PreparedFamilyStatusCaseBriefAppendV1Alpha1(_StrictFrozenContract):
    """Append of one Brief, its Case receipt, and its family-aware status projection."""

    contract: Literal["ace.intelligence.prepared-family-status-case-brief-append/v1alpha1"] = (
        PREPARED_FAMILY_STATUS_CASE_BRIEF_APPEND_VERSION
    )
    synthesis_key: str
    request_id: str
    request_digest: str
    brief: BriefV1Alpha1
    synthesis_receipt: CaseBriefSynthesisReceiptV1Alpha1
    status_projection: BriefEpistemicStatusProjectionV1Alpha2
    submitted_at: datetime
    append_id: str | None = None
    append_digest: str | None = None

    @field_validator("synthesis_key", "request_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("request_digest", "append_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, value: datetime) -> datetime:
        return _aware(value, name="submitted_at")

    @field_validator("append_id")
    @classmethod
    def validate_append_id(cls, value: str | None) -> str | None:
        return _reference(value, name="append_id") if value is not None else None

    @model_validator(mode="after")
    def validate_exact_triple_and_identity(self) -> Self:
        receipt = self.synthesis_receipt
        projection = self.status_projection
        if (
            self.brief.mode is not IntelligenceResourceMode.PREPARED
            or self.brief.product_id != receipt.product_id
            or self.brief.activation_revision != receipt.activation_revision
            or self.brief.resource_id != receipt.brief_id
            or self.brief.resource_digest != receipt.brief_digest
            or self.synthesis_key != receipt.synthesis_key
            or self.request_id != receipt.request_id
            or self.request_digest != receipt.request_digest
            or self.submitted_at != receipt.created_at
            or self.brief.generated_at != self.submitted_at
        ):
            raise ValueError("prepared family-status Case Brief append does not bind its exact synthesis receipt")
        if not any(item.resource_id == receipt.case.resource_id for item in self.brief.lineage):
            raise ValueError("a Case-bound Brief must carry its exact Case in lineage")
        if (
            projection.product_id != receipt.product_id
            or projection.mode is not receipt.mode
            or projection.activation_revision != receipt.activation_revision
            or projection.brief_id != receipt.brief_id
            or projection.brief_digest != receipt.brief_digest
            or projection.synthesis_receipt_contract != receipt.contract
            or projection.synthesis_receipt_id != receipt.receipt_id
            or projection.synthesis_receipt_digest != receipt.receipt_digest
            or projection.template_id != receipt.template_id
            or projection.as_of != self.brief.as_of
            or projection.generated_at != self.submitted_at
        ):
            raise ValueError("status projection does not bind its exact Brief and synthesis receipt")
        receipted_claim_ids = tuple(item.claim_id for item in receipt.claim_supports)
        projected_claim_ids = tuple(item.claim_id for item in projection.claim_statuses)
        if projected_claim_ids != receipted_claim_ids:
            raise ValueError("status projection must bind every receipted section claim exactly once and in order")
        grounding_by_claim = {item.claim_id: item.grounding_kind for item in receipt.claim_supports}
        supports_by_claim = {item.claim_id: item.support_record_ids for item in receipt.claim_supports}
        for item in projection.claim_statuses:
            if grounding_by_claim[item.claim_id] is not item.grounding_kind:
                raise ValueError("status projection crossed the receipted claim grounding kind")
            if item.support_record_ids != supports_by_claim[item.claim_id]:
                raise ValueError("status projection crossed the receipted claim support identities")
        _derive_identity(
            self,
            prefix="prepared_family_status_case_brief_append",
            id_field="append_id",
            digest_field="append_digest",
        )
        return self


__all__ = [
    "BRIEF_DRAFT_CLAIM_VERSION",
    "PREPARED_FAMILY_STATUS_CASE_BRIEF_APPEND_VERSION",
    "PREPARED_FAMILY_STATUS_CASE_BRIEF_APPEND_INTENT_VERSION",
    "PREPARED_FAMILY_STATUS_CASE_BRIEF_APPEND_RECIPE_VERSION",
    "PreparedFamilyStatusCaseBriefAppendV1Alpha1",
    "PreparedFamilyStatusCaseBriefAppendIntentV1Alpha1",
    "PreparedFamilyStatusCaseBriefAppendRecordRecipeV1Alpha1",
    "BRIEF_DRAFT_SECTION_VERSION",
    "BRIEF_CLAIM_SUPPORT_BINDING_VERSION",
    "BRIEF_CITATION_SUPPORT_BINDING_VERSION",
    "BRIEF_SELECTED_CONTEXT_BINDING_VERSION",
    "BRIEF_SECTION_CLAIM_BINDING_VERSION",
    "BRIEF_SYNTHESIS_DRAFT_VERSION",
    "BRIEF_SYNTHESIS_DRAFT_V1ALPHA2_VERSION",
    "BRIEF_SYNTHESIS_RECEIPT_VERSION",
    "BRIEF_SYNTHESIS_REQUEST_VERSION",
    "CASE_BRIEF_SYNTHESIS_RECEIPT_VERSION",
    "CASE_BRIEF_SYNTHESIS_REQUEST_VERSION",
    "CASE_MEMBER_ATTENTION_BINDING_VERSION",
    "INITIAL_CORPUS_BRIEF_SYNTHESIS_RECEIPT_VERSION",
    "INITIAL_CORPUS_BRIEF_SYNTHESIS_REQUEST_VERSION",
    "PREPARED_INITIAL_CORPUS_BRIEF_APPEND_VERSION",
    "PREPARED_INITIAL_CORPUS_BRIEF_APPEND_INTENT_VERSION",
    "PREPARED_INITIAL_CORPUS_BRIEF_APPEND_RECIPE_VERSION",
    "InitialCorpusBriefSynthesisReceiptV1Alpha1",
    "InitialCorpusBriefSynthesisRequestV1Alpha1",
    "PreparedInitialCorpusBriefAppendV1Alpha1",
    "PreparedInitialCorpusBriefAppendIntentV1Alpha1",
    "PreparedInitialCorpusBriefAppendRecordRecipeV1Alpha1",
    "PREPARED_BRIEF_APPEND_VERSION",
    "PREPARED_BRIEF_APPEND_INTENT_VERSION",
    "PREPARED_BRIEF_APPEND_RECIPE_VERSION",
    "PREPARED_CASE_BRIEF_APPEND_VERSION",
    "PREPARED_CASE_BRIEF_APPEND_INTENT_VERSION",
    "PREPARED_CASE_BRIEF_APPEND_RECIPE_VERSION",
    "PREPARED_STATUS_CASE_BRIEF_APPEND_VERSION",
    "PREPARED_STATUS_CASE_BRIEF_APPEND_INTENT_VERSION",
    "PREPARED_STATUS_CASE_BRIEF_APPEND_RECIPE_VERSION",
    "SYNTHESIS_MODULE_VERSION",
    "SYNTHESIS_MODULE_V1ALPHA2_VERSION",
    "BriefDraftClaimV1Alpha1",
    "BriefDraftSectionV1Alpha1",
    "BriefCitationSupportBindingV1Alpha1",
    "BriefClaimSupportBindingV1Alpha1",
    "BriefSelectedContextBindingV1Alpha1",
    "BriefSectionClaimBindingV1Alpha1",
    "BriefSynthesisDraftV1Alpha1",
    "BriefSynthesisDraftV1Alpha2",
    "BriefSynthesisReceiptV1Alpha1",
    "BriefSynthesisRequestV1Alpha1",
    "BriefTemplateV1",
    "BriefTemplateV1Alpha2",
    "CaseBriefSynthesisReceiptV1Alpha1",
    "CaseBriefSynthesisRequestV1Alpha1",
    "CaseMemberAttentionBindingV1Alpha1",
    "PreparedCaseBriefAppendV1Alpha1",
    "PreparedCaseBriefAppendIntentV1Alpha1",
    "PreparedCaseBriefAppendRecordRecipeV1Alpha1",
    "PreparedBriefAppendV1Alpha1",
    "PreparedBriefAppendIntentV1Alpha1",
    "PreparedBriefAppendRecordRecipeV1Alpha1",
    "PreparedStatusCaseBriefAppendV1Alpha1",
    "PreparedStatusCaseBriefAppendIntentV1Alpha1",
    "PreparedStatusCaseBriefAppendRecordRecipeV1Alpha1",
    "SynthesisModuleV1",
    "SynthesisModuleV1Alpha2",
]
