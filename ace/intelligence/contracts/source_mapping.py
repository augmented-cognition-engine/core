"""Closed declarative source-mapping contracts for the alpha compiler."""

from __future__ import annotations

import math
import re
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, StrictInt, field_validator, model_validator

from ace.core.contracts import FrozenContract
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    validate_product_id,
    validate_reference,
    validate_slug,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    IntelligenceResourceMode,
)

SOURCE_MAPPING_MODULE_VERSION = "ace.intelligence.source-mapping/v1alpha1"
RESOLVED_SUBJECT_BINDING_VERSION = "ace.intelligence.resolved-subject-binding/v1alpha1"
MAX_POINTER_CHARS = 500
MAX_POINTER_SEGMENTS = 64
MAX_MAPPED_STRING_CHARS = 4_096

_URI_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]{0,31}$")
_SOURCE_TYPE_REFERENCE = re.compile(r"^[a-z][a-z0-9]*(?:[._:/-][a-z0-9]+){0,15}$")


class SourceMappingTransform(StrEnum):
    """The complete alpha transform allowlist."""

    COPY = "copy"
    DECIMAL_TEXT_TO_NUMBER = "decimal_text_to_number"


class SourceMappingCharacterSet(StrEnum):
    """The complete alpha character-set constraint allowlist."""

    ASCII_UPPER = "ascii_upper"


def _validate_json_pointer(value: str) -> str:
    if len(value) > MAX_POINTER_CHARS:
        raise ValueError(f"source_pointer exceeds the {MAX_POINTER_CHARS}-character bound")
    if value == "":
        return value
    if not value.startswith("/"):
        raise ValueError("source_pointer must be an RFC 6901 JSON Pointer")
    segments = value.split("/")[1:]
    if len(segments) > MAX_POINTER_SEGMENTS:
        raise ValueError(f"source_pointer exceeds the {MAX_POINTER_SEGMENTS}-segment bound")
    for segment in segments:
        index = 0
        while index < len(segment):
            if segment[index] == "~":
                if index + 1 >= len(segment) or segment[index + 1] not in {"0", "1"}:
                    raise ValueError("source_pointer contains an invalid RFC 6901 escape")
                index += 2
            else:
                index += 1
    return value


class AttributeMappingV1(FrozenContract):
    """Map one captured JSON value into one declared ontology attribute."""

    attribute_id: str
    source_pointer: str
    transform: SourceMappingTransform = SourceMappingTransform.COPY
    min_length: StrictInt | None = Field(default=None, ge=0, le=MAX_MAPPED_STRING_CHARS)
    max_length: StrictInt | None = Field(default=None, ge=0, le=MAX_MAPPED_STRING_CHARS)
    character_set: SourceMappingCharacterSet | None = None

    @field_validator("attribute_id")
    @classmethod
    def validate_attribute_id(cls, value: str) -> str:
        return validate_slug(value, name="attribute_id")

    @field_validator("source_pointer")
    @classmethod
    def validate_source_pointer(cls, value: str) -> str:
        return _validate_json_pointer(value)

    @model_validator(mode="after")
    def validate_string_bounds(self) -> Self:
        if self.min_length is not None and self.max_length is not None and self.min_length > self.max_length:
            raise ValueError("min_length cannot exceed max_length")
        return self


