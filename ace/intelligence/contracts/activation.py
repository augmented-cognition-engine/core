"""Declarative Overlay and append-only Domain Activation contracts."""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, StrictInt, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.intelligence.contracts.common import (
    MAX_CANONICAL_VALUE_CHARS,
    MAX_DECLARATIONS,
    normalized_strings,
    parse_json_strict,
    sorted_unique,
    validate_contract,
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
    validate_version,
)

ORGANIZATION_OVERLAY_VERSION = "ace.intelligence.organization-overlay/v1alpha1"
COMPILED_OVERLAY_VERSION = "ace.intelligence.compiled-overlay/v1alpha1"
DOMAIN_ACTIVATION_SPEC_VERSION = "ace.intelligence.domain-activation-spec/v1alpha1"
DOMAIN_ACTIVATION_REVISION_VERSION = "ace.intelligence.domain-activation-revision/v1alpha1"


class OverlayValueV1(FrozenContract):
    slot_id: str
    value_json: str = Field(min_length=1, max_length=MAX_CANONICAL_VALUE_CHARS)

    @field_validator("slot_id")
    @classmethod
    def validate_slot_id(cls, value: str) -> str:
        return validate_slug(value, name="slot_id")

    @field_validator("value_json")
    @classmethod
    def normalize_json(cls, value: str) -> str:
        try:
            parsed = parse_json_strict(value)
            normalized = canonical_json(parsed)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("overlay value must be valid finite JSON") from exc
        if len(normalized) > MAX_CANONICAL_VALUE_CHARS:
            raise ValueError("overlay value exceeds the bounded serialized size")
        return normalized

    def parsed_value(self) -> Any:
        return parse_json_strict(self.value_json)


