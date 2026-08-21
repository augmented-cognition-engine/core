"""Versioned domain-neutral proposal contracts for the 0.7D Intelligence Agent."""

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
from ace.intelligence.contracts.resources import CanonicalJsonValueV1Alpha1

AUTHORIZED_OBSERVATION_SET_VERSION = "ace.application.authorized-observation-set/v1alpha1"
INTELLIGENCE_MODEL_PROPOSAL_VERSION = "ace.application.intelligence-model-proposal/v1alpha1"
INTELLIGENCE_MODEL_DISPOSITION_VERSION = "ace.application.intelligence-model-disposition/v1alpha1"


class EpistemicClassification(StrEnum):
    OBSERVATION = "observation"
    CLAIM = "claim"
    INFERENCE = "inference"
    DISAGREEMENT = "disagreement"
    UNKNOWN = "unknown"


class WatchTargetKind(StrEnum):
    ATTRIBUTE = "attribute"
    RELATIONSHIP = "relationship"


class DetectorStrategyKind(StrEnum):
    NUMERIC_DELTA = "numeric_delta"
    CATEGORICAL_TRANSITION = "categorical_transition"


class ProposedCadence(StrEnum):
    IMMEDIATE = "immediate"
    DAILY = "daily"
    WEEKLY = "weekly"
    RECORD_ONLY = "record_only"


