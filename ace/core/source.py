"""Canonical, host-provided source values owned by the ACE Core boundary.

The captured payload is inert evidence.  Labels or fields inside it never grant
authority, prove acquisition, select a product, or override this envelope.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, Self
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1

CANONICAL_SOURCE_SNAPSHOT_VERSION = "ace.core.canonical-source-snapshot/v1alpha1"
RESOLVED_SOURCE_DEFINITION_VERSION = "ace.core.resolved-source-definition/v1alpha1"
SOURCE_DEFINITION_STATE_KIND = "source_definition"
MAX_CAPTURED_PAYLOAD_CHARS = 1_000_000

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_TYPE_REFERENCE = re.compile(r"^[a-z][a-z0-9]*(?:[._:/-][a-z0-9]+){0,15}$")
_URI_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]{0,31}$")
_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


class SourceAcquisitionMode(StrEnum):
    """Host-asserted acquisition class; only a later live boundary may admit LIVE."""

    LIVE = "live"
    RECORDED_REPLAY = "recorded_replay"
    PREPARED_FIXTURE = "prepared_fixture"


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _reject_noninteger_number(value: str) -> None:
    display = value if len(value) <= 80 else f"{value[:77]}..."
    raise ValueError(
        f"non-integer JSON numeric tokens are not allowed in alpha source snapshots: {display}; "
        "capture exact decimal text and use decimal_text_to_number"
    )


def _reject_surrogates(value: Any) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                raise ValueError("JSON strings must contain Unicode scalar values")
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)


def _parse_captured_payload(value: str) -> Any:
    parsed = json.loads(
        value,
        object_pairs_hook=_unique_object,
        parse_float=_reject_noninteger_number,
        parse_constant=_reject_nonfinite,
    )
    _reject_surrogates(parsed)
    return parsed


def _validate_reference(value: str, *, name: str) -> str:
    if not _REFERENCE.fullmatch(value):
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def _validate_digest(value: str, *, name: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    return value


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def validate_public_ip_literal(value: str, *, name: str = "ip_address") -> str:
    """Return one canonical globally routable unicast IP literal or fail closed."""

    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be one exact IP literal") from exc
    if not address.is_global or address.is_multicast or address.is_unspecified:
        raise ValueError(f"{name} must be a globally routable unicast address")
    return address.compressed


def validate_exact_https_uri(value: str, *, name: str = "authorized_uri") -> str:
    """Validate the closed P1C2 HTTPS URI policy without normalizing bytes."""

    if len(value) > 2_048:
        raise ValueError(f"{name} exceeds the URI length bound")
    if any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F or 0xD800 <= ord(character) <= 0xDFFF
        for character in value
    ):
        raise ValueError(f"{name} cannot contain whitespace, controls, DEL, or lone surrogates")
    for index, character in enumerate(value):
        if character == "%" and (
            index + 2 >= len(value) or value[index + 1] not in _HEX_DIGITS or value[index + 2] not in _HEX_DIGITS
        ):
            raise ValueError(f"{name} contains a malformed percent escape")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{name} must be one valid absolute HTTPS URI") from exc
    del port
    if parsed.scheme != "https" or value[:5] != "https":
        raise ValueError(f"{name} must use exact lowercase HTTPS")
    if not parsed.netloc or parsed.hostname is None:
        raise ValueError(f"{name} requires an authority and host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{name} cannot contain URI userinfo or credentials")
    if parsed.fragment:
        raise ValueError(f"{name} cannot contain a fragment")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise ValueError(f"{name} cannot target a local hostname")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if hostname and all(character in "0123456789." for character in hostname):
            raise ValueError(f"{name} contains a non-canonical IP literal") from None
    else:
        validate_public_ip_literal(address.compressed, name=name)
    return value


class ResolvedSourceDefinitionV1Alpha1(_StrictFrozenContract):
    """One current product-scoped source definition resolved by the host."""

    contract: Literal["ace.core.resolved-source-definition/v1alpha1"] = RESOLVED_SOURCE_DEFINITION_VERSION
    product_id: str
    source_definition_ref: str
    source_type_ref: str
    configuration_ref: str
    configuration_digest: str
    authorized_uri: str = Field(min_length=9, max_length=2_048)
    subject_binding_id: str
    entity_type_id: str
    entity_ref: str
    state_head_precondition: GovernedStateHeadPreconditionV1Alpha1

    @field_validator(
        "product_id",
        "source_definition_ref",
        "configuration_ref",
        "entity_ref",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _validate_reference(value, name=info.field_name)

    @field_validator("configuration_digest")
    @classmethod
    def validate_configuration_digest(cls, value: str) -> str:
        return _validate_digest(value, name="configuration_digest")

    @field_validator("source_type_ref")
    @classmethod
    def validate_source_type_ref(cls, value: str) -> str:
        if len(value) > 240 or not _TYPE_REFERENCE.fullmatch(value):
            raise ValueError("source_type_ref must be a bounded lowercase type reference")
        return value

    @field_validator("subject_binding_id", "entity_type_id")
    @classmethod
    def validate_identifiers(cls, value: str, info) -> str:
        if len(value) > 120 or not re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", value):
            raise ValueError(f"{info.field_name} must be a bounded lowercase identifier")
        return value

    @field_validator("authorized_uri")
    @classmethod
    def validate_authorized_uri(cls, value: str) -> str:
        return validate_exact_https_uri(value)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if (
            self.state_head_precondition.product_id != self.product_id
            or self.state_head_precondition.state_kind != SOURCE_DEFINITION_STATE_KIND
            or self.state_head_precondition.state_id != self.source_definition_ref
        ):
            raise ValueError("source definition requires its exact named governed-state head")
        return self


class SourceDefinitionResolver(Protocol):
    """Port to a current Core-governed source-definition source of truth."""

    async def resolve_source_definition(
        self,
        *,
        product_id: str,
        source_definition_ref: str,
        resolved_at: datetime,
    ) -> ResolvedSourceDefinitionV1Alpha1: ...


class CanonicalSourceSnapshotV1Alpha1(_StrictFrozenContract):
    """One immutable source capture supplied by a host without implied authority."""

    contract: Literal["ace.core.canonical-source-snapshot/v1alpha1"] = CANONICAL_SOURCE_SNAPSHOT_VERSION
    source_definition_ref: str
    source_snapshot_ref: str | None = None
    source_snapshot_digest: str | None = None
    source_type_ref: str
    source_uri: str = Field(min_length=3, max_length=2_048)
    captured_payload_json: str = Field(min_length=1, max_length=MAX_CAPTURED_PAYLOAD_CHARS)
    captured_payload_digest: str
    source_published_at: datetime | None = None
    event_effective_at: datetime | None = None
    observed_at: datetime
    ingested_at: datetime
    locator: str | None = Field(default=None, min_length=1, max_length=1_000)
    acquisition_mode: SourceAcquisitionMode
    acquisition_receipt_ref: str
    acquisition_receipt_digest: str

    @field_validator(
        "source_definition_ref",
        "source_snapshot_ref",
        "acquisition_receipt_ref",
    )
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return _validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("source_snapshot_digest", "captured_payload_digest", "acquisition_receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _validate_digest(value, name=info.field_name) if value is not None else None

    @field_validator("source_type_ref")
    @classmethod
    def validate_source_type_ref(cls, value: str) -> str:
        if len(value) > 240 or not _TYPE_REFERENCE.fullmatch(value):
            raise ValueError("source_type_ref must be a bounded lowercase type reference")
        return value

    @field_validator("source_uri")
    @classmethod
    def validate_source_uri(cls, value: str) -> str:
        if any(
            character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F or 0xD800 <= ord(character) <= 0xDFFF
            for character in value
        ):
            raise ValueError("source_uri cannot contain whitespace, ASCII controls, DEL, or lone surrogates")
        for index, character in enumerate(value):
            if character == "%" and (
                index + 2 >= len(value) or value[index + 1] not in _HEX_DIGITS or value[index + 2] not in _HEX_DIGITS
            ):
                raise ValueError("source_uri contains a malformed percent escape")
        try:
            scheme = urlsplit(value).scheme
        except ValueError as exc:
            raise ValueError("source_uri must be a valid absolute URI") from exc
        if not _URI_SCHEME.fullmatch(scheme) or value[: len(scheme)] != scheme:
            raise ValueError("source_uri must use a bounded lowercase absolute URI scheme")
        return value

    @field_validator("locator")
    @classmethod
    def validate_locator(cls, value: str | None) -> str | None:
        if value is not None and any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("locator must contain Unicode scalar values")
        return value

    @field_validator("captured_payload_json")
    @classmethod
    def canonicalize_payload(cls, value: str) -> str:
        try:
            parsed = _parse_captured_payload(value)
        except ValueError as exc:
            message = str(exc)
            if len(message) > 300:
                message = f"{message[:297]}..."
            raise ValueError(message) from exc
        except (UnicodeError, RecursionError) as exc:
            raise ValueError("captured payload could not be parsed within contract bounds") from exc
        try:
            normalized = canonical_json(parsed)
            normalized.encode("utf-8")
        except (TypeError, UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError("captured payload could not be canonicalized within contract bounds") from exc
        if len(normalized) > MAX_CAPTURED_PAYLOAD_CHARS:
            raise ValueError("captured payload exceeds the canonical size bound")
        return normalized

    @field_validator(
        "source_published_at",
        "event_effective_at",
        "observed_at",
        "ingested_at",
    )
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware_utc(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_exact_material(self) -> Self:
        payload_digest = f"sha256:{hashlib.sha256(self.captured_payload_json.encode('utf-8')).hexdigest()}"
        if self.captured_payload_digest != payload_digest:
            raise ValueError("captured_payload_digest does not match the canonical captured payload")
        if self.observed_at > self.ingested_at:
            raise ValueError("ingested_at cannot precede observed_at")
        if self.source_published_at is not None and self.source_published_at > self.observed_at:
            raise ValueError("source_published_at cannot follow observed_at")

        material = self.model_dump(
            mode="json",
            exclude={"source_snapshot_ref", "source_snapshot_digest"},
        )
        snapshot_hash = canonical_hash(material)
        expected_ref = f"source_snapshot:{snapshot_hash[:32]}"
        expected_digest = f"sha256:{snapshot_hash}"
        if self.source_snapshot_ref is not None and self.source_snapshot_ref != expected_ref:
            raise ValueError("source_snapshot_ref does not match exact snapshot material")
        if self.source_snapshot_digest is not None and self.source_snapshot_digest != expected_digest:
            raise ValueError("source_snapshot_digest does not match exact snapshot material")
        object.__setattr__(self, "source_snapshot_ref", expected_ref)
        object.__setattr__(self, "source_snapshot_digest", expected_digest)
        return self

    @property
    def as_of(self) -> datetime:
        """Alpha source availability and as-of are both the host's ingestion time."""

        return self.ingested_at

    def captured_payload(self) -> Any:
        """Return a fresh inert payload value that cannot mutate this snapshot."""

        return _parse_captured_payload(self.captured_payload_json)


__all__ = [
    "CANONICAL_SOURCE_SNAPSHOT_VERSION",
    "CanonicalSourceSnapshotV1Alpha1",
    "RESOLVED_SOURCE_DEFINITION_VERSION",
    "SOURCE_DEFINITION_STATE_KIND",
    "ResolvedSourceDefinitionV1Alpha1",
    "SourceDefinitionResolver",
    "SourceAcquisitionMode",
    "validate_exact_https_uri",
    "validate_public_ip_literal",
]
