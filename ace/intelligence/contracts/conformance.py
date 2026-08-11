"""Stable, provider-free Domain Pack golden-fixture and receipt contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import Field, StrictBool, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.intelligence.contracts.activation import OverlayValueV1
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    normalized_strings,
    parse_json_strict,
    sorted_unique,
    validate_contract,
    validate_digest,
    validate_reference,
    validate_slug,
    validate_version,
)
from ace.intelligence.contracts.diagnostics import PackCompatibilityStatus, PackDiagnosticV1

DOMAIN_PACK_GOLDEN_FIXTURE_VERSION = "ace.intelligence.domain-pack-golden-fixture/v1"
DOMAIN_PACK_CONFORMANCE_RECEIPT_VERSION = "ace.intelligence.domain-pack-conformance-receipt/v1"


class GoldenDetectorOutcomeV1(FrozenContract):
    detector_id: str
    entity_ref: str
    material: StrictBool
    shift_type: str | None = None
    signal_type: str | None = None
    routing_rule_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    persona_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    template_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)

    @field_validator("detector_id", "shift_type", "signal_type")
    @classmethod
    def validate_ids(cls, value: str | None, info) -> str | None:
        return validate_slug(value, name=info.field_name) if value is not None else None

    @field_validator("entity_ref")
    @classmethod
    def validate_entity_ref(cls, value: str) -> str:
        return validate_reference(value, name="entity_ref")

    @field_validator("routing_rule_ids", "persona_ids", "template_ids", mode="before")
    @classmethod
    def normalize_ids(cls, value: Any, info) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name=info.field_name)
            for item in normalized_strings(value, label=info.field_name)
        )

    @model_validator(mode="after")
    def validate_material_outcome(self) -> Self:
        if self.material and (self.shift_type is None or self.signal_type is None):
            raise ValueError("material outcomes require shift_type and signal_type")
        if not self.material and any(
            value for value in (self.shift_type, self.signal_type, self.routing_rule_ids, self.persona_ids, self.template_ids)
        ):
            raise ValueError("non-material outcomes cannot claim Shift, Signal, route, persona, or template selection")
        return self


class GoldenObservationTransitionV1(FrozenContract):
    case_id: str
    entity_type_id: str
    entity_ref: str
    baseline_attributes_json: str = Field(min_length=2, max_length=32_000)
    current_attributes_json: str = Field(min_length=2, max_length=32_000)
    baseline_as_of: datetime
    current_as_of: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    expected: tuple[GoldenDetectorOutcomeV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)

    @field_validator("case_id", "entity_type_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("entity_ref")
    @classmethod
    def validate_entity_ref(cls, value: str) -> str:
        return validate_reference(value, name="entity_ref")

    @field_validator("baseline_attributes_json", "current_attributes_json")
    @classmethod
    def normalize_attributes(cls, value: str) -> str:
        parsed = parse_json_strict(value)
        if not isinstance(parsed, dict):
            raise ValueError("golden Observation attributes must be a JSON object")
        return canonical_json(parsed)

    @field_validator("baseline_as_of", "current_as_of")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{info.field_name} must include a timezone")
        return value

    @field_validator("expected")
    @classmethod
    def normalize_expected(cls, value: tuple[GoldenDetectorOutcomeV1, ...]) -> tuple[GoldenDetectorOutcomeV1, ...]:
        return sorted_unique(value, key=lambda item: item.detector_id, label="golden detector outcomes")

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.baseline_as_of >= self.current_as_of:
            raise ValueError("golden Observation baseline must precede current state")
        return self


class DomainPackGoldenFixtureV1(FrozenContract):
    contract: Literal["ace.intelligence.domain-pack-golden-fixture/v1"] = DOMAIN_PACK_GOLDEN_FIXTURE_VERSION
    fixture_id: str
    fixture_version: str
    overlay_values: tuple[OverlayValueV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    observations: tuple[GoldenObservationTransitionV1, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)

    @field_validator("fixture_id")
    @classmethod
    def validate_fixture_id(cls, value: str) -> str:
        return validate_slug(value, name="fixture_id")

    @field_validator("fixture_version")
    @classmethod
    def validate_fixture_version(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("overlay_values")
    @classmethod
    def normalize_overlay_values(cls, value: tuple[OverlayValueV1, ...]) -> tuple[OverlayValueV1, ...]:
        return sorted_unique(value, key=lambda item: item.slot_id, label="fixture overlay values")

    @field_validator("observations")
    @classmethod
    def normalize_observations(
        cls, value: tuple[GoldenObservationTransitionV1, ...]
    ) -> tuple[GoldenObservationTransitionV1, ...]:
        return sorted_unique(value, key=lambda item: item.case_id, label="golden Observation cases")


class DomainPackConformanceReceiptV1(FrozenContract):
    contract: Literal[
        "ace.intelligence.domain-pack-conformance-receipt/v1"
    ] = DOMAIN_PACK_CONFORMANCE_RECEIPT_VERSION
    pack_id: str
    pack_version: str
    compiled_pack_id: str
    pack_digest: str
    manifest_contract: str
    compiler_contract: str
    intelligence_contract: str
    compatibility_status: PackCompatibilityStatus
    compilation_result_id: str
    compilation_result_digest: str
    fixture_id: str
    fixture_version: str
    fixture_digest: str
    expected_digest: str
    actual_digest: str
    passed: StrictBool
    diagnostics: tuple[PackDiagnosticV1, ...] = Field(default_factory=tuple, max_length=256)
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("pack_id", "fixture_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("pack_version", "fixture_version")
    @classmethod
    def validate_versions(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("compiled_pack_id", "compilation_result_id")
    @classmethod
    def validate_compiled_pack_id(cls, value: str) -> str:
        return validate_reference(value, name="compiled_pack_id")

    @field_validator("manifest_contract", "compiler_contract", "intelligence_contract")
    @classmethod
    def validate_contracts(cls, value: str) -> str:
        return validate_contract(value)

    @field_validator(
        "pack_digest",
        "compilation_result_digest",
        "fixture_digest",
        "expected_digest",
        "actual_digest",
        "receipt_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def validate_and_derive(self) -> Self:
        has_errors = any(item.severity == "error" for item in self.diagnostics)
        if self.passed and (has_errors or self.expected_digest != self.actual_digest):
            raise ValueError("passing conformance requires identical expected and actual results without errors")
        if not self.passed and not has_errors:
            raise ValueError("failed conformance requires an error diagnostic")
        expected_pack_id = f"pack_ir:{self.pack_digest.removeprefix('sha256:')[:32]}"
        if self.compiled_pack_id != expected_pack_id:
            raise ValueError("conformance receipt Pack IR identity and digest do not agree")
        expected_compilation_id = (
            f"pack_compilation:{self.compilation_result_digest.removeprefix('sha256:')[:32]}"
        )
        if self.compilation_result_id != expected_compilation_id:
            raise ValueError("conformance receipt compilation result identity and digest do not agree")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_digest"})
        digest = canonical_hash(material)
        expected_id = f"pack_conformance:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("conformance receipt identity does not match exact material")
        if self.receipt_digest is not None and self.receipt_digest != expected_digest:
            raise ValueError("conformance receipt digest does not match exact material")
        object.__setattr__(self, "receipt_id", expected_id)
        object.__setattr__(self, "receipt_digest", expected_digest)
        return self


__all__ = [
    "DOMAIN_PACK_CONFORMANCE_RECEIPT_VERSION",
    "DOMAIN_PACK_GOLDEN_FIXTURE_VERSION",
    "DomainPackConformanceReceiptV1",
    "DomainPackGoldenFixtureV1",
    "GoldenDetectorOutcomeV1",
    "GoldenObservationTransitionV1",
]