class SourceMappingRuleV1(FrozenContract):
    """One inert source shape mapped to one already-resolved entity subject."""

    mapping_id: str
    source_definition_ref: str
    source_type_ref: str
    capability_requirement_id: str
    authority_request_id: str
    allowed_uri_schemes: tuple[str, ...] = Field(min_length=1, max_length=16)
    subject_binding_id: str
    entity_type_id: str
    attribute_mappings: tuple[AttributeMappingV1, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )
    static_confidence: float

    @field_validator(
        "mapping_id",
        "capability_requirement_id",
        "authority_request_id",
        "subject_binding_id",
        "entity_type_id",
    )
    @classmethod
    def validate_identifiers(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("source_type_ref")
    @classmethod
    def validate_source_type_ref(cls, value: str) -> str:
        if len(value) > 240 or not _SOURCE_TYPE_REFERENCE.fullmatch(value):
            raise ValueError("source_type_ref must be a bounded lowercase type reference")
        return value

    @field_validator("source_definition_ref")
    @classmethod
    def validate_source_definition_ref(cls, value: str) -> str:
        return validate_reference(value, name="source_definition_ref")

    @field_validator("allowed_uri_schemes", mode="before")
    @classmethod
    def normalize_uri_schemes(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("allowed_uri_schemes must be an ordered collection")
        if not value or len(value) > 16 or any(not isinstance(item, str) for item in value):
            raise ValueError("allowed_uri_schemes must contain between 1 and 16 strings")
        if any(not _URI_SCHEME.fullmatch(item) for item in value):
            raise ValueError("allowed_uri_schemes must contain bounded lowercase URI schemes")
        if len(value) != len(set(value)):
            raise ValueError("allowed_uri_schemes must be unique")
        return tuple(sorted(value))

    @field_validator("attribute_mappings", mode="before")
    @classmethod
    def preserve_mapping_collection(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("attribute_mappings must be an ordered collection")
        return value

    @field_validator("attribute_mappings")
    @classmethod
    def canonicalize_attribute_mappings(
        cls,
        value: tuple[AttributeMappingV1, ...],
    ) -> tuple[AttributeMappingV1, ...]:
        identifiers = [item.attribute_id for item in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("attribute_mappings must map each attribute at most once")
        return tuple(sorted(value, key=lambda item: item.attribute_id))

    @field_validator("static_confidence", mode="before")
    @classmethod
    def validate_static_confidence(cls, value: Any) -> float:
        if type(value) is not float or not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("static_confidence must be a finite float between 0.0 and 1.0")
        return 0.0 if value == 0.0 else value


class SourceMappingModuleV1(FrozenContract):
    """One versioned module containing only closed source mapping declarations."""

    contract: Literal["ace.intelligence.source-mapping/v1alpha1"] = SOURCE_MAPPING_MODULE_VERSION
    module_id: str
    mappings: tuple[SourceMappingRuleV1, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("mappings", mode="before")
    @classmethod
    def preserve_mapping_collection(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("mappings must be an ordered collection")
        return value

    @field_validator("mappings")
    @classmethod
    def canonicalize_mappings(
        cls,
        value: tuple[SourceMappingRuleV1, ...],
    ) -> tuple[SourceMappingRuleV1, ...]:
        identifiers = [item.mapping_id for item in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("mappings must use unique mapping IDs")
        return tuple(sorted(value, key=lambda item: item.mapping_id))


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


class ResolvedSubjectBindingV1Alpha1(_StrictFrozenContract):
    """One host-resolved entity identity; mapping performs no entity resolution."""

    contract: Literal["ace.intelligence.resolved-subject-binding/v1alpha1"] = RESOLVED_SUBJECT_BINDING_VERSION
    product_id: str
    mode: Literal[
        IntelligenceResourceMode.PREPARED,
        IntelligenceResourceMode.LIVE,
    ] = IntelligenceResourceMode.PREPARED
    activation_revision: ActivationRevisionReferenceV1Alpha1
    subject_binding_id: str
    entity_type_id: str
    entity_ref: str

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("subject_binding_id", "entity_type_id")
    @classmethod
    def validate_subject_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("entity_ref")
    @classmethod
    def validate_entity_ref(cls, value: str) -> str:
        return validate_reference(value, name="entity_ref")

    @model_validator(mode="after")
    def validate_activation_scope(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("subject binding product_id must match its exact activation revision")
        return self


__all__ = [
    "AttributeMappingV1",
    "RESOLVED_SUBJECT_BINDING_VERSION",
    "ResolvedSubjectBindingV1Alpha1",
    "SOURCE_MAPPING_MODULE_VERSION",
    "SourceMappingCharacterSet",
    "SourceMappingModuleV1",
    "SourceMappingRuleV1",
    "SourceMappingTransform",
]
