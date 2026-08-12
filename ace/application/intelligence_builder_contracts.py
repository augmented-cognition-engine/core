"""Domain-neutral public contracts for the Intelligence Builder onboarding journey.

These application contracts remain opaque payloads to Core. They coordinate
proposal-only agent handoffs without granting connector, persistence, scheduling,
delivery, or activation authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    normalized_strings,
    sorted_unique,
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
)

SOURCE_OPTION_CATALOG_VERSION = "ace.application.source-option-catalog/v1alpha1"
SOURCE_SCOPE_PROPOSAL_VERSION = "ace.application.source-scope-proposal/v1alpha1"
SOURCE_SAMPLE_VERSION = "ace.application.source-sample/v1alpha1"
SOURCE_PROFILE_PROPOSAL_VERSION = "ace.application.source-profile-proposal/v1alpha1"
ONBOARDING_ARTIFACT_REFERENCE_VERSION = "ace.application.onboarding-artifact-reference/v1alpha1"
ONBOARDING_SESSION_REVISION_VERSION = "ace.application.intelligence-builder-session-revision/v1alpha1"


class IntelligenceBuilderContract(FrozenContract):
    """Strict frozen base shared by versioned Intelligence Builder artifacts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def aware_datetime(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def bounded_text(value: str, *, name: str, maximum: int = 2_000) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def derive_builder_identity(
    instance: IntelligenceBuilderContract,
    *,
    prefix: str,
    id_field: str,
    digest_field: str,
) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact proposal material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact proposal material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class ConnectionEffect(StrEnum):
    CONNECTION_TEST = "connection_test"
    BOUNDED_SAMPLE = "bounded_sample"


class SourceValueKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    REFERENCE = "reference"
    UNKNOWN = "unknown"


class OnboardingStage(StrEnum):
    GOAL_SELECTED = "goal_selected"
    SOURCES_CONNECTING = "sources_connecting"
    SOURCES_READY = "sources_ready"
    CONCEPT_MODEL_PROPOSED = "concept_model_proposed"
    CONCEPT_MODEL_APPROVED = "concept_model_approved"
    INTELLIGENCE_MODEL_PROPOSED = "intelligence_model_proposed"
    INTELLIGENCE_MODEL_APPROVED = "intelligence_model_approved"
    FIRST_BRIEFING_READY = "first_briefing_ready"
    ACTIVATION_PENDING = "activation_pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    RETRYING = "retrying"


class OnboardingBlockReason(StrEnum):
    FAILED_CONNECTOR = "failed_connector"
    INSUFFICIENT_PERMISSION = "insufficient_permission"
    LOW_CONFIDENCE_MAPPING = "low_confidence_mapping"
    CONFLICTING_SOURCES = "conflicting_sources"
    NO_MATERIAL_SHIFTS = "no_material_shifts"


class OnboardingTransitionAuthority(StrEnum):
    PRODUCT_INPUT = "product_input"
    AGENT_PROPOSAL = "agent_proposal"
    HUMAN_CORE_DISPOSITION = "human_core_disposition"
    CORE_ACTIVATION = "core_activation"


class OnboardingArtifactKind(StrEnum):
    SOURCE_SCOPE_PROPOSAL = "source_scope_proposal"
    SOURCE_PROFILE_PROPOSAL = "source_profile_proposal"
    CONCEPT_MODEL_PROPOSAL = "concept_model_proposal"
    CONCEPT_MODEL_DISPOSITION = "concept_model_disposition"
    INTELLIGENCE_MODEL_PROPOSAL = "intelligence_model_proposal"
    FIRST_BRIEFING_PREVIEW = "first_briefing_preview"
    ACTIVATION_PLAN = "activation_plan"
    ACTIVATION_RECEIPT = "activation_receipt"
    UPDATE = "update"
    FEEDBACK = "feedback"


class SourceOptionV1(IntelligenceBuilderContract):
    """One host-described source option; it contains no credential material."""

    option_id: str
    display_name: str = Field(min_length=1, max_length=160)
    connector_ref: str
    connector_digest: str
    source_type_ref: str
    source_ref: str
    permission_options: tuple[str, ...] = Field(min_length=1, max_length=64)
    scope_options: tuple[str, ...] = Field(min_length=1, max_length=128)
    allowed_effects: tuple[ConnectionEffect, ...] = Field(min_length=1, max_length=2)
    maximum_sample_records: StrictInt = Field(ge=1, le=100)

    @field_validator("option_id")
    @classmethod
    def validate_option_id(cls, value: str) -> str:
        return validate_slug(value, name="option_id")

    @field_validator("connector_ref", "source_type_ref", "source_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("connector_digest")
    @classmethod
    def validate_connector_digest(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("permission_options", "scope_options", mode="before")
    @classmethod
    def normalize_options(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name=info.field_name)
            for item in normalized_strings(value, label=info.field_name, maximum=128)
        )

    @field_validator("allowed_effects")
    @classmethod
    def normalize_effects(cls, value: tuple[ConnectionEffect, ...]) -> tuple[ConnectionEffect, ...]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_effects must be unique")
        return tuple(sorted(value, key=lambda item: item.value))


class SourceOptionCatalogV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.source-option-catalog/v1alpha1"] = SOURCE_OPTION_CATALOG_VERSION
    provider_ref: str
    provider_digest: str
    options: tuple[SourceOptionV1, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    catalog_id: str | None = None
    catalog_digest: str | None = None

    @field_validator("provider_ref")
    @classmethod
    def validate_provider_ref(cls, value: str) -> str:
        return validate_reference(value, name="provider_ref")

    @field_validator("provider_digest", "catalog_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("options")
    @classmethod
    def normalize_source_options(cls, value: tuple[SourceOptionV1, ...]) -> tuple[SourceOptionV1, ...]:
        return sorted_unique(value, key=lambda item: item.option_id, label="source options")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        derive_builder_identity(
            self,
            prefix="source_option_catalog",
            id_field="catalog_id",
            digest_field="catalog_digest",
        )
        return self


class SourceScopeSelectionV1(IntelligenceBuilderContract):
    option_id: str
    permissions: tuple[str, ...] = Field(min_length=1, max_length=64)
    scopes: tuple[str, ...] = Field(min_length=1, max_length=128)
    effects: tuple[ConnectionEffect, ...] = Field(min_length=1, max_length=2)
    sample_records: StrictInt = Field(ge=1, le=100)

    @field_validator("option_id")
    @classmethod
    def validate_option_id(cls, value: str) -> str:
        return validate_slug(value, name="option_id")

    @field_validator("permissions", "scopes", mode="before")
    @classmethod
    def normalize_scope(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name=info.field_name)
            for item in normalized_strings(value, label=info.field_name, maximum=128)
        )

    @field_validator("effects")
    @classmethod
    def normalize_effects(cls, value: tuple[ConnectionEffect, ...]) -> tuple[ConnectionEffect, ...]:
        if len(value) != len(set(value)):
            raise ValueError("effects must be unique")
        return tuple(sorted(value, key=lambda item: item.value))


class SourceScopeProposalV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.source-scope-proposal/v1alpha1"] = SOURCE_SCOPE_PROPOSAL_VERSION
    session_id: str
    goal_ref: str
    catalog_id: str
    catalog_digest: str
    selections: tuple[SourceScopeSelectionV1, ...] = Field(min_length=1, max_length=32)
    created_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator("session_id", "goal_ref", "catalog_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("catalog_digest", "proposal_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("selections")
    @classmethod
    def normalize_selections(
        cls, value: tuple[SourceScopeSelectionV1, ...]
    ) -> tuple[SourceScopeSelectionV1, ...]:
        return sorted_unique(value, key=lambda item: item.option_id, label="source scope selections", maximum=32)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="created_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        derive_builder_identity(
            self,
            prefix="source_scope_proposal",
            id_field="proposal_id",
            digest_field="proposal_digest",
        )
        return self


class SourceFieldProfileV1(IntelligenceBuilderContract):
    field_path: str
    value_kind: SourceValueKind
    nullable: StrictBool
    observed_count: StrictInt = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("field_path")
    @classmethod
    def validate_field_path(cls, value: str) -> str:
        if not value.startswith("/") or len(value) > 240 or "//" in value or value != value.strip():
            raise ValueError("field_path must be a bounded normalized JSON pointer")
        return value


class SourceSampleV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.source-sample/v1alpha1"] = SOURCE_SAMPLE_VERSION
    option_id: str
    connector_ref: str
    connector_digest: str
    source_ref: str
    scope_proposal_id: str
    scope_proposal_digest: str
    permissions: tuple[str, ...] = Field(min_length=1, max_length=64)
    scopes: tuple[str, ...] = Field(min_length=1, max_length=128)
    effects_performed: tuple[ConnectionEffect, ...] = Field(min_length=1, max_length=2)
    sample_records: StrictInt = Field(ge=1, le=100)
    fields: tuple[SourceFieldProfileV1, ...] = Field(min_length=1, max_length=256)
    evidence_digest: str
    observed_at: datetime
    authoritative_config_persisted: Literal[False] = False
    scheduled: Literal[False] = False
    delivered: Literal[False] = False
    sample_id: str | None = None
    sample_digest: str | None = None

    @field_validator("option_id")
    @classmethod
    def validate_option_id(cls, value: str) -> str:
        return validate_slug(value, name="option_id")

    @field_validator("connector_ref", "source_ref", "scope_proposal_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("connector_digest", "scope_proposal_digest", "evidence_digest", "sample_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("permissions", "scopes", mode="before")
    @classmethod
    def normalize_scope(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name=info.field_name)
            for item in normalized_strings(value, label=info.field_name, maximum=128)
        )

    @field_validator("effects_performed")
    @classmethod
    def normalize_effects(cls, value: tuple[ConnectionEffect, ...]) -> tuple[ConnectionEffect, ...]:
        if len(value) != len(set(value)):
            raise ValueError("effects_performed must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("fields")
    @classmethod
    def normalize_fields(cls, value: tuple[SourceFieldProfileV1, ...]) -> tuple[SourceFieldProfileV1, ...]:
        return sorted_unique(value, key=lambda item: item.field_path, label="source fields")

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="observed_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        derive_builder_identity(
            self,
            prefix="source_sample",
            id_field="sample_id",
            digest_field="sample_digest",
        )
        return self


class SourceProfileProposalV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.source-profile-proposal/v1alpha1"] = (
        SOURCE_PROFILE_PROPOSAL_VERSION
    )
    session_id: str
    scope_proposal_id: str
    scope_proposal_digest: str
    samples: tuple[SourceSampleV1, ...] = Field(min_length=1, max_length=32)
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    created_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator("session_id", "scope_proposal_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("scope_proposal_digest", "proposal_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("samples")
    @classmethod
    def normalize_samples(cls, value: tuple[SourceSampleV1, ...]) -> tuple[SourceSampleV1, ...]:
        return sorted_unique(value, key=lambda item: item.option_id, label="source samples", maximum=32)

    @field_validator("limitations", mode="before")
    @classmethod
    def normalize_limitations(cls, value: Any) -> tuple[str, ...]:
        values = normalized_strings(value, label="limitations", maximum=64)
        return tuple(bounded_text(item, name="limitation", maximum=500) for item in values)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="created_at")

    @model_validator(mode="after")
    def validate_and_derive(self) -> Self:
        if any(
            sample.scope_proposal_id != self.scope_proposal_id
            or sample.scope_proposal_digest != self.scope_proposal_digest
            for sample in self.samples
        ):
            raise ValueError("every source sample must bind the exact scope proposal")
        derive_builder_identity(
            self,
            prefix="source_profile_proposal",
            id_field="proposal_id",
            digest_field="proposal_digest",
        )
        return self


class OnboardingArtifactReferenceV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.onboarding-artifact-reference/v1alpha1"] = (
        ONBOARDING_ARTIFACT_REFERENCE_VERSION
    )
    artifact_kind: OnboardingArtifactKind
    artifact_id: str
    artifact_digest: str

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        return validate_reference(value, name="artifact_id")

    @field_validator("artifact_digest")
    @classmethod
    def validate_artifact_digest(cls, value: str) -> str:
        return validate_digest(value)


class IntelligenceBuilderSessionRevisionV1(IntelligenceBuilderContract):
    contract: Literal["ace.application.intelligence-builder-session-revision/v1alpha1"] = (
        ONBOARDING_SESSION_REVISION_VERSION
    )
    product_id: str
    session_id: str
    correlation_id: str
    goal_ref: str
    sequence: StrictInt = Field(ge=1)
    stage: OnboardingStage
    prior_revision_id: str | None = None
    prior_revision_digest: str | None = None
    transition_authority: OnboardingTransitionAuthority
    transition_actor_ref: str
    approval_receipt_ref: str | None = None
    artifacts: tuple[OnboardingArtifactReferenceV1, ...] = Field(default_factory=tuple, max_length=32)
    block_reason: OnboardingBlockReason | None = None
    resume_stage: OnboardingStage | None = None
    safe_diagnostic: str | None = Field(default=None, max_length=500)
    occurred_at: datetime
    revision_id: str | None = None
    revision_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator(
        "session_id",
        "correlation_id",
        "goal_ref",
        "prior_revision_id",
        "transition_actor_ref",
        "approval_receipt_ref",
        "revision_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("prior_revision_digest", "revision_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("artifacts")
    @classmethod
    def normalize_artifacts(
        cls, value: tuple[OnboardingArtifactReferenceV1, ...]
    ) -> tuple[OnboardingArtifactReferenceV1, ...]:
        return sorted_unique(
            value,
            key=lambda item: item.artifact_kind.value,
            label="onboarding artifact references",
            maximum=32,
        )

    @field_validator("safe_diagnostic")
    @classmethod
    def validate_safe_diagnostic(cls, value: str | None) -> str | None:
        return bounded_text(value, name="safe_diagnostic", maximum=500) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="occurred_at")

    @model_validator(mode="after")
    def validate_chain_state_and_identity(self) -> Self:
        if self.sequence == 1 and (self.prior_revision_id is not None or self.prior_revision_digest is not None):
            raise ValueError("the first onboarding revision cannot name prior material")
        if self.sequence > 1 and (self.prior_revision_id is None or self.prior_revision_digest is None):
            raise ValueError("later onboarding revisions require exact prior material")
        if self.stage in {OnboardingStage.BLOCKED, OnboardingStage.RETRYING}:
            if self.block_reason is None or self.resume_stage is None:
                raise ValueError("blocked and retrying sessions require a reason and resume stage")
            if self.resume_stage in {
                OnboardingStage.BLOCKED,
                OnboardingStage.RETRYING,
                OnboardingStage.ACTIVE,
            }:
                raise ValueError("resume_stage must name one nonterminal primary onboarding stage")
        elif self.block_reason is not None or self.resume_stage is not None or self.safe_diagnostic is not None:
            raise ValueError("only blocked or retrying sessions may carry blocked-state material")
        requires_approval = self.transition_authority in {
            OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION,
            OnboardingTransitionAuthority.CORE_ACTIVATION,
        }
        if requires_approval != (self.approval_receipt_ref is not None):
            raise ValueError("disposition transitions require one approval receipt and proposal transitions forbid one")
        derive_builder_identity(
            self,
            prefix="intelligence_builder_session_revision",
            id_field="revision_id",
            digest_field="revision_digest",
        )
        return self


__all__ = [
    "ConnectionEffect",
    "IntelligenceBuilderContract",
    "IntelligenceBuilderSessionRevisionV1",
    "ONBOARDING_ARTIFACT_REFERENCE_VERSION",
    "ONBOARDING_SESSION_REVISION_VERSION",
    "OnboardingArtifactKind",
    "OnboardingArtifactReferenceV1",
    "OnboardingBlockReason",
    "OnboardingStage",
    "OnboardingTransitionAuthority",
    "SOURCE_OPTION_CATALOG_VERSION",
    "SOURCE_PROFILE_PROPOSAL_VERSION",
    "SOURCE_SAMPLE_VERSION",
    "SOURCE_SCOPE_PROPOSAL_VERSION",
    "SourceFieldProfileV1",
    "SourceOptionCatalogV1",
    "SourceOptionV1",
    "SourceProfileProposalV1",
    "SourceSampleV1",
    "SourceScopeProposalV1",
    "SourceScopeSelectionV1",
    "SourceValueKind",
    "aware_datetime",
    "bounded_text",
    "derive_builder_identity",
]