class AuthorizedObservationV1(IntelligenceBuilderContract):
    source_profile_proposal_id: str
    source_profile_proposal_digest: str
    source_sample_id: str
    source_sample_digest: str
    source_ref: str
    evidence_digest: str
    subject_ref: str
    entity_type_id: str
    attributes: CanonicalJsonValueV1Alpha1
    observed_at: datetime
    admitted_at: datetime
    as_of: datetime
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    disagrees_with_observation_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    unknown_fields: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    observation_id: str | None = None
    observation_digest: str | None = None

    @field_validator("source_profile_proposal_id", "source_sample_id", "source_ref", "subject_ref", "observation_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "source_profile_proposal_digest",
        "source_sample_digest",
        "evidence_digest",
        "observation_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("entity_type_id")
    @classmethod
    def validate_entity_type_id(cls, value: str) -> str:
        return validate_slug(value, name="entity_type_id")

    @field_validator("disagrees_with_observation_ids", mode="before")
    @classmethod
    def normalize_disagreements(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_reference(item, name="observation_id")
            for item in normalized_strings(value, label="disagrees_with_observation_ids", maximum=64)
        )

    @field_validator("unknown_fields", mode="before")
    @classmethod
    def normalize_unknown_fields(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="unknown_field")
            for item in normalized_strings(value, label="unknown_fields", maximum=64)
        )

    @field_validator("observed_at", "admitted_at", "as_of")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return aware_datetime(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_time_and_identity(self) -> Self:
        if not self.observed_at <= self.admitted_at <= self.as_of:
            raise ValueError("observation times must satisfy observed_at <= admitted_at <= as_of")
        derive_builder_identity(
            self,
            prefix="authorized_observation",
            id_field="observation_id",
            digest_field="observation_digest",
        )
        if self.observation_id in self.disagrees_with_observation_ids:
            raise ValueError("an observation cannot disagree with itself")
        return self


class AuthorizedObservationSetV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.authorized-observation-set/v1alpha1"] = AUTHORIZED_OBSERVATION_SET_VERSION
    session_id: str
    correlation_id: str
    source_profile_proposal_id: str
    source_profile_proposal_digest: str
    observations: tuple[AuthorizedObservationV1, ...] = Field(min_length=2, max_length=256)
    closure_complete: StrictBool
    admitted_at: datetime
    observation_set_id: str | None = None
    observation_set_digest: str | None = None

    @field_validator("session_id", "correlation_id", "source_profile_proposal_id", "observation_set_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("source_profile_proposal_digest", "observation_set_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("observations")
    @classmethod
    def normalize_observations(cls, value: tuple[AuthorizedObservationV1, ...]) -> tuple[AuthorizedObservationV1, ...]:
        return sorted_unique(
            value, key=lambda item: str(item.observation_id), label="authorized observations", maximum=256
        )

    @field_validator("admitted_at")
    @classmethod
    def validate_admitted_at(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="admitted_at")

    @model_validator(mode="after")
    def validate_closure_and_identity(self) -> Self:
        ids = {str(item.observation_id) for item in self.observations}
        if len({item.source_ref for item in self.observations}) < 2:
            raise ValueError("authorized observation set requires at least two distinct sources")
        for observation in self.observations:
            if (
                observation.source_profile_proposal_id != self.source_profile_proposal_id
                or observation.source_profile_proposal_digest != self.source_profile_proposal_digest
                or not set(observation.disagrees_with_observation_ids).issubset(ids)
                or observation.admitted_at > self.admitted_at
            ):
                raise ValueError("authorized observation set lost exact source, disagreement, or admission closure")
        derive_builder_identity(
            self,
            prefix="authorized_observation_set",
            id_field="observation_set_id",
            digest_field="observation_set_digest",
        )
        return self


class IntelligenceCitationV1(IntelligenceBuilderContract):
    citation_id: str
    observation_id: str
    observation_digest: str
    source_ref: str
    evidence_digest: str
    field_path: str

    @field_validator("citation_id")
    @classmethod
    def validate_citation_id(cls, value: str) -> str:
        return validate_slug(value, name="citation_id")

    @field_validator("observation_id", "source_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("observation_digest", "evidence_digest")
    @classmethod
    def validate_digests(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("field_path")
    @classmethod
    def validate_field_path(cls, value: str) -> str:
        if not value.startswith("/") or "//" in value or value != value.strip() or len(value) > 240:
            raise ValueError("field_path must be a bounded normalized JSON pointer")
        return value


class WatchTargetV1(IntelligenceBuilderContract):
    target_id: str
    target_kind: WatchTargetKind
    entity_type_id: str
    member_id: str
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=64)

    @field_validator("target_id", "entity_type_id", "member_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return _slugs(value, label="citation_ids")


class BaselineProposalV1(IntelligenceBuilderContract):
    baseline_id: str
    target_id: str
    value: CanonicalJsonValueV1Alpha1
    as_of: datetime
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=64)

    @field_validator("baseline_id", "target_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="as_of")

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return _slugs(value, label="citation_ids")


class DetectorProposalV1(IntelligenceBuilderContract):
    detector_id: str
    target_id: str
    strategy: DetectorStrategyKind
    configuration: CanonicalJsonValueV1Alpha1
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=64)

    @field_validator("detector_id", "target_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return _slugs(value, label="citation_ids")


class MaterialityRuleV1(IntelligenceBuilderContract):
    rule_id: str
    detector_id: str
    minimum_change: StrictFloat = Field(ge=0.0)
    minimum_confidence: StrictFloat = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=1_000)
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=64)

    @field_validator("rule_id", "detector_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return bounded_text(value, name="rationale", maximum=1_000)

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return _slugs(value, label="citation_ids")


class AudienceProposalV1(IntelligenceBuilderContract):
    audience_id: str
    display_name: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=1_000)

    @field_validator("audience_id")
    @classmethod
    def validate_audience_id(cls, value: str) -> str:
        return validate_slug(value, name="audience_id")


class RoutingCadenceProposalV1(IntelligenceBuilderContract):
    route_id: str
    audience_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    target_ids: tuple[str, ...] = Field(min_length=1, max_length=128)
    cadence: ProposedCadence
    minimum_confidence: StrictFloat = Field(ge=0.0, le=1.0)

    @field_validator("route_id")
    @classmethod
    def validate_route_id(cls, value: str) -> str:
        return validate_slug(value, name="route_id")

    @field_validator("audience_ids", "target_ids", mode="before")
    @classmethod
    def normalize_ids(cls, value: Any, info) -> tuple[str, ...]:
        return _slugs(value, label=info.field_name, maximum=128)


class SuppressionGroupingRuleV1(IntelligenceBuilderContract):
    rule_id: str
    target_ids: tuple[str, ...] = Field(min_length=1, max_length=128)
    group_by: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    suppress_below_confidence: StrictFloat = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=1_000)

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, value: str) -> str:
        return validate_slug(value, name="rule_id")

    @field_validator("target_ids", "group_by", mode="before")
    @classmethod
    def normalize_ids(cls, value: Any, info) -> tuple[str, ...]:
        return _slugs(value, label=info.field_name, maximum=128)


