"""Versioned domain-neutral proposal contracts for the 0.7C Ontology Agent."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, StrictBool, StrictFloat, StrictInt, field_validator, model_validator

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

CONCEPT_MODEL_PROPOSAL_VERSION = "ace.application.concept-model-proposal/v1alpha1"
CONCEPT_MODEL_DISPOSITION_VERSION = "ace.application.concept-model-disposition/v1alpha1"


class ConceptValueKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    REFERENCE = "reference"
    UNKNOWN = "unknown"


class ConceptCitationV1(IntelligenceBuilderContract):
    citation_id: str
    source_profile_proposal_id: str
    source_profile_proposal_digest: str
    source_sample_id: str
    source_sample_digest: str
    source_ref: str
    field_path: str
    evidence_digest: str

    @field_validator("citation_id")
    @classmethod
    def validate_citation_id(cls, value: str) -> str:
        return validate_slug(value, name="citation_id")

    @field_validator(
        "source_profile_proposal_id",
        "source_sample_id",
        "source_ref",
    )
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator(
        "source_profile_proposal_digest",
        "source_sample_digest",
        "evidence_digest",
    )
    @classmethod
    def validate_digests(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("field_path")
    @classmethod
    def validate_field_path(cls, value: str) -> str:
        if not value.startswith("/") or "//" in value or value != value.strip() or len(value) > 240:
            raise ValueError("field_path must be a bounded normalized JSON pointer")
        return value


class ConceptAttributeV1(IntelligenceBuilderContract):
    attribute_id: str
    display_name: str = Field(min_length=1, max_length=160)
    value_kind: ConceptValueKind
    required: bool = False
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    confidence: StrictFloat = Field(ge=0.0, le=1.0)

    @field_validator("attribute_id")
    @classmethod
    def validate_attribute_id(cls, value: str) -> str:
        return validate_slug(value, name="attribute_id")

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="citation_id")
            for item in normalized_strings(value, label="citation_ids", maximum=64)
        )


class ConceptEntityTypeV1(IntelligenceBuilderContract):
    type_id: str
    display_name: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=1_000)
    aliases: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    attributes: tuple[ConceptAttributeV1, ...] = Field(default_factory=tuple, max_length=128)
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    confidence: StrictFloat = Field(ge=0.0, le=1.0)

    @field_validator("type_id")
    @classmethod
    def validate_type_id(cls, value: str) -> str:
        return validate_slug(value, name="type_id")

    @field_validator("definition")
    @classmethod
    def validate_definition(cls, value: str) -> str:
        return bounded_text(value, name="definition", maximum=1_000)

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            bounded_text(item, name="alias", maximum=160)
            for item in normalized_strings(value, label="aliases", maximum=64)
        )

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="citation_id")
            for item in normalized_strings(value, label="citation_ids", maximum=64)
        )

    @field_validator("attributes")
    @classmethod
    def normalize_attributes(cls, value: tuple[ConceptAttributeV1, ...]) -> tuple[ConceptAttributeV1, ...]:
        return sorted_unique(value, key=lambda item: item.attribute_id, label="concept attributes", maximum=128)


class ConceptRelationshipTypeV1(IntelligenceBuilderContract):
    type_id: str
    display_name: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=1_000)
    from_type_id: str
    to_type_id: str
    aliases: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    confidence: StrictFloat = Field(ge=0.0, le=1.0)

    @field_validator("type_id", "from_type_id", "to_type_id")
    @classmethod
    def validate_type_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("definition")
    @classmethod
    def validate_definition(cls, value: str) -> str:
        return bounded_text(value, name="definition", maximum=1_000)

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            bounded_text(item, name="alias", maximum=160)
            for item in normalized_strings(value, label="aliases", maximum=64)
        )

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="citation_id")
            for item in normalized_strings(value, label="citation_ids", maximum=64)
        )


class ConceptTerminologyV1(IntelligenceBuilderContract):
    term_id: str
    preferred_term: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=1_000)
    synonyms: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    citation_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)

    @field_validator("term_id")
    @classmethod
    def validate_term_id(cls, value: str) -> str:
        return validate_slug(value, name="term_id")

    @field_validator("definition")
    @classmethod
    def validate_definition(cls, value: str) -> str:
        return bounded_text(value, name="definition", maximum=1_000)

    @field_validator("synonyms", mode="before")
    @classmethod
    def normalize_synonyms(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            bounded_text(item, name="synonym", maximum=160)
            for item in normalized_strings(value, label="synonyms", maximum=64)
        )

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="citation_id")
            for item in normalized_strings(value, label="citation_ids", maximum=64)
        )


class ConceptConflictV1(IntelligenceBuilderContract):
    conflict_id: str
    description: str = Field(min_length=1, max_length=1_000)
    citation_ids: tuple[str, ...] = Field(min_length=2, max_length=64)
    blocks_mapping: StrictBool = False

    @field_validator("conflict_id")
    @classmethod
    def validate_conflict_id(cls, value: str) -> str:
        return validate_slug(value, name="conflict_id")

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return bounded_text(value, name="description", maximum=1_000)

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="citation_id")
            for item in normalized_strings(value, label="citation_ids", maximum=64)
        )


class OrganizationTerminologyV1(IntelligenceBuilderContract):
    term_id: str
    preferred_term: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=1_000)
    synonyms: tuple[str, ...] = Field(default_factory=tuple, max_length=64)

    @field_validator("term_id")
    @classmethod
    def validate_term_id(cls, value: str) -> str:
        return validate_slug(value, name="term_id")

    @field_validator("definition")
    @classmethod
    def validate_definition(cls, value: str) -> str:
        return bounded_text(value, name="definition", maximum=1_000)

    @field_validator("synonyms", mode="before")
    @classmethod
    def normalize_synonyms(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            bounded_text(item, name="synonym", maximum=160)
            for item in normalized_strings(value, label="synonyms", maximum=64)
        )


class ConceptModelProposalV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.concept-model-proposal/v1alpha1"] = CONCEPT_MODEL_PROPOSAL_VERSION
    session_id: str
    correlation_id: str
    goal_ref: str
    user_intent: str = Field(min_length=1, max_length=2_000)
    source_profile_proposal_id: str
    source_profile_proposal_digest: str
    revision: StrictInt = Field(ge=1)
    prior_proposal_id: str | None = None
    prior_proposal_digest: str | None = None
    edit_summary: str | None = Field(default=None, max_length=1_000)
    semantic_diff: tuple[str, ...] = Field(default_factory=tuple, max_length=128)
    citations: tuple[ConceptCitationV1, ...] = Field(min_length=1, max_length=256)
    entity_types: tuple[ConceptEntityTypeV1, ...] = Field(min_length=1, max_length=128)
    relationship_types: tuple[ConceptRelationshipTypeV1, ...] = Field(default_factory=tuple, max_length=128)
    terminology: tuple[ConceptTerminologyV1, ...] = Field(default_factory=tuple, max_length=128)
    exclusions: tuple[str, ...] = Field(min_length=1, max_length=128)
    conflicts: tuple[ConceptConflictV1, ...] = Field(default_factory=tuple, max_length=128)
    unknowns: tuple[str, ...] = Field(default_factory=tuple, max_length=128)
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    created_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator(
        "session_id",
        "correlation_id",
        "goal_ref",
        "source_profile_proposal_id",
        "prior_proposal_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("source_profile_proposal_digest", "prior_proposal_digest", "proposal_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("citations")
    @classmethod
    def normalize_citation_records(cls, value: tuple[ConceptCitationV1, ...]) -> tuple[ConceptCitationV1, ...]:
        return sorted_unique(value, key=lambda item: item.citation_id, label="concept citations")

    @field_validator("entity_types")
    @classmethod
    def normalize_entities(cls, value: tuple[ConceptEntityTypeV1, ...]) -> tuple[ConceptEntityTypeV1, ...]:
        return sorted_unique(value, key=lambda item: item.type_id, label="concept entity types", maximum=128)

    @field_validator("relationship_types")
    @classmethod
    def normalize_relationships(
        cls, value: tuple[ConceptRelationshipTypeV1, ...]
    ) -> tuple[ConceptRelationshipTypeV1, ...]:
        return sorted_unique(value, key=lambda item: item.type_id, label="concept relationship types", maximum=128)

    @field_validator("terminology")
    @classmethod
    def normalize_terminology(cls, value: tuple[ConceptTerminologyV1, ...]) -> tuple[ConceptTerminologyV1, ...]:
        return sorted_unique(value, key=lambda item: item.term_id, label="concept terminology", maximum=128)

    @field_validator("conflicts")
    @classmethod
    def normalize_conflicts(cls, value: tuple[ConceptConflictV1, ...]) -> tuple[ConceptConflictV1, ...]:
        return sorted_unique(value, key=lambda item: item.conflict_id, label="concept conflicts", maximum=128)

    @field_validator("exclusions", "unknowns", "semantic_diff", mode="before")
    @classmethod
    def normalize_text_sets(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            bounded_text(item, name=info.field_name, maximum=1_000)
            for item in normalized_strings(value, label=info.field_name, maximum=128)
        )

    @field_validator("edit_summary")
    @classmethod
    def validate_edit_summary(cls, value: str | None) -> str | None:
        return bounded_text(value, name="edit_summary", maximum=1_000) if value is not None else None

    @field_validator("user_intent")
    @classmethod
    def validate_user_intent(cls, value: str) -> str:
        return bounded_text(value, name="user_intent", maximum=2_000)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="created_at")

    @model_validator(mode="after")
    def validate_model_and_identity(self) -> Self:
        has_prior = self.prior_proposal_id is not None or self.prior_proposal_digest is not None
        if self.revision == 1 and (has_prior or self.edit_summary is not None or self.semantic_diff):
            raise ValueError("first concept-model proposal cannot carry edit lineage")
        if self.revision > 1 and (
            self.prior_proposal_id is None
            or self.prior_proposal_digest is None
            or self.edit_summary is None
            or not self.semantic_diff
        ):
            raise ValueError("edited concept-model proposal requires exact prior lineage and semantic diff")
        citation_ids = {item.citation_id for item in self.citations}
        referenced = set()
        entity_ids = {item.type_id for item in self.entity_types}
        for entity in self.entity_types:
            referenced.update(entity.citation_ids)
            for attribute in entity.attributes:
                referenced.update(attribute.citation_ids)
        for relationship in self.relationship_types:
            if relationship.from_type_id not in entity_ids or relationship.to_type_id not in entity_ids:
                raise ValueError("relationship endpoints must name declared entity types")
            referenced.update(relationship.citation_ids)
        for term in self.terminology:
            referenced.update(term.citation_ids)
        for conflict in self.conflicts:
            referenced.update(conflict.citation_ids)
        if referenced != citation_ids:
            raise ValueError("every concept citation must be valid and attributed exactly once or more")
        all_type_ids = entity_ids | {item.type_id for item in self.relationship_types}
        if len(all_type_ids) != len(entity_ids) + len(self.relationship_types):
            raise ValueError("entity and relationship type identifiers must not collide")
        derive_builder_identity(
            self,
            prefix="concept_model_proposal",
            id_field="proposal_id",
            digest_field="proposal_digest",
        )
        return self


class ConceptModelDispositionV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.concept-model-disposition/v1alpha1"] = CONCEPT_MODEL_DISPOSITION_VERSION
    session_id: str
    proposal_id: str
    proposal_digest: str
    disposition: Literal["approved"] = "approved"
    actor_ref: str
    approval_receipt_ref: str
    approved_at: datetime
    disposition_id: str | None = None
    disposition_digest: str | None = None

    @field_validator("session_id", "proposal_id", "actor_ref", "approval_receipt_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("proposal_digest", "disposition_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("approved_at")
    @classmethod
    def validate_approved_at(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="approved_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        derive_builder_identity(
            self,
            prefix="concept_model_disposition",
            id_field="disposition_id",
            digest_field="disposition_digest",
        )
        return self


def concept_model_semantic_diff(
    prior: ConceptModelProposalV1,
    edited: ConceptModelProposalV1,
) -> tuple[str, ...]:
    """Return the exact deterministic public diff between two concept revisions."""

    changes: list[str] = []
    for field_name, key_name in (
        ("citations", "citation_id"),
        ("entity_types", "type_id"),
        ("relationship_types", "type_id"),
        ("terminology", "term_id"),
        ("conflicts", "conflict_id"),
    ):
        before = {getattr(item, key_name): item for item in getattr(prior, field_name)}
        after = {getattr(item, key_name): item for item in getattr(edited, field_name)}
        changes.extend(f"{field_name}.added:{key}" for key in after.keys() - before.keys())
        changes.extend(f"{field_name}.removed:{key}" for key in before.keys() - after.keys())
        changes.extend(
            f"{field_name}.changed:{key}"
            for key in before.keys() & after.keys()
            if before[key] != after[key]
        )
    for field_name in ("exclusions", "unknowns"):
        before = set(getattr(prior, field_name))
        after = set(getattr(edited, field_name))
        changes.extend(f"{field_name}.added:{item}" for item in after - before)
        changes.extend(f"{field_name}.removed:{item}" for item in before - after)
    if prior.confidence != edited.confidence:
        changes.append(f"confidence.changed:{prior.confidence}->{edited.confidence}")
    return tuple(sorted(changes))


__all__ = [
    "CONCEPT_MODEL_DISPOSITION_VERSION",
    "CONCEPT_MODEL_PROPOSAL_VERSION",
    "ConceptAttributeV1",
    "ConceptCitationV1",
    "ConceptConflictV1",
    "ConceptEntityTypeV1",
    "ConceptModelDispositionV1",
    "ConceptModelProposalV1",
    "ConceptRelationshipTypeV1",
    "ConceptTerminologyV1",
    "ConceptValueKind",
    "OrganizationTerminologyV1",
    "concept_model_semantic_diff",
]
