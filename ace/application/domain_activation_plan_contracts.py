"""Additive exact-plan contracts for governed Domain Activation.

The v1alpha1 Domain Activation contracts remain unchanged.  This sibling
contract binds a separately approved activation plan to one exact embedded
v1alpha1 activation specification and to the requested runtime effects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, StrictInt, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.activation import (
    AuthorityBindingV1,
    CapabilityBindingV1,
    DomainActivationSpecV1,
)
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    normalized_strings,
    sorted_unique,
    validate_digest,
    validate_reference,
    validate_slug,
)

INTELLIGENCE_ACTIVATION_PLAN_V1ALPHA2_VERSION = (
    "ace.application.intelligence-activation-plan/v1alpha2"
)
DOMAIN_ACTIVATION_REVISION_V1ALPHA2_VERSION = (
    "ace.intelligence.domain-activation-revision/v1alpha2"
)
DOMAIN_ACTIVATION_COMMIT_REFERENCE_V1ALPHA2_VERSION = (
    "ace.application.domain-activation-commit-reference/v1alpha2"
)


class ActivationPlanAction(StrEnum):
    INITIAL_ACTIVATION = "initial_activation"
    UPGRADE = "upgrade"
    SUSPEND = "suspend"
    REACTIVATE = "reactivate"
    ROLLBACK = "rollback"
    RETIRE = "retire"


class ActivationRuntimeState(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class ActivationRequestedEffect(StrEnum):
    PACK_ACTIVATION = "pack_activation"
    MONITOR_BINDING = "monitor_binding"
    SUBSCRIPTION_BINDING = "subscription_binding"
    SHIFT_DERIVATION = "shift_derivation"
    BRIEF_SYNTHESIS = "brief_synthesis"
    ACTIVATION_SUSPENSION = "activation_suspension"
    ACTIVATION_RETIREMENT = "activation_retirement"


_LIVE_ACTIONS = {
    ActivationPlanAction.INITIAL_ACTIVATION,
    ActivationPlanAction.UPGRADE,
    ActivationPlanAction.REACTIVATE,
    ActivationPlanAction.ROLLBACK,
}
_LIVE_EFFECTS = {
    ActivationRequestedEffect.PACK_ACTIVATION,
    ActivationRequestedEffect.MONITOR_BINDING,
    ActivationRequestedEffect.SUBSCRIPTION_BINDING,
    ActivationRequestedEffect.SHIFT_DERIVATION,
    ActivationRequestedEffect.BRIEF_SYNTHESIS,
}


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _material_digest(value: Any) -> str:
    return f"sha256:{canonical_hash(value)}"


class IntelligenceActivationPlanV1Alpha2(FrozenContract):
    """Immutable plan that is the exact subject of human/Core approval."""

    contract: Literal[
        "ace.application.intelligence-activation-plan/v1alpha2"
    ] = INTELLIGENCE_ACTIVATION_PLAN_V1ALPHA2_VERSION
    action: ActivationPlanAction
    spec: DomainActivationSpecV1
    embedded_spec_id: str | None = None
    embedded_spec_digest: str | None = None
    requested_effects: tuple[ActivationRequestedEffect, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )
    requested_effects_digest: str | None = None
    requested_capabilities: tuple[CapabilityBindingV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_DECLARATIONS,
    )
    requested_capabilities_digest: str | None = None
    requested_authorities: tuple[AuthorityBindingV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_DECLARATIONS,
    )
    requested_authorities_digest: str | None = None
    expected_head_revision_id: str | None = None
    rollback_target_revision_id: str | None = None
    rollback_target_revision_digest: str | None = None
    created_at: datetime
    plan_id: str | None = None
    plan_digest: str | None = None

    @field_validator("requested_effects", mode="before")
    @classmethod
    def normalize_effects(cls, value: Any) -> tuple[ActivationRequestedEffect, ...]:
        values = normalized_strings(value, label="requested effects")
        return tuple(sorted({ActivationRequestedEffect(item) for item in values}, key=lambda item: item.value))

    @field_validator("requested_capabilities")
    @classmethod
    def normalize_capabilities(
        cls,
        value: tuple[CapabilityBindingV1, ...],
    ) -> tuple[CapabilityBindingV1, ...]:
        return sorted_unique(
            value,
            key=lambda item: item.requirement_id,
            label="requested capabilities",
        )

    @field_validator("requested_authorities")
    @classmethod
    def normalize_authorities(
        cls,
        value: tuple[AuthorityBindingV1, ...],
    ) -> tuple[AuthorityBindingV1, ...]:
        return sorted_unique(
            value,
            key=lambda item: item.request_id,
            label="requested authorities",
        )

    @field_validator(
        "embedded_spec_id",
        "expected_head_revision_id",
        "rollback_target_revision_id",
        "plan_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "embedded_spec_digest",
        "requested_effects_digest",
        "requested_capabilities_digest",
        "requested_authorities_digest",
        "rollback_target_revision_digest",
        "plan_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, name="created_at")

    @model_validator(mode="after")
    def validate_and_derive(self) -> Self:
        if self.spec.spec_id is None or self.spec.spec_hash is None:
            raise ValueError("activation plan requires an exact embedded activation specification")

        expected_spec_id = self.spec.spec_id
        expected_spec_digest = f"sha256:{self.spec.spec_hash}"
        if self.embedded_spec_id is not None and self.embedded_spec_id != expected_spec_id:
            raise ValueError("embedded activation specification identity does not match exact material")
        if self.embedded_spec_digest is not None and self.embedded_spec_digest != expected_spec_digest:
            raise ValueError("embedded activation specification digest does not match exact material")
        object.__setattr__(self, "embedded_spec_id", expected_spec_id)
        object.__setattr__(self, "embedded_spec_digest", expected_spec_digest)

        effect_digest = _material_digest([item.value for item in self.requested_effects])
        capability_digest = _material_digest(
            [item.model_dump(mode="json") for item in self.requested_capabilities]
        )
        authority_digest = _material_digest(
            [item.model_dump(mode="json") for item in self.requested_authorities]
        )
        for field_name, supplied, expected in (
            ("requested_effects_digest", self.requested_effects_digest, effect_digest),
            (
                "requested_capabilities_digest",
                self.requested_capabilities_digest,
                capability_digest,
            ),
            (
                "requested_authorities_digest",
                self.requested_authorities_digest,
                authority_digest,
            ),
        ):
            if supplied is not None and supplied != expected:
                raise ValueError(f"{field_name} does not match exact requested material")
            object.__setattr__(self, field_name, expected)

        requested_effects = set(self.requested_effects)
        if self.action in _LIVE_ACTIONS:
            if ActivationRequestedEffect.PACK_ACTIVATION not in requested_effects:
                raise ValueError("live activation plans require the pack_activation effect")
            if not requested_effects <= _LIVE_EFFECTS:
                raise ValueError("live activation plans contain a lifecycle-only effect")
            if self.requested_capabilities != self.spec.capability_bindings:
                raise ValueError("live activation plans must bind every exact activation capability")
            if self.requested_authorities != self.spec.authority_bindings:
                raise ValueError("live activation plans must bind every exact activation authority")
        elif self.action is ActivationPlanAction.SUSPEND:
            if requested_effects != {ActivationRequestedEffect.ACTIVATION_SUSPENSION}:
                raise ValueError("suspension plans may request only activation_suspension")
            if self.requested_capabilities or self.requested_authorities:
                raise ValueError("suspension plans cannot request runtime capability or authority use")
        else:
            if requested_effects != {ActivationRequestedEffect.ACTIVATION_RETIREMENT}:
                raise ValueError("retirement plans may request only activation_retirement")
            if self.requested_capabilities or self.requested_authorities:
                raise ValueError("retirement plans cannot request runtime capability or authority use")

        if self.action is ActivationPlanAction.INITIAL_ACTIVATION:
            if self.expected_head_revision_id is not None:
                raise ValueError("initial activation cannot name an existing head")
        elif self.expected_head_revision_id is None:
            raise ValueError("non-initial activation plans require the exact expected head")

        target_fields = (
            self.rollback_target_revision_id,
            self.rollback_target_revision_digest,
        )
        if self.action is ActivationPlanAction.ROLLBACK:
            if any(item is None for item in target_fields):
                raise ValueError("rollback plans require an exact target revision and digest")
        elif any(item is not None for item in target_fields):
            raise ValueError("only rollback plans may name a rollback target")

        material = self.model_dump(mode="json", exclude={"plan_id", "plan_digest"})
        digest = canonical_hash(material)
        expected_id = f"intelligence_activation_plan:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.plan_id is not None and self.plan_id != expected_id:
            raise ValueError("activation plan identity does not match exact material")
        if self.plan_digest is not None and self.plan_digest != expected_digest:
            raise ValueError("activation plan digest does not match exact material")
        object.__setattr__(self, "plan_id", expected_id)
        object.__setattr__(self, "plan_digest", expected_digest)
        return self


class DomainActivationRevisionV1Alpha2(FrozenContract):
    """Append-only activation revision whose approval subject is its exact plan."""

    contract: Literal[
        "ace.intelligence.domain-activation-revision/v1alpha2"
    ] = DOMAIN_ACTIVATION_REVISION_V1ALPHA2_VERSION
    activation_id: str | None = None
    revision: StrictInt = Field(ge=1)
    plan: IntelligenceActivationPlanV1Alpha2
    state: ActivationRuntimeState
    prior_revision_id: str | None = None
    actor_ref: str
    approval_disposition: Literal["approved"] = "approved"
    approval_receipt_ref: str
    occurred_at: datetime
    revision_id: str | None = None
    revision_digest: str | None = None

    @field_validator(
        "activation_id",
        "prior_revision_id",
        "actor_ref",
        "approval_receipt_ref",
        "revision_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("revision_digest")
    @classmethod
    def validate_revision_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, name="occurred_at")

    @model_validator(mode="after")
    def validate_and_derive(self) -> Self:
        expected_activation_id = (
            "domain_activation:"
            f"{canonical_hash([self.plan.spec.product_id, self.plan.spec.activation_key])[:32]}"
        )
        if self.activation_id is not None and self.activation_id != expected_activation_id:
            raise ValueError("activation identity does not match the plan product and activation scope")
        if self.revision == 1 and self.prior_revision_id is not None:
            raise ValueError("the first v1alpha2 activation revision cannot have a prior revision")
        if self.revision > 1 and self.prior_revision_id is None:
            raise ValueError("later v1alpha2 activation revisions require a prior revision")
        if self.prior_revision_id != self.plan.expected_head_revision_id:
            raise ValueError("activation revision prior identity must equal the plan expected head")
        if self.occurred_at < self.plan.created_at:
            raise ValueError("activation transition cannot predate its exact plan")

        expected_state = (
            ActivationRuntimeState.SUSPENDED
            if self.plan.action is ActivationPlanAction.SUSPEND
            else ActivationRuntimeState.RETIRED
            if self.plan.action is ActivationPlanAction.RETIRE
            else ActivationRuntimeState.ACTIVE
        )
        if self.state is not expected_state:
            raise ValueError("activation revision state does not match the exact plan action")

        material = self.model_dump(
            mode="json",
            exclude={"activation_id", "revision_id", "revision_digest"},
        )
        digest = canonical_hash(material)
        expected_id = f"activation_revision:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.revision_id is not None and self.revision_id != expected_id:
            raise ValueError("v1alpha2 activation revision identity does not match exact material")
        if self.revision_digest is not None and self.revision_digest != expected_digest:
            raise ValueError("v1alpha2 activation revision digest does not match exact material")
        object.__setattr__(self, "activation_id", expected_activation_id)
        object.__setattr__(self, "revision_id", expected_id)
        object.__setattr__(self, "revision_digest", expected_digest)
        return self


class DomainActivationCommitReferenceV1Alpha2(FrozenContract):
    """Opaque historical coordinates that grant no present runtime authority."""

    contract: Literal[
        "ace.application.domain-activation-commit-reference/v1alpha2"
    ] = DOMAIN_ACTIVATION_COMMIT_REFERENCE_V1ALPHA2_VERSION
    authority_stage: Literal["historical_reference"] = "historical_reference"
    live_authority: Literal[False] = False
    product_id: str
    activation_key: str
    activation_id: str
    state: ActivationRuntimeState
    plan_id: str
    plan_digest: str
    revision: StrictInt = Field(ge=1)
    revision_id: str
    revision_digest: str
    commit_receipt_id: str
    commit_receipt_digest: str
    committed_at: datetime

    @field_validator(
        "product_id",
        "activation_id",
        "plan_id",
        "revision_id",
        "commit_receipt_id",
    )
    @classmethod
    def validate_coordinate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("activation_key")
    @classmethod
    def validate_activation_key(cls, value: str) -> str:
        return validate_slug(value, name="activation_key")

    @field_validator(
        "plan_digest",
        "revision_digest",
        "commit_receipt_digest",
    )
    @classmethod
    def validate_coordinate_digests(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("committed_at")
    @classmethod
    def validate_committed_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, name="committed_at")


__all__ = [
    "DOMAIN_ACTIVATION_COMMIT_REFERENCE_V1ALPHA2_VERSION",
    "DOMAIN_ACTIVATION_REVISION_V1ALPHA2_VERSION",
    "INTELLIGENCE_ACTIVATION_PLAN_V1ALPHA2_VERSION",
    "ActivationPlanAction",
    "ActivationRequestedEffect",
    "ActivationRuntimeState",
    "DomainActivationCommitReferenceV1Alpha2",
    "DomainActivationRevisionV1Alpha2",
    "IntelligenceActivationPlanV1Alpha2",
]