class EpistemicStatementV1(IntelligenceBuilderContract):
    statement_id: str
    classification: EpistemicClassification
    statement: str = Field(min_length=1, max_length=2_000)
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    confidence: StrictFloat = Field(ge=0.0, le=1.0)

    @field_validator("statement_id")
    @classmethod
    def validate_statement_id(cls, value: str) -> str:
        return validate_slug(value, name="statement_id")

    @field_validator("statement")
    @classmethod
    def validate_statement(cls, value: str) -> str:
        return bounded_text(value, name="statement", maximum=2_000)

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return _slugs(value, label="citation_ids")


class IntelligenceConflictV1(IntelligenceBuilderContract):
    conflict_id: str
    description: str = Field(min_length=1, max_length=1_000)
    citation_ids: tuple[str, ...] = Field(min_length=2, max_length=64)
    blocks_proposal: StrictBool = False

    @field_validator("conflict_id")
    @classmethod
    def validate_conflict_id(cls, value: str) -> str:
        return validate_slug(value, name="conflict_id")

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_citations(cls, value: Any) -> tuple[str, ...]:
        return _slugs(value, label="citation_ids")


def _slugs(value: Any, *, label: str, maximum: int = 64) -> tuple[str, ...]:
    return tuple(validate_slug(item, name=label) for item in normalized_strings(value, label=label, maximum=maximum))


