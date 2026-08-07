"""Declarative monitor definitions over activated domain-pack detection rules."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import (
    normalized_strings,
    validate_product_id,
    validate_reference,
    validate_slug,
)

MONITOR_VERSION = "ace.intelligence.monitor/v1alpha1"
MONITOR_STATE_KIND = "monitor"


class MonitorDisposition(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class MonitorV1Alpha1(FrozenContract):
    """One inert subscription target resolved against an activated pack."""

    contract: Literal["ace.intelligence.monitor/v1alpha1"] = MONITOR_VERSION
    monitor_id: str
    product_id: str
    subject_entity_type_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    detection_rule_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    compiled_pack: CompiledPackRefV1
    activation_revision_ref: str
    disposition: MonitorDisposition = MonitorDisposition.ENABLED
    monitor_ref: str | None = None
    monitor_digest: str | None = None

    @field_validator("monitor_id")
    @classmethod
    def validate_monitor_id(cls, value: str) -> str:
        return validate_slug(value, name="monitor_id")

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("activation_revision_ref", "monitor_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("subject_entity_type_ids", "detection_rule_ids", mode="before")
    @classmethod
    def normalize_slugs(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name=info.field_name) for item in normalized_strings(value, label=info.field_name)
        )

    @field_validator("subject_refs", mode="before")
    @classmethod
    def normalize_subject_refs(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_reference(item, name="subject_ref") for item in normalized_strings(value, label="subject_refs")
        )

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"monitor_ref", "monitor_digest"})
        digest = canonical_hash(material)
        expected_ref = f"monitor:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.monitor_ref is not None and self.monitor_ref != expected_ref:
            raise ValueError("monitor reference does not match exact material")
        if self.monitor_digest is not None and self.monitor_digest != expected_digest:
            raise ValueError("monitor digest does not match exact material")
        object.__setattr__(self, "monitor_ref", expected_ref)
        object.__setattr__(self, "monitor_digest", expected_digest)
        return self


__all__ = [
    "MONITOR_STATE_KIND",
    "MONITOR_VERSION",
    "MonitorDisposition",
    "MonitorV1Alpha1",
]
