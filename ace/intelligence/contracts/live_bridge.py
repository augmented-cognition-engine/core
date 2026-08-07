"""Exact contracts for the narrow governed LIVE Intelligence bridge."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.reasoning import ReceiptReferenceV1Alpha1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import (
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
)
from ace.intelligence.contracts.ledger import (
    IntelligenceRecordKind,
    IntelligenceRecordReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    IntelligenceResourceMode,
)

LIVE_DERIVATION_REQUEST_VERSION = "ace.intelligence.live-derivation-request/v1alpha1"
LIVE_DERIVATION_RECEIPT_VERSION = "ace.intelligence.live-derivation-receipt/v1alpha1"


class _StrictFrozenContract(FrozenContract):
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


def _derive_identity(
    instance: _StrictFrozenContract,
    *,
    prefix: str,
    id_field: str,
    digest_field: str,
) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact LIVE bridge material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact LIVE bridge material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class LiveDerivationRequestV1Alpha1(_StrictFrozenContract):
    """One exact request to derive LIVE Shift, Signal, and attention state."""

    contract: Literal["ace.intelligence.live-derivation-request/v1alpha1"] = LIVE_DERIVATION_REQUEST_VERSION
    derivation_key: str
    product_id: str
    mode: Literal[IntelligenceResourceMode.LIVE] = IntelligenceResourceMode.LIVE
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    activation_revision: ActivationRevisionReferenceV1Alpha1
    pack: CompiledPackRefV1
    detector_id: str
    baseline: IntelligenceRecordReferenceV1Alpha1
    current: IntelligenceRecordReferenceV1Alpha1
    detected_at: datetime
    attention_evaluated_at: datetime
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("derivation_key")
    @classmethod
    def validate_derivation_key(cls, value: str) -> str:
        return validate_reference(value, name="derivation_key")

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("detector_id")
    @classmethod
    def validate_detector_id(cls, value: str) -> str:
        return validate_slug(value, name="detector_id")

    @field_validator("detected_at", "attention_evaluated_at", "requested_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        return validate_reference(value, name="request_id") if value is not None else None

    @field_validator("request_digest")
    @classmethod
    def validate_request_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        snapshots = (self.baseline, self.current)
        if (
            self.authenticated_context.product_id != self.product_id
            or self.activation_revision.product_id != self.product_id
            or any(
                item.product_id != self.product_id
                or item.mode is not IntelligenceResourceMode.LIVE
                or item.resource_kind is not IntelligenceRecordKind.ENTITY_SNAPSHOT
                for item in snapshots
            )
        ):
            raise ValueError("LIVE derivation crossed product, mode, or snapshot scope")
        if self.baseline.as_of >= self.current.as_of:
            raise ValueError("LIVE derivation baseline must precede current snapshot")
        if self.detected_at < max(item.available_at for item in snapshots):
            raise ValueError("LIVE derivation cannot predate admitted snapshot availability")
        if not self.detected_at <= self.attention_evaluated_at <= self.requested_at:
            raise ValueError("LIVE detection, attention, and request times must be ordered")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("LIVE derivation request must occur inside authentication")
        _derive_identity(
            self,
            prefix="live_derivation_request",
            id_field="request_id",
            digest_field="request_digest",
        )
        return self


class LiveDerivationReceiptV1Alpha1(_StrictFrozenContract):
    """Durable correlation for an authorized atomic LIVE derivation append."""

    contract: Literal["ace.intelligence.live-derivation-receipt/v1alpha1"] = LIVE_DERIVATION_RECEIPT_VERSION
    product_id: str
    mode: Literal[IntelligenceResourceMode.LIVE] = IntelligenceResourceMode.LIVE
    derivation_key: str
    request_id: str
    request_digest: str
    activation_revision: ActivationRevisionReferenceV1Alpha1
    activation_commit: ReceiptReferenceV1Alpha1
    pack: CompiledPackRefV1
    detector_id: str
    baseline: IntelligenceRecordReferenceV1Alpha1
    current: IntelligenceRecordReferenceV1Alpha1
    shift: IntelligenceRecordReferenceV1Alpha1
    signal: IntelligenceRecordReferenceV1Alpha1
    attention: IntelligenceRecordReferenceV1Alpha1
    append_authorization: ReceiptReferenceV1Alpha1
    created_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("derivation_key", "request_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("detector_id")
    @classmethod
    def validate_detector_id(cls, value: str) -> str:
        return validate_slug(value, name="detector_id")

    @field_validator("request_digest", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _aware(value, name="created_at")

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return validate_reference(value, name="receipt_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        expected = (
            (self.baseline, IntelligenceRecordKind.ENTITY_SNAPSHOT),
            (self.current, IntelligenceRecordKind.ENTITY_SNAPSHOT),
            (self.shift, IntelligenceRecordKind.SHIFT),
            (self.signal, IntelligenceRecordKind.SIGNAL),
            (self.attention, IntelligenceRecordKind.ATTENTION_DISPOSITION),
        )
        if self.activation_revision.product_id != self.product_id or any(
            item.product_id != self.product_id
            or item.mode is not IntelligenceResourceMode.LIVE
            or item.resource_kind is not kind
            for item, kind in expected
        ):
            raise ValueError("LIVE derivation receipt crossed product, mode, or record kinds")
        if self.created_at < self.attention.available_at:
            raise ValueError("LIVE derivation receipt cannot predate attention evaluation")
        _derive_identity(
            self,
            prefix="live_derivation_receipt",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


__all__ = [
    "LIVE_DERIVATION_RECEIPT_VERSION",
    "LIVE_DERIVATION_REQUEST_VERSION",
    "LiveDerivationReceiptV1Alpha1",
    "LiveDerivationRequestV1Alpha1",
]
