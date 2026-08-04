"""Immutable TP8 product-lifecycle and operational evidence contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.contracts import FrozenContract, canonical_hash

PRODUCT_LIFECYCLE_VERSION = "ace.grounded-state.product-lifecycle/v1"
OPERATIONAL_RECEIPT_VERSION = "ace.grounded-state.operational-receipt/v1"


class ProductLifecycleState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class OperationalStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value


class ProductLifecycleReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.product-lifecycle/v1"] = PRODUCT_LIFECYCLE_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    state: ProductLifecycleState
    prior_receipt_id: str | None = Field(default=None, max_length=240)
    actor_ref: str = Field(min_length=1, max_length=240)
    reason: str = Field(min_length=1, max_length=1_000)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "occurred_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_product_lifecycle:{expected_hash[:32]}"
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("product lifecycle identity does not match exact material")
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("product lifecycle hash does not match exact material")
        object.__setattr__(self, "receipt_id", expected_id)
        object.__setattr__(self, "receipt_hash", expected_hash)
        return self


class OperationalReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.operational-receipt/v1"] = OPERATIONAL_RECEIPT_VERSION
    receipt_id: str | None = None
    receipt_hash: str | None = None
    product_id: str
    run_id: str = Field(min_length=1, max_length=240)
    operation_id: str = Field(min_length=1, max_length=240)
    operation_kind: str = Field(min_length=1, max_length=120)
    status: OperationalStatus
    started_at: datetime
    finished_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=50)

    @field_validator("started_at", "finished_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_and_derive(self) -> Self:
        if self.status is OperationalStatus.STARTED and self.finished_at is not None:
            raise ValueError("started operations cannot claim a finish time")
        if self.status is not OperationalStatus.STARTED and self.finished_at is None:
            raise ValueError("terminal operations require a finish time")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("operation finish cannot precede start")
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_hash = canonical_hash(material)
        expected_id = f"grounded_operational_receipt:{expected_hash[:32]}"
        if self.receipt_id is not None and self.receipt_id != expected_id:
            raise ValueError("operational receipt identity does not match exact material")
        if self.receipt_hash is not None and self.receipt_hash != expected_hash:
            raise ValueError("operational receipt hash does not match exact material")
        object.__setattr__(self, "receipt_id", expected_id)
        object.__setattr__(self, "receipt_hash", expected_hash)
        return self
