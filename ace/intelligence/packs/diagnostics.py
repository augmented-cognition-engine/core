"""Structured, path-specific Domain Pack compilation diagnostics."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, model_validator

from ace.core.contracts import FrozenContract

PACK_COMPILATION_REPORT_VERSION = "ace.intelligence.pack-compilation-report/v1alpha1"


class PackDiagnosticV1(FrozenContract):
    severity: Literal["error", "warning"]
    code: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, max_length=500)
    message: str = Field(min_length=1, max_length=1_000)


class PackCompilationReportV1(FrozenContract):
    contract: Literal["ace.intelligence.pack-compilation-report/v1alpha1"] = PACK_COMPILATION_REPORT_VERSION
    success: StrictBool
    diagnostics: tuple[PackDiagnosticV1, ...] = Field(default_factory=tuple, max_length=256)

    @model_validator(mode="after")
    def validate_result(self):
        has_errors = any(item.severity == "error" for item in self.diagnostics)
        if self.success == has_errors:
            raise ValueError("successful reports cannot contain errors and failed reports require one")
        return self