class IntelligenceModelProposalV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.intelligence-model-proposal/v1alpha1"] = INTELLIGENCE_MODEL_PROPOSAL_VERSION
    session_id: str
    correlation_id: str
    goal_ref: str
    user_intent: str
    concept_model_proposal_id: str
    concept_model_proposal_digest: str
    concept_model_disposition_id: str
    concept_model_disposition_digest: str
    observation_set_id: str
    observation_set_digest: str
    audience_constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    cadence_constraints: tuple[ProposedCadence, ...] = Field(default_factory=tuple, max_length=4)
    revision: StrictInt = Field(ge=1)
    prior_proposal_id: str | None = None
    prior_proposal_digest: str | None = None
    edit_summary: str | None = Field(default=None, max_length=1_000)
    semantic_diff: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    citations: tuple[IntelligenceCitationV1, ...] = Field(min_length=1, max_length=256)
    watch_targets: tuple[WatchTargetV1, ...] = Field(min_length=1, max_length=128)
    baselines: tuple[BaselineProposalV1, ...] = Field(min_length=1, max_length=128)
    detectors: tuple[DetectorProposalV1, ...] = Field(min_length=1, max_length=128)
    materiality_rules: tuple[MaterialityRuleV1, ...] = Field(min_length=1, max_length=128)
    audiences: tuple[AudienceProposalV1, ...] = Field(min_length=1, max_length=64)
    routes: tuple[RoutingCadenceProposalV1, ...] = Field(min_length=1, max_length=128)
    suppression_grouping_rules: tuple[SuppressionGroupingRuleV1, ...] = Field(min_length=1, max_length=128)
    epistemic_statements: tuple[EpistemicStatementV1, ...] = Field(min_length=1, max_length=256)
    conflicts: tuple[IntelligenceConflictV1, ...] = Field(default_factory=tuple, max_length=128)
    unknowns: tuple[str, ...] = Field(min_length=1, max_length=128)
    exclusions: tuple[str, ...] = Field(min_length=1, max_length=128)
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    created_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator(
        "session_id",
        "correlation_id",
        "goal_ref",
        "concept_model_proposal_id",
        "concept_model_disposition_id",
        "observation_set_id",
        "prior_proposal_id",
        "proposal_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "concept_model_proposal_digest",
        "concept_model_disposition_digest",
        "observation_set_digest",
        "prior_proposal_digest",
        "proposal_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("user_intent", "edit_summary")
    @classmethod
    def validate_text(cls, value: str | None, info) -> str | None:
        return bounded_text(value, name=info.field_name, maximum=2_000) if value is not None else None

    @field_validator("audience_constraints", "unknowns", "exclusions", "semantic_diff", mode="before")
    @classmethod
    def normalize_text_sets(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            bounded_text(item, name=info.field_name, maximum=1_000)
            for item in normalized_strings(value, label=info.field_name, maximum=256)
        )

    @field_validator("cadence_constraints")
    @classmethod
    def normalize_cadences(cls, value: tuple[ProposedCadence, ...]) -> tuple[ProposedCadence, ...]:
        if len(value) != len(set(value)):
            raise ValueError("cadence constraints must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="created_at")

    @field_validator("citations")
    @classmethod
    def normalize_citations(cls, value: tuple[IntelligenceCitationV1, ...]) -> tuple[IntelligenceCitationV1, ...]:
        return sorted_unique(value, key=lambda item: item.citation_id, label="intelligence citations", maximum=256)

    @field_validator(
        "watch_targets",
        "baselines",
        "detectors",
        "materiality_rules",
        "audiences",
        "routes",
        "suppression_grouping_rules",
        "epistemic_statements",
        "conflicts",
    )
    @classmethod
    def normalize_declarations(cls, value: tuple[Any, ...], info) -> tuple[Any, ...]:
        key_names = {
            "watch_targets": "target_id",
            "baselines": "baseline_id",
            "detectors": "detector_id",
            "materiality_rules": "rule_id",
            "audiences": "audience_id",
            "routes": "route_id",
            "suppression_grouping_rules": "rule_id",
            "epistemic_statements": "statement_id",
            "conflicts": "conflict_id",
        }
        return sorted_unique(
            value, key=lambda item: getattr(item, key_names[info.field_name]), label=info.field_name, maximum=256
        )

    @model_validator(mode="after")
    def validate_graph_and_identity(self) -> Self:
        has_prior = self.prior_proposal_id is not None or self.prior_proposal_digest is not None
        if self.revision == 1 and (has_prior or self.edit_summary is not None or self.semantic_diff):
            raise ValueError("first intelligence-model proposal cannot carry edit lineage")
        if self.revision > 1 and (
            self.prior_proposal_id is None
            or self.prior_proposal_digest is None
            or self.edit_summary is None
            or not self.semantic_diff
        ):
            raise ValueError("edited intelligence-model proposal requires exact lineage and semantic diff")
        citation_ids = {item.citation_id for item in self.citations}
        target_ids = {item.target_id for item in self.watch_targets}
        detector_ids = {item.detector_id for item in self.detectors}
        audience_ids = {item.audience_id for item in self.audiences}
        referenced_citations: set[str] = set()
        for collection in (
            self.watch_targets,
            self.baselines,
            self.detectors,
            self.materiality_rules,
            self.epistemic_statements,
            self.conflicts,
        ):
            for item in collection:
                referenced_citations.update(item.citation_ids)
        if referenced_citations != citation_ids:
            raise ValueError("every intelligence citation must be used and every citation reference must resolve")
        if any(item.target_id not in target_ids for item in (*self.baselines, *self.detectors)):
            raise ValueError("baselines and detectors must name declared watch targets")
        if any(item.detector_id not in detector_ids for item in self.materiality_rules):
            raise ValueError("materiality rules must name declared detectors")
        if any(
            not set(item.audience_ids).issubset(audience_ids) or not set(item.target_ids).issubset(target_ids)
            for item in self.routes
        ):
            raise ValueError("routes must name declared audiences and watch targets")
        if any(not set(item.target_ids).issubset(target_ids) for item in self.suppression_grouping_rules):
            raise ValueError("suppression/grouping rules must name declared watch targets")
        required_classes = set(EpistemicClassification)
        if not required_classes.issubset({item.classification for item in self.epistemic_statements}):
            raise ValueError("intelligence proposal must expose every domain-neutral epistemic classification")
        derive_builder_identity(
            self, prefix="intelligence_model_proposal", id_field="proposal_id", digest_field="proposal_digest"
        )
        return self


class IntelligenceModelDispositionV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.intelligence-model-disposition/v1alpha1"] = (
        INTELLIGENCE_MODEL_DISPOSITION_VERSION
    )
    session_id: str
    proposal_id: str
    proposal_digest: str
    disposition: Literal["approved"] = "approved"
    actor_ref: str
    approval_receipt_ref: str
    approved_at: datetime
    disposition_id: str | None = None
    disposition_digest: str | None = None

    @field_validator("session_id", "proposal_id", "actor_ref", "approval_receipt_ref", "disposition_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

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
            self, prefix="intelligence_model_disposition", id_field="disposition_id", digest_field="disposition_digest"
        )
        return self


def intelligence_model_semantic_diff(
    prior: IntelligenceModelProposalV1, edited: IntelligenceModelProposalV1
) -> tuple[str, ...]:
    """Return the deterministic public diff between two intelligence-model revisions."""

    changes: list[str] = []
    for field_name, key_name in (
        ("citations", "citation_id"),
        ("watch_targets", "target_id"),
        ("baselines", "baseline_id"),
        ("detectors", "detector_id"),
        ("materiality_rules", "rule_id"),
        ("audiences", "audience_id"),
        ("routes", "route_id"),
        ("suppression_grouping_rules", "rule_id"),
        ("epistemic_statements", "statement_id"),
        ("conflicts", "conflict_id"),
    ):
        before = {getattr(item, key_name): item for item in getattr(prior, field_name)}
        after = {getattr(item, key_name): item for item in getattr(edited, field_name)}
        changes.extend(f"{field_name}.added:{key}" for key in after.keys() - before.keys())
        changes.extend(f"{field_name}.removed:{key}" for key in before.keys() - after.keys())
        changes.extend(
            f"{field_name}.changed:{key}" for key in before.keys() & after.keys() if before[key] != after[key]
        )
    for field_name in ("audience_constraints", "cadence_constraints", "unknowns", "exclusions"):
        before = set(getattr(prior, field_name))
        after = set(getattr(edited, field_name))
        changes.extend(f"{field_name}.added:{item}" for item in after - before)
        changes.extend(f"{field_name}.removed:{item}" for item in before - after)
    if prior.confidence != edited.confidence:
        changes.append(f"confidence.changed:{prior.confidence}->{edited.confidence}")
    return tuple(sorted(changes))


__all__ = [
    "AUTHORIZED_OBSERVATION_SET_VERSION",
    "INTELLIGENCE_MODEL_DISPOSITION_VERSION",
    "INTELLIGENCE_MODEL_PROPOSAL_VERSION",
    "AudienceProposalV1",
    "AuthorizedObservationSetV1",
    "AuthorizedObservationV1",
    "BaselineProposalV1",
    "CanonicalJsonValueV1Alpha1",
    "DetectorProposalV1",
    "DetectorStrategyKind",
    "EpistemicClassification",
    "EpistemicStatementV1",
    "IntelligenceCitationV1",
    "IntelligenceConflictV1",
    "IntelligenceModelDispositionV1",
    "IntelligenceModelProposalV1",
    "MaterialityRuleV1",
    "ProposedCadence",
    "RoutingCadenceProposalV1",
    "SuppressionGroupingRuleV1",
    "WatchTargetKind",
    "WatchTargetV1",
    "intelligence_model_semantic_diff",
]
