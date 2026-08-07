"""Principal-to-persona bindings and Intelligence-owned subscriptions."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, StrictFloat, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import (
    normalized_strings,
    validate_product_id,
    validate_reference,
    validate_slug,
)

PERSONA_BINDING_VERSION = "ace.intelligence.persona-binding/v1alpha1"
SUBSCRIPTION_VERSION = "ace.intelligence.subscription/v1alpha1"
PERSONA_BINDING_STATE_KIND = "persona_binding"
SUBSCRIPTION_STATE_KIND = "subscription"


class SubscriptionDeliveryDisposition(StrEnum):
    IMMEDIATE = "immediate"
    DIGEST = "digest"
    RECORD_ONLY = "record_only"


class PersonaBindingV1Alpha1(FrozenContract):
    """Intelligence-owned join between a Core principal and a pack persona."""

    contract: Literal["ace.intelligence.persona-binding/v1alpha1"] = PERSONA_BINDING_VERSION
    product_id: str
    principal_ref: str
    persona_id: str
    compiled_pack: CompiledPackRefV1
    activation_revision_ref: str
    binding_ref: str | None = None
    binding_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("principal_ref", "activation_revision_ref", "binding_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("persona_id")
    @classmethod
    def validate_persona_id(cls, value: str) -> str:
        return validate_slug(value, name="persona_id")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"binding_ref", "binding_digest"})
        digest = canonical_hash(material)
        expected_ref = f"persona_binding:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.binding_ref is not None and self.binding_ref != expected_ref:
            raise ValueError("persona binding reference does not match exact material")
        if self.binding_digest is not None and self.binding_digest != expected_digest:
            raise ValueError("persona binding digest does not match exact material")
        object.__setattr__(self, "binding_ref", expected_ref)
        object.__setattr__(self, "binding_digest", expected_digest)
        return self


class SubscriptionV1Alpha1(FrozenContract):
    """Declarative Intelligence delivery preference for one persona binding."""

    contract: Literal["ace.intelligence.subscription/v1alpha1"] = SUBSCRIPTION_VERSION
    subscription_id: str
    product_id: str
    persona_binding_ref: str
    monitor_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    signal_types: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    brief_template_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    minimum_confidence: StrictFloat = Field(ge=0.0, le=1.0)
    delivery: SubscriptionDeliveryDisposition
    subscription_ref: str | None = None
    subscription_digest: str | None = None

    @field_validator("subscription_id")
    @classmethod
    def validate_subscription_id(cls, value: str) -> str:
        return validate_slug(value, name="subscription_id")

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("persona_binding_ref", "subscription_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("monitor_refs", mode="before")
    @classmethod
    def normalize_monitor_refs(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_reference(item, name="monitor_ref") for item in normalized_strings(value, label="monitor_refs")
        )

    @field_validator("signal_types", "brief_template_ids", mode="before")
    @classmethod
    def normalize_selectors(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name=info.field_name) for item in normalized_strings(value, label=info.field_name)
        )

    @field_validator("minimum_confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float:
        if type(value) is not float or not math.isfinite(value):
            raise ValueError("minimum_confidence must be a finite float without coercion")
        return value

    @model_validator(mode="after")
    def validate_selector_and_derive_identity(self) -> Self:
        if not (self.monitor_refs or self.signal_types or self.brief_template_ids):
            raise ValueError("subscription requires at least one monitor, signal, or brief selector")
        material = self.model_dump(
            mode="json",
            exclude={"subscription_ref", "subscription_digest"},
        )
        digest = canonical_hash(material)
        expected_ref = f"subscription:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.subscription_ref is not None and self.subscription_ref != expected_ref:
            raise ValueError("subscription reference does not match exact material")
        if self.subscription_digest is not None and self.subscription_digest != expected_digest:
            raise ValueError("subscription digest does not match exact material")
        object.__setattr__(self, "subscription_ref", expected_ref)
        object.__setattr__(self, "subscription_digest", expected_digest)
        return self


__all__ = [
    "PERSONA_BINDING_STATE_KIND",
    "PERSONA_BINDING_VERSION",
    "SUBSCRIPTION_STATE_KIND",
    "SUBSCRIPTION_VERSION",
    "PersonaBindingV1Alpha1",
    "SubscriptionDeliveryDisposition",
    "SubscriptionV1Alpha1",
]
