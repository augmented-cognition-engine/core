"""Versioned domain-neutral first-Brief preview contracts for 0.7D."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, StrictFloat, field_validator, model_validator

from ace.application.intelligence_agent_contracts import EpistemicClassification, IntelligenceCitationV1
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderContract,
    aware_datetime,
    bounded_text,
    derive_builder_identity,
)
from ace.intelligence.contracts.common import (
    normalized_strings,
    sorted_unique,
    validate_digest,
    validate_reference,
    validate_slug,
)

BRIEFING_DERIVATION_VERSION = "ace.application.briefing-derivation/v1alpha1"
FIRST_BRIEFING_PREVIEW_VERSION = "ace.application.first-briefing-preview/v1alpha1"


class BriefingItemKind(StrEnum):
    CURRENT_STATE = "current_state"
    SIGNAL = "signal"
    SHIFT = "shift"
    DISAGREEMENT = "disagreement"
    UNKNOWN = "unknown"


class BriefingDerivationV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.briefing-derivation/v1alpha1"] = BRIEFING_DERIVATION_VERSION
    session_id: str
    correlation_id: str
    concept_model_proposal_id: str
    concept_model_proposal_digest: str
    concept_model_disposition_id: str
    concept_model_disposition_digest: str
    intelligence_model_proposal_id: str
    intelligence_model_proposal_digest: str
    intelligence_model_disposition_id: str
    intelligence_model_disposition_digest: str
    observation_set_id: str
    observation_set_digest: str
    derivation_id: str | None = None
    derivation_digest: str | None = None

    @field_validator(
        "session_id",
        "correlation_id",
        "concept_model_proposal_id",
        "concept_model_disposition_id",
        "intelligence_model_proposal_id",
        "intelligence_model_disposition_id",
        "observation_set_id",
        "derivation_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "concept_model_proposal_digest",
        "concept_model_disposition_digest",
        "intelligence_model_proposal_digest",
        "intelligence_model_disposition_digest",
        "observation_set_digest",
        "derivation_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        derive_builder_identity(
            self, prefix="briefing_derivation", id_field="derivation_id", digest_field="derivation_digest"
        )
        return self


class BriefingItemV1(IntelligenceBuilderContract):
    item_id: str
    item_kind: BriefingItemKind
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=4_000)
    why_it_matters: str = Field(min_length=1, max_length=2_000)
    epistemic_classification: EpistemicClassification
    statement_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    counterevidence_citation_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    uncertainty: str = Field(min_length=1, max_length=2_000)
    alternatives: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    recommended_attention: str | None = Field(default=None, max_length=1_000)
    decision_question: str | None = Field(default=None, max_length=1_000)
    materiality_rule_id: str | None = None

    @field_validator("item_id", "materiality_rule_id")
    @classmethod
    def validate_ids(cls, value: str | None, info) -> str | None:
        return validate_slug(value, name=info.field_name) if value is not None else None

    @field_validator("summary", "why_it_matters", "uncertainty", "recommended_attention", "decision_question")
    @classmethod
    def validate_text(cls, value: str | None, info) -> str | None:
        return bounded_text(value, name=info.field_name, maximum=4_000) if value is not None else None

    @field_validator("statement_ids", "citation_ids", "counterevidence_citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="citation_id")
            for item in normalized_strings(value, label=info.field_name, maximum=64)
        )

    @field_validator("alternatives", mode="before")
    @classmethod
    def normalize_alternatives(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            bounded_text(item, name="alternative", maximum=1_000)
            for item in normalized_strings(value, label="alternatives", maximum=32)
        )

    @model_validator(mode="after")
    def validate_kind_and_classification(self) -> Self:
        expected = {
            BriefingItemKind.DISAGREEMENT: EpistemicClassification.DISAGREEMENT,
            BriefingItemKind.UNKNOWN: EpistemicClassification.UNKNOWN,
        }.get(self.item_kind)
        if expected is not None and self.epistemic_classification is not expected:
            raise ValueError("disagreement and unknown item kinds require matching epistemic classification")
        if self.item_kind in {BriefingItemKind.SIGNAL, BriefingItemKind.SHIFT} and self.materiality_rule_id is None:
            raise ValueError("material signals and shifts require an exact materiality rule")
        return self


class FirstBriefingPreviewV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.first-briefing-preview/v1alpha1"] = FIRST_BRIEFING_PREVIEW_VERSION
    derivation: BriefingDerivationV1
    title: str = Field(min_length=1, max_length=300)
    executive_summary: str = Field(min_length=1, max_length=8_000)
    items: tuple[BriefingItemV1, ...] = Field(min_length=1, max_length=128)
    citations: tuple[IntelligenceCitationV1, ...] = Field(min_length=1, max_length=256)
    as_of: datetime
    freshness_statement: str = Field(min_length=1, max_length=1_000)
    generated_at: datetime
    brief_id: str | None = None
    brief_digest: str | None = None

    @field_validator("brief_id")
    @classmethod
    def validate_brief_id(cls, value: str | None) -> str | None:
        return validate_reference(value, name="brief_id") if value is not None else None

    @field_validator("brief_digest")
    @classmethod
    def validate_brief_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("executive_summary", "freshness_statement")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return bounded_text(value, name=info.field_name, maximum=8_000)

    @field_validator("as_of", "generated_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return aware_datetime(value, name=info.field_name)

    @field_validator("items")
    @classmethod
    def normalize_items(cls, value: tuple[BriefingItemV1, ...]) -> tuple[BriefingItemV1, ...]:
        ids = [item.item_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Brief items must use unique item IDs")
        return value

    @field_validator("citations")
    @classmethod
    def normalize_citations(cls, value: tuple[IntelligenceCitationV1, ...]) -> tuple[IntelligenceCitationV1, ...]:
        return sorted_unique(value, key=lambda item: item.citation_id, label="Brief citations", maximum=256)

    @model_validator(mode="after")
    def validate_grounding_and_identity(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("Brief generated_at cannot precede its as_of cutoff")
        citation_ids = {item.citation_id for item in self.citations}
        used = {
            citation for item in self.items for citation in (*item.citation_ids, *item.counterevidence_citation_ids)
        }
        if used != citation_ids:
            raise ValueError("every Brief citation must be used and every item citation must resolve")
        material_kinds = {BriefingItemKind.CURRENT_STATE, BriefingItemKind.SIGNAL, BriefingItemKind.SHIFT}
        if not any(item.item_kind in material_kinds for item in self.items):
            raise ValueError("first Brief requires at least one material current-state, signal, or shift item")
        disagreements = [item for item in self.items if item.item_kind is BriefingItemKind.DISAGREEMENT]
        unknowns = [item for item in self.items if item.item_kind is BriefingItemKind.UNKNOWN]
        if not disagreements or not unknowns:
            raise ValueError("first Brief must expose disagreement and unknown items")
        sources = {citation.citation_id: citation.source_ref for citation in self.citations}
        for item in disagreements:
            if len({sources[citation_id] for citation_id in item.citation_ids}) < 2:
                raise ValueError("Brief disagreement must retain at least two distinct sources")
        derive_builder_identity(self, prefix="first_briefing_preview", id_field="brief_id", digest_field="brief_digest")
        return self


__all__ = [
    "BRIEFING_DERIVATION_VERSION",
    "FIRST_BRIEFING_PREVIEW_VERSION",
    "BriefingDerivationV1",
    "BriefingItemKind",
    "BriefingItemV1",
    "FirstBriefingPreviewV1",
]
