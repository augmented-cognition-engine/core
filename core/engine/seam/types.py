"""Shared types for the seam analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FieldShape:
    """A field in an API response or frontend type."""

    name: str
    type_hint: str | None = None
    source: str = "inferred"  # return_literal | response_model | interface | inline_type


@dataclass
class SeamContract:
    """Backend: what an endpoint returns."""

    route: str
    method: str
    source_file: str
    source_line: int = 0
    response_fields: list[FieldShape] = field(default_factory=list)


@dataclass
class SeamExpectation:
    """Frontend: what a consumer expects."""

    route: str
    method: str
    consumer_file: str
    consumer_line: int = 0
    type_name: str = ""
    expected_fields: list[FieldShape] = field(default_factory=list)


@dataclass
class SeamGap:
    """A mismatch between backend contract and frontend expectation."""

    route: str
    severity: str  # error | warning | info
    gap_type: str  # missing_field | extra_field | unmatched_route
    backend_file: str = ""
    frontend_file: str = ""
    detail: str = ""