class OrganizationOverlayV1(FrozenContract):
    contract: Literal["ace.intelligence.organization-overlay/v1alpha1"] = ORGANIZATION_OVERLAY_VERSION
    overlay_id: str
    version: str
    pack_id: str
    pack_version: str
    pack_digest: str
    values: tuple[OverlayValueV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)

    @field_validator("overlay_id", "pack_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("version", "pack_version")
    @classmethod
    def validate_versions(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("pack_digest")
    @classmethod
    def validate_pack_digest(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("values")
    @classmethod
    def normalize_values(cls, value: tuple[OverlayValueV1, ...]) -> tuple[OverlayValueV1, ...]:
        return sorted_unique(value, key=lambda item: item.slot_id, label="overlay values")


class CompiledOverlayV1(FrozenContract):
    contract: Literal["ace.intelligence.compiled-overlay/v1alpha1"] = COMPILED_OVERLAY_VERSION
    overlay_id: str
    version: str
    pack_id: str
    pack_version: str
    pack_digest: str
    values: tuple[OverlayValueV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    compiled_overlay_id: str | None = None
    overlay_digest: str | None = None

    @field_validator("overlay_id", "pack_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("version", "pack_version")
    @classmethod
    def validate_versions(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("pack_digest")
    @classmethod
    def validate_pack_digest(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("values")
    @classmethod
    def normalize_values(cls, value: tuple[OverlayValueV1, ...]) -> tuple[OverlayValueV1, ...]:
        return sorted_unique(value, key=lambda item: item.slot_id, label="overlay values")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"compiled_overlay_id", "overlay_digest"})
        digest = canonical_hash(material)
        expected_digest = f"sha256:{digest}"
        expected_id = f"overlay_ir:{digest[:32]}"
        if self.compiled_overlay_id is not None and self.compiled_overlay_id != expected_id:
            raise ValueError("compiled overlay identity does not match exact material")
        if self.overlay_digest is not None and self.overlay_digest != expected_digest:
            raise ValueError("compiled overlay digest does not match exact material")
        object.__setattr__(self, "compiled_overlay_id", expected_id)
        object.__setattr__(self, "overlay_digest", expected_digest)
        return self


class CapabilityBindingV1(FrozenContract):
    requirement_id: str
    capability: str
    contract: str
    implementation_id: str
    implementation_version: str
    artifact_digest: str
    configuration_ref: str | None = None
    secret_ref: str | None = None

    @field_validator("requirement_id", "capability", "implementation_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("implementation_version")
    @classmethod
    def validate_implementation_version(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("contract")
    @classmethod
    def validate_binding_contract(cls, value: str) -> str:
        return validate_contract(value)

    @field_validator("artifact_digest")
    @classmethod
    def validate_artifact_digest(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("configuration_ref", "secret_ref")
    @classmethod
    def validate_optional_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None


class AuthorityBindingV1(FrozenContract):
    request_id: str
    authority: str
    grant_ref: str

    @field_validator("request_id", "authority")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("grant_ref")
    @classmethod
    def validate_grant_ref(cls, value: str) -> str:
        return validate_reference(value, name="grant_ref")


class CompiledPackRefV1(FrozenContract):
    pack_id: str
    pack_version: str
    compiled_pack_id: str
    pack_digest: str

    @field_validator("pack_id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        return validate_slug(value, name="pack_id")

    @field_validator("pack_version")
    @classmethod
    def validate_pack_version(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("compiled_pack_id")
    @classmethod
    def validate_compiled_pack_id(cls, value: str) -> str:
        return validate_reference(value, name="compiled_pack_id")

    @field_validator("pack_digest")
    @classmethod
    def validate_pack_digest(cls, value: str) -> str:
        return validate_digest(value)

    @model_validator(mode="after")
    def validate_identity_pair(self) -> Self:
        expected_id = f"pack_ir:{self.pack_digest.removeprefix('sha256:')[:32]}"
        if self.compiled_pack_id != expected_id:
            raise ValueError("compiled pack reference ID and digest do not agree")
        return self


class DomainActivationSpecV1(FrozenContract):
    contract: Literal["ace.intelligence.domain-activation-spec/v1alpha1"] = DOMAIN_ACTIVATION_SPEC_VERSION
    product_id: str = Field(min_length=1, max_length=240)
    activation_key: str
    pack: CompiledPackRefV1
    overlay: CompiledOverlayV1
    compilation_receipt_ref: str = Field(min_length=1, max_length=240)
    capability_bindings: tuple[CapabilityBindingV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    authority_bindings: tuple[AuthorityBindingV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    conformance_receipt_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    spec_id: str | None = None
    spec_hash: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("activation_key")
    @classmethod
    def validate_activation_key(cls, value: str) -> str:
        return validate_slug(value, name="activation_key")

    @field_validator("compilation_receipt_ref")
    @classmethod
    def validate_compilation_receipt(cls, value: str) -> str:
        return validate_reference(value, name="compilation_receipt_ref")

    @field_validator("capability_bindings")
    @classmethod
    def normalize_capability_bindings(cls, value: tuple[CapabilityBindingV1, ...]) -> tuple[CapabilityBindingV1, ...]:
        return sorted_unique(value, key=lambda item: item.requirement_id, label="capability bindings")

    @field_validator("authority_bindings")
    @classmethod
    def normalize_authority_bindings(cls, value: tuple[AuthorityBindingV1, ...]) -> tuple[AuthorityBindingV1, ...]:
        return sorted_unique(value, key=lambda item: item.request_id, label="authority bindings")

    @field_validator("conformance_receipt_refs", mode="before")
    @classmethod
    def normalize_conformance_refs(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_reference(item, name="conformance receipt")
            for item in normalized_strings(value, label="conformance receipt references")
        )

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.overlay.pack_id != self.pack.pack_id or self.overlay.pack_version != self.pack.pack_version:
            raise ValueError("overlay must target the exact compiled pack identity and version")
        if self.overlay.pack_digest != self.pack.pack_digest:
            raise ValueError("overlay must target the exact compiled pack digest")
        material = self.model_dump(mode="json", exclude={"spec_id", "spec_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"activation_spec:{expected_hash[:32]}"
        if self.spec_id is not None and self.spec_id != expected_id:
            raise ValueError("activation specification identity does not match exact material")
        if self.spec_hash is not None and self.spec_hash != expected_hash:
            raise ValueError("activation specification hash does not match exact material")
        object.__setattr__(self, "spec_id", expected_id)
        object.__setattr__(self, "spec_hash", expected_hash)
        return self


class ActivationState(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class DomainActivationRevisionV1(FrozenContract):
    contract: Literal["ace.intelligence.domain-activation-revision/v1alpha1"] = DOMAIN_ACTIVATION_REVISION_VERSION
    activation_id: str | None = None
    revision: StrictInt = Field(ge=1)
    spec: DomainActivationSpecV1
    state: ActivationState
    prior_revision_id: str | None = None
    rollback_of_revision_id: str | None = None
    actor_ref: str = Field(min_length=1, max_length=240)
    approval_receipt_ref: str = Field(min_length=1, max_length=240)
    occurred_at: datetime
    revision_id: str | None = None
    revision_hash: str | None = None

    @field_validator(
        "activation_id",
        "prior_revision_id",
        "rollback_of_revision_id",
        "actor_ref",
        "approval_receipt_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_and_derive(self) -> Self:
        expected_activation_id = (
            f"domain_activation:{canonical_hash([self.spec.product_id, self.spec.activation_key])[:32]}"
        )
        if self.activation_id is not None and self.activation_id != expected_activation_id:
            raise ValueError("activation identity does not match product scope and activation key")
        if self.revision == 1 and self.prior_revision_id is not None:
            raise ValueError("the first activation revision cannot have a prior revision")
        if self.revision > 1 and self.prior_revision_id is None:
            raise ValueError("later activation revisions require a prior revision")
        if self.revision == 1 and self.rollback_of_revision_id is not None:
            raise ValueError("the first activation revision cannot be a rollback")
        if self.rollback_of_revision_id is not None and self.state is not ActivationState.ACTIVE:
            raise ValueError("rollback creates a new active revision")
        material = self.model_dump(
            mode="json",
            exclude={"activation_id", "revision_id", "revision_hash"},
        )
        expected_hash = canonical_hash(material)
        expected_revision_id = f"activation_revision:{expected_hash[:32]}"
        if self.revision_id is not None and self.revision_id != expected_revision_id:
            raise ValueError("activation revision identity does not match exact material")
        if self.revision_hash is not None and self.revision_hash != expected_hash:
            raise ValueError("activation revision hash does not match exact material")
        object.__setattr__(self, "activation_id", expected_activation_id)
        object.__setattr__(self, "revision_id", expected_revision_id)
        object.__setattr__(self, "revision_hash", expected_hash)
        return self


def overlay_value_matches_kind(value: Any, kind: str) -> bool:
    """Validate an already parsed overlay value without coercion."""

    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "string_list":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return kind == "json"
