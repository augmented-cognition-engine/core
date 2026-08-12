"""Stable structured diagnostics and compatibility negotiation contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, StrictBool, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.common import validate_contract, validate_digest

PACK_COMPILATION_REPORT_VERSION = "ace.intelligence.pack-compilation-report/v1alpha1"
STABLE_PACK_COMPILATION_REPORT_VERSION = "ace.intelligence.pack-compilation-report/v1"
PACK_COMPATIBILITY_RESULT_VERSION = "ace.intelligence.pack-compatibility-result/v1"
STABLE_PACK_COMPILATION_RESULT_VERSION = "ace.intelligence.pack-compilation-result/v1"


class PackCompatibilityStatus(StrEnum):
    SUPPORTED = "supported"
    DEPRECATED = "deprecated"
    MIGRATION_REQUIRED = "migration_required"
    REJECTED = "rejected"


class PackDiagnosticV1(FrozenContract):
    severity: Literal["error", "warning"]
    code: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, max_length=500)
    message: str = Field(min_length=1, max_length=1_000)


class PackCompilationReportV1(FrozenContract):
    contract: Literal[
        "ace.intelligence.pack-compilation-report/v1alpha1",
        "ace.intelligence.pack-compilation-report/v1",
    ] = PACK_COMPILATION_REPORT_VERSION
    success: StrictBool
    diagnostics: tuple[PackDiagnosticV1, ...] = Field(default_factory=tuple, max_length=256)

    @model_validator(mode="after")
    def validate_result(self):
        has_errors = any(item.severity == "error" for item in self.diagnostics)
        if self.success == has_errors:
            raise ValueError("successful reports cannot contain errors and failed reports require one")
        return self


class PackCompatibilityResultV1(FrozenContract):
    """Deterministic negotiation result; package versions are intentionally absent."""

    contract: Literal["ace.intelligence.pack-compatibility-result/v1"] = PACK_COMPATIBILITY_RESULT_VERSION
    manifest_contract: str
    compiler_contract: str
    intelligence_contract: str
    declared_compatibility_digest: str | None = None
    status: PackCompatibilityStatus
    diagnostics: tuple[PackDiagnosticV1, ...] = Field(default_factory=tuple, max_length=16)
    result_id: str | None = None
    result_digest: str | None = None

    @field_validator("manifest_contract", "compiler_contract", "intelligence_contract")
    @classmethod
    def validate_contracts(cls, value: str) -> str:
        return validate_contract(value)

    @field_validator("declared_compatibility_digest", "result_digest")
    @classmethod
    def validate_result_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def validate_and_derive(self) -> Self:
        has_errors = any(item.severity == "error" for item in self.diagnostics)
        if self.status in {PackCompatibilityStatus.SUPPORTED, PackCompatibilityStatus.DEPRECATED}:
            if has_errors:
                raise ValueError("accepted compatibility results cannot contain errors")
        elif not has_errors:
            raise ValueError("refused compatibility results require an error diagnostic")
        material = self.model_dump(mode="json", exclude={"result_id", "result_digest"})
        digest = canonical_hash(material)
        expected_id = f"pack_compatibility:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.result_id is not None and self.result_id != expected_id:
            raise ValueError("compatibility result identity does not match exact material")
        if self.result_digest is not None and self.result_digest != expected_digest:
            raise ValueError("compatibility result digest does not match exact material")
        object.__setattr__(self, "result_id", expected_id)
        object.__setattr__(self, "result_digest", expected_digest)
        return self


class StablePackCompilationResultV1(FrozenContract):
    """Successful stable compilation evidence bound to exact Pack IR and negotiation."""

    contract: Literal["ace.intelligence.pack-compilation-result/v1"] = STABLE_PACK_COMPILATION_RESULT_VERSION
    manifest_contract: str
    compiler_contract: str
    intelligence_contract: str
    compatibility_result_id: str
    compatibility_result_digest: str
    compiled_pack_id: str
    pack_digest: str
    diagnostics: tuple[PackDiagnosticV1, ...] = Field(default_factory=tuple, max_length=16)
    result_id: str | None = None
    result_digest: str | None = None

    @field_validator("manifest_contract", "compiler_contract", "intelligence_contract")
    @classmethod
    def validate_contracts(cls, value: str) -> str:
        return validate_contract(value)

    @field_validator("compatibility_result_id", "compiled_pack_id")
    @classmethod
    def validate_references(cls, value: str) -> str:
        if not value or len(value) > 240:
            raise ValueError("compilation result references must be bounded")
        return value

    @field_validator("compatibility_result_digest", "pack_digest", "result_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def validate_and_derive(self) -> Self:
        if any(item.severity == "error" for item in self.diagnostics):
            raise ValueError("successful compilation results cannot contain errors")
        expected_pack_id = f"pack_ir:{self.pack_digest.removeprefix('sha256:')[:32]}"
        if self.compiled_pack_id != expected_pack_id:
            raise ValueError("compilation result Pack IR identity and digest do not agree")
        material = self.model_dump(mode="json", exclude={"result_id", "result_digest"})
        digest = canonical_hash(material)
        expected_id = f"pack_compilation:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.result_id is not None and self.result_id != expected_id:
            raise ValueError("compilation result identity does not match exact material")
        if self.result_digest is not None and self.result_digest != expected_digest:
            raise ValueError("compilation result digest does not match exact material")
        object.__setattr__(self, "result_id", expected_id)
        object.__setattr__(self, "result_digest", expected_digest)
        return self


__all__ = [
    "PACK_COMPATIBILITY_RESULT_VERSION",
    "PACK_COMPILATION_REPORT_VERSION",
    "STABLE_PACK_COMPILATION_REPORT_VERSION",
    "STABLE_PACK_COMPILATION_RESULT_VERSION",
    "PackCompatibilityResultV1",
    "PackCompatibilityStatus",
    "PackCompilationReportV1",
    "PackDiagnosticV1",
    "StablePackCompilationResultV1",
]
