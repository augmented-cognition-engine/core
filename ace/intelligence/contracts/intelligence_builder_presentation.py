"""Domain-neutral presentation contracts for the Intelligence Builder journey."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.common import (
    normalized_strings,
    sorted_unique,
    validate_digest,
    validate_reference,
    validate_slug,
)

INTELLIGENCE_ONBOARDING_PROFILE_VERSION = "ace.intelligence.onboarding-profile/v1alpha1"


class _BuilderPresentationContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _text(value: str, *, name: str, maximum: int = 2_000) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


class IntelligenceOnboardingOutcomeV1Alpha1(_BuilderPresentationContract):
    outcome_id: str
    label: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1_000)
    icon_hint: str
    recommended_watch_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    recommended_intelligence_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    recommended_topic_labels: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    recommended_intelligence_labels: tuple[str, ...] = Field(default_factory=tuple, max_length=32)

    @field_validator("outcome_id", "icon_hint")
    @classmethod
    def slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("recommended_watch_ids", "recommended_intelligence_ids", mode="before")
    @classmethod
    def ids(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name=info.field_name)
            for item in normalized_strings(value, label=info.field_name, maximum=32)
        )

    @field_validator("recommended_topic_labels", "recommended_intelligence_labels", mode="before")
    @classmethod
    def labels(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            _text(item, name=info.field_name, maximum=160)
            for item in normalized_strings(value, label=info.field_name, maximum=32)
        )


class IntelligenceOnboardingCadenceV1Alpha1(_BuilderPresentationContract):
    cadence_id: str
    label: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1_000)

    @field_validator("cadence_id")
    @classmethod
    def cadence_slug(cls, value: str) -> str:
        return validate_slug(value, name="cadence_id")


class IntelligenceOnboardingSourceGroupV1Alpha1(_BuilderPresentationContract):
    """One inert, reviewable group of evidence sources proposed during onboarding."""

    source_group_id: str
    label: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1_000)
    evidence_role: str
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    source_labels: tuple[str, ...] = Field(min_length=1, max_length=8)
    access_label: str = Field(min_length=1, max_length=160)
    default_selected: StrictBool = True

    @field_validator("source_group_id", "evidence_role")
    @classmethod
    def slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("source_ids", mode="before")
    @classmethod
    def ids(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="source_ids")
            for item in normalized_strings(value, label="source_ids", maximum=32)
        )

    @field_validator("source_labels", mode="before")
    @classmethod
    def labels(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            _text(item, name="source_labels", maximum=160)
            for item in normalized_strings(value, label="source_labels", maximum=8)
        )


class IntelligenceOnboardingFirstValueV1Alpha1(_BuilderPresentationContract):
    public_sources_first: StrictBool = True
    private_sources_optional: StrictBool = True
    completion_label: str = Field(min_length=1, max_length=160)


class IntelligenceOnboardingGuardrailsV1Alpha1(_BuilderPresentationContract):
    declarative_only: Literal[True] = True
    authorizes_connections: Literal[False] = False
    authorizes_monitors: Literal[False] = False
    proposed_sources_are_not_connected: Literal[True] = True
    feedback_may_reweight_relevance_not_authority: Literal[True] = True


class IntelligenceOnboardingProfileV1Alpha1(_BuilderPresentationContract):
    """One inert domain-supplied starting profile; it grants no runtime authority."""

    contract: Literal["ace.intelligence.onboarding-profile/v1alpha1"] = INTELLIGENCE_ONBOARDING_PROFILE_VERSION
    profile_id: str
    profile_digest: str | None = None
    topic_id: str
    domain_label: str | None = Field(default=None, min_length=1, max_length=160)
    topic_label: str | None = Field(default=None, min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=2_000)
    starter_prompts: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    outcomes: tuple[IntelligenceOnboardingOutcomeV1Alpha1, ...] = Field(min_length=1, max_length=16)
    source_groups: tuple[IntelligenceOnboardingSourceGroupV1Alpha1, ...] = Field(
        default_factory=tuple, max_length=16
    )
    cadences: tuple[IntelligenceOnboardingCadenceV1Alpha1, ...] = Field(min_length=1, max_length=16)
    default_cadence_id: str
    first_value: IntelligenceOnboardingFirstValueV1Alpha1
    guardrails: IntelligenceOnboardingGuardrailsV1Alpha1

    @field_validator("profile_id")
    @classmethod
    def profile_reference(cls, value: str) -> str:
        return validate_reference(value, name="profile_id")

    @field_validator("profile_digest")
    @classmethod
    def digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("topic_id", "default_cadence_id")
    @classmethod
    def profile_slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("starter_prompts", mode="before")
    @classmethod
    def prompts(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            _text(item, name="starter_prompts", maximum=300)
            for item in normalized_strings(value, label="starter_prompts", maximum=8)
        )

    @field_validator("outcomes")
    @classmethod
    def unique_outcomes(
        cls, value: tuple[IntelligenceOnboardingOutcomeV1Alpha1, ...]
    ) -> tuple[IntelligenceOnboardingOutcomeV1Alpha1, ...]:
        return sorted_unique(value, key=lambda item: item.outcome_id, label="onboarding outcomes", maximum=16)

    @field_validator("cadences")
    @classmethod
    def unique_cadences(
        cls, value: tuple[IntelligenceOnboardingCadenceV1Alpha1, ...]
    ) -> tuple[IntelligenceOnboardingCadenceV1Alpha1, ...]:
        return sorted_unique(value, key=lambda item: item.cadence_id, label="onboarding cadences", maximum=16)

    @field_validator("source_groups")
    @classmethod
    def unique_source_groups(
        cls, value: tuple[IntelligenceOnboardingSourceGroupV1Alpha1, ...]
    ) -> tuple[IntelligenceOnboardingSourceGroupV1Alpha1, ...]:
        return sorted_unique(
            value,
            key=lambda item: item.source_group_id,
            label="onboarding source groups",
            maximum=16,
        )

    @model_validator(mode="after")
    def bind_profile(self) -> Self:
        if self.default_cadence_id not in {item.cadence_id for item in self.cadences}:
            raise ValueError("default cadence must name one declared cadence")
        material = self.model_dump(mode="json", exclude={"profile_digest"})
        expected = f"sha256:{canonical_hash(material)}"
        if self.profile_digest not in {None, expected}:
            raise ValueError("profile_digest does not match exact profile material")
        object.__setattr__(self, "profile_digest", expected)
        return self


__all__ = [
    "INTELLIGENCE_ONBOARDING_PROFILE_VERSION",
    "IntelligenceOnboardingCadenceV1Alpha1",
    "IntelligenceOnboardingFirstValueV1Alpha1",
    "IntelligenceOnboardingGuardrailsV1Alpha1",
    "IntelligenceOnboardingOutcomeV1Alpha1",
    "IntelligenceOnboardingProfileV1Alpha1",
    "IntelligenceOnboardingSourceGroupV1Alpha1",
]
