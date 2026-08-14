"""Activation-neutral identities for explicitly reviewed recorded sources.

A reviewed selection binds the exact source bytes (through their digest),
metadata, semantic subject, product, and compiled Pack before activation.  It
deliberately does not contain an activation revision.  Recorded-source
admission later combines this identity with the separately approved, current
activation-bound material and refuses either half on mismatch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import (
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
)

RECORDED_SOURCE_SELECTION_VERSION = "ace.application.recorded-source-selection/v1alpha1"
RECORDED_SOURCE_SELECTION_REFERENCE_VERSION = "ace.application.recorded-source-selection-reference/v1alpha1"


class _SelectionContract(FrozenContract):
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


class RecordedSourceSelectionReferenceV1Alpha1(_SelectionContract):
    """Compact exact identity copied from a reviewed plan into ``/start``."""

    contract: Literal["ace.application.recorded-source-selection-reference/v1alpha1"] = (
        RECORDED_SOURCE_SELECTION_REFERENCE_VERSION
    )
    source_group_id: str
    selection_id: str
    selection_digest: str

    @field_validator("source_group_id")
    @classmethod
    def validate_group(cls, value: str) -> str:
        return validate_slug(value, name="source_group_id")

    @field_validator("selection_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_reference(value, name="selection_id")

    @field_validator("selection_digest")
    @classmethod
    def validate_exact_digest(cls, value: str) -> str:
        return validate_digest(value)


class RecordedSourceSelectionV1Alpha1(_SelectionContract):
    """Exact reviewed source and semantic subject, independent of activation."""

    contract: Literal["ace.application.recorded-source-selection/v1alpha1"] = RECORDED_SOURCE_SELECTION_VERSION
    product_id: str
    pack: CompiledPackRefV1
    source_group_id: str
    mapping_id: str
    subject_binding_id: str
    entity_type_id: str
    entity_ref: str
    source_definition_ref: str
    source_type_ref: str
    source_uri: str = Field(min_length=3, max_length=2_048)
    captured_payload_digest: str
    source_published_at: datetime | None = None
    event_effective_at: datetime | None = None
    observed_at: datetime
    locator: str | None = Field(default=None, min_length=1, max_length=1_000)
    selection_id: str | None = None
    selection_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("source_group_id", "mapping_id", "subject_binding_id", "entity_type_id")
    @classmethod
    def validate_slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("entity_ref", "source_definition_ref", "source_type_ref", "selection_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("captured_payload_digest", "selection_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("source_published_at", "event_effective_at", "observed_at")
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.source_published_at is not None and self.source_published_at > self.observed_at:
            raise ValueError("source_published_at cannot follow observed_at")
        if self.event_effective_at is not None and self.event_effective_at > self.observed_at:
            raise ValueError("event_effective_at cannot follow observed_at")
        material = self.model_dump(mode="json", exclude={"selection_id", "selection_digest"})
        digest = canonical_hash(material)
        expected_id = f"recorded_source_selection:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.selection_id not in {None, expected_id}:
            raise ValueError("selection_id does not match exact reviewed source material")
        if self.selection_digest not in {None, expected_digest}:
            raise ValueError("selection_digest does not match exact reviewed source material")
        object.__setattr__(self, "selection_id", expected_id)
        object.__setattr__(self, "selection_digest", expected_digest)
        return self

    def reference(self) -> RecordedSourceSelectionReferenceV1Alpha1:
        return RecordedSourceSelectionReferenceV1Alpha1(
            source_group_id=self.source_group_id,
            selection_id=str(self.selection_id),
            selection_digest=str(self.selection_digest),
        )


__all__ = [
    "RECORDED_SOURCE_SELECTION_REFERENCE_VERSION",
    "RECORDED_SOURCE_SELECTION_VERSION",
    "RecordedSourceSelectionReferenceV1Alpha1",
    "RecordedSourceSelectionV1Alpha1",
]
