"""Domain-neutral append-only record and atomic transaction contracts.

Core owns product fencing, storage identity, transactionality, replay conflicts,
availability-time reads, and durable transaction receipts. Payload vocabulary is
opaque to this boundary and belongs to the calling bounded context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Protocol, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, stable_id
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1

IMMUTABLE_RECORD_VERSION = "ace.core.immutable-record/v1alpha1"
IMMUTABLE_RECORD_REFERENCE_VERSION = "ace.core.immutable-record-reference/v1alpha1"
APPEND_ONLY_TRANSACTION_VERSION = "ace.core.append-only-transaction/v1alpha1"
APPEND_ONLY_TRANSACTION_RECEIPT_VERSION = "ace.core.append-only-transaction-receipt/v1alpha1"

MAX_TRANSACTION_RECORDS = 1_024


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _bounded(value: str, *, name: str, maximum: int = 240) -> str:
    if not value or len(value) > maximum or value != value.strip():
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def immutable_record_storage_id(*, product_id: str, record_space: str, record_kind: str, record_key: str) -> str:
    """Return Core's stable identity for one immutable logical record."""

    return stable_id(
        "immutable_record",
        {
            "product_id": _bounded(product_id, name="product_id"),
            "record_space": _bounded(record_space, name="record_space", maximum=120),
            "record_kind": _bounded(record_kind, name="record_kind", maximum=120),
            "record_key": _bounded(record_key, name="record_key"),
        },
    )


def append_only_transaction_id(*, product_id: str, record_space: str, transaction_key: str) -> str:
    """Return Core's stable identity for one product-scoped append attempt."""

    return stable_id(
        "append_only_transaction",
        {
            "product_id": _bounded(product_id, name="product_id"),
            "record_space": _bounded(record_space, name="record_space", maximum=120),
            "transaction_key": _bounded(transaction_key, name="transaction_key"),
        },
    )


def append_only_receipt_id(*, product_id: str, record_space: str, transaction_key: str) -> str:
    """Return Core's stable durable receipt identity for one append attempt."""

    return stable_id(
        "append_only_receipt",
        {
            "product_id": _bounded(product_id, name="product_id"),
            "record_space": _bounded(record_space, name="record_space", maximum=120),
            "transaction_key": _bounded(transaction_key, name="transaction_key"),
        },
    )


def _canonical_preconditions(
    value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
    identities = [(item.state_kind, item.product_id, item.state_id) for item in value]
    if len(identities) != len(set(identities)):
        raise ValueError("governed-state preconditions must name each exact state identity at most once")
    return tuple(
        sorted(
            value,
            key=lambda item: (
                item.state_kind,
                item.product_id,
                item.state_id,
                item.sequence,
                item.revision_id,
                item.commit_receipt_id,
            ),
        )
    )


class ImmutableRecordV1(_StrictFrozenContract):
    """One opaque append-only record with Core-owned storage identity."""

    contract: Literal["ace.core.immutable-record/v1alpha1"] = IMMUTABLE_RECORD_VERSION
    product_id: str
    record_space: str
    record_kind: str
    record_key: str
    payload_contract: str
    payload: dict[str, Any]
    as_of: datetime
    available_at: datetime
    processing_order: int = Field(ge=0)
    storage_id: str | None = None
    material_hash: str | None = None

    @field_validator("product_id", "record_key", "payload_contract")
    @classmethod
    def validate_bounded_fields(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("record_space", "record_kind")
    @classmethod
    def validate_classifier_fields(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name, maximum=120)

    @field_validator("as_of", "available_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.available_at < self.as_of:
            raise ValueError("available_at cannot precede as_of")
        expected_storage_id = immutable_record_storage_id(
            product_id=self.product_id,
            record_space=self.record_space,
            record_kind=self.record_kind,
            record_key=self.record_key,
        )
        material = self.model_dump(mode="json", exclude={"storage_id", "material_hash"})
        expected_hash = f"sha256:{canonical_hash(material)}"
        if self.storage_id is not None and self.storage_id != expected_storage_id:
            raise ValueError("storage_id does not match the exact record scope and key")
        if self.material_hash is not None and self.material_hash != expected_hash:
            raise ValueError("material_hash does not match the exact immutable record")
        object.__setattr__(self, "storage_id", expected_storage_id)
        object.__setattr__(self, "material_hash", expected_hash)
        return self

    def reference(self) -> ImmutableRecordReferenceV1:
        return ImmutableRecordReferenceV1(
            product_id=self.product_id,
            record_space=self.record_space,
            record_kind=self.record_kind,
            record_key=self.record_key,
            storage_id=str(self.storage_id),
            material_hash=str(self.material_hash),
            payload_contract=self.payload_contract,
            as_of=self.as_of,
            available_at=self.available_at,
            processing_order=self.processing_order,
        )


class ImmutableRecordReferenceV1(_StrictFrozenContract):
    """Exact replay coordinates for one stored immutable record."""

    contract: Literal["ace.core.immutable-record-reference/v1alpha1"] = IMMUTABLE_RECORD_REFERENCE_VERSION
    product_id: str
    record_space: str
    record_kind: str
    record_key: str
    storage_id: str
    material_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    payload_contract: str
    as_of: datetime
    available_at: datetime
    processing_order: int = Field(ge=0)

    @field_validator("product_id", "record_key", "storage_id", "payload_contract")
    @classmethod
    def validate_bounded_fields(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("record_space", "record_kind")
    @classmethod
    def validate_classifier_fields(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name, maximum=120)

    @field_validator("as_of", "available_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        expected = immutable_record_storage_id(
            product_id=self.product_id,
            record_space=self.record_space,
            record_kind=self.record_kind,
            record_key=self.record_key,
        )
        if self.storage_id != expected:
            raise ValueError("record reference storage_id does not match its exact scope and key")
        if self.available_at < self.as_of:
            raise ValueError("record reference available_at cannot precede as_of")
        return self


class AppendOnlyTransactionRequestV1(_StrictFrozenContract):
    """One exact atomic append across an ordered immutable record set."""

    contract: Literal["ace.core.append-only-transaction/v1alpha1"] = APPEND_ONLY_TRANSACTION_VERSION
    product_id: str
    record_space: str
    transaction_key: str
    records: tuple[ImmutableRecordV1, ...] = Field(min_length=1, max_length=MAX_TRANSACTION_RECORDS)
    submitted_at: datetime
    governed_state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=64,
        exclude_if=lambda value: not value,
    )
    transaction_id: str | None = None
    request_hash: str | None = None

    @field_validator("product_id", "transaction_key")
    @classmethod
    def validate_bounded_fields(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("record_space")
    @classmethod
    def validate_record_space(cls, value: str) -> str:
        return _bounded(value, name="record_space", maximum=120)

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, value: datetime) -> datetime:
        return _aware(value, "submitted_at")

    @field_validator("governed_state_preconditions", mode="before")
    @classmethod
    def preserve_precondition_collection(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("governed_state_preconditions must be an ordered collection")
        return tuple(value)

    @field_validator("governed_state_preconditions")
    @classmethod
    def canonicalize_preconditions(
        cls,
        value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        return _canonical_preconditions(value)

    @model_validator(mode="after")
    def validate_scope_order_and_identity(self) -> Self:
        if any(record.product_id != self.product_id for record in self.records):
            raise ValueError("every record must use the transaction product scope")
        if any(record.record_space != self.record_space for record in self.records):
            raise ValueError("every record must use the transaction record space")
        if any(precondition.product_id != self.product_id for precondition in self.governed_state_preconditions):
            raise ValueError("every governed-state precondition must use the transaction product scope")
        if any(record.available_at > self.submitted_at for record in self.records):
            raise ValueError("transaction submission cannot predate record availability")
        orders = tuple(record.processing_order for record in self.records)
        if orders != tuple(range(len(self.records))):
            raise ValueError("records must use one gap-free deterministic processing order")
        storage_ids = [record.storage_id for record in self.records]
        if len(storage_ids) != len(set(storage_ids)):
            raise ValueError("a transaction cannot contain the same storage identity twice")

        expected_id = append_only_transaction_id(
            product_id=self.product_id,
            record_space=self.record_space,
            transaction_key=self.transaction_key,
        )
        material = self.model_dump(mode="json", exclude={"transaction_id", "request_hash"})
        expected_hash = f"sha256:{canonical_hash(material)}"
        if self.transaction_id is not None and self.transaction_id != expected_id:
            raise ValueError("transaction_id does not match the exact product, space, and key")
        if self.request_hash is not None and self.request_hash != expected_hash:
            raise ValueError("request_hash does not match the exact append request")
        object.__setattr__(self, "transaction_id", expected_id)
        object.__setattr__(self, "request_hash", expected_hash)
        return self

    def receipt(self) -> AppendOnlyTransactionReceiptV1:
        return AppendOnlyTransactionReceiptV1(
            product_id=self.product_id,
            record_space=self.record_space,
            transaction_key=self.transaction_key,
            transaction_id=str(self.transaction_id),
            request_hash=str(self.request_hash),
            records=tuple(record.reference() for record in self.records),
            committed_at=self.submitted_at,
            governed_state_preconditions=self.governed_state_preconditions,
        )


class AppendOnlyTransactionReceiptV1(_StrictFrozenContract):
    """Durable proof that one exact record set committed atomically."""

    contract: Literal["ace.core.append-only-transaction-receipt/v1alpha1"] = APPEND_ONLY_TRANSACTION_RECEIPT_VERSION
    disposition: Literal["committed"] = "committed"
    product_id: str
    record_space: str
    transaction_key: str
    transaction_id: str
    request_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    records: tuple[ImmutableRecordReferenceV1, ...] = Field(min_length=1, max_length=MAX_TRANSACTION_RECORDS)
    committed_at: datetime
    governed_state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=64,
        exclude_if=lambda value: not value,
    )
    receipt_id: str | None = None
    receipt_hash: str | None = None

    @field_validator("product_id", "transaction_key", "transaction_id")
    @classmethod
    def validate_bounded_fields(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("record_space")
    @classmethod
    def validate_record_space(cls, value: str) -> str:
        return _bounded(value, name="record_space", maximum=120)

    @field_validator("committed_at")
    @classmethod
    def validate_committed_at(cls, value: datetime) -> datetime:
        return _aware(value, "committed_at")

    @field_validator("governed_state_preconditions", mode="before")
    @classmethod
    def preserve_precondition_collection(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("governed_state_preconditions must be an ordered collection")
        return tuple(value)

    @field_validator("governed_state_preconditions")
    @classmethod
    def canonicalize_preconditions(
        cls,
        value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        return _canonical_preconditions(value)

    @model_validator(mode="after")
    def validate_scope_order_and_identity(self) -> Self:
        expected_transaction_id = append_only_transaction_id(
            product_id=self.product_id,
            record_space=self.record_space,
            transaction_key=self.transaction_key,
        )
        if self.transaction_id != expected_transaction_id:
            raise ValueError("receipt transaction_id does not match its exact scope")
        if any(record.product_id != self.product_id for record in self.records):
            raise ValueError("receipt records crossed the transaction product scope")
        if any(record.record_space != self.record_space for record in self.records):
            raise ValueError("receipt records crossed the transaction record space")
        if any(precondition.product_id != self.product_id for precondition in self.governed_state_preconditions):
            raise ValueError("receipt governed-state preconditions crossed the transaction product scope")
        if tuple(record.processing_order for record in self.records) != tuple(range(len(self.records))):
            raise ValueError("receipt records must preserve the exact processing order")
        if any(record.available_at > self.committed_at for record in self.records):
            raise ValueError("receipt cannot predate record availability")

        expected_receipt_id = append_only_receipt_id(
            product_id=self.product_id,
            record_space=self.record_space,
            transaction_key=self.transaction_key,
        )
        material = self.model_dump(mode="json", exclude={"receipt_id", "receipt_hash"})
        expected_receipt_hash = f"sha256:{canonical_hash(material)}"
        if self.receipt_id is not None and self.receipt_id != expected_receipt_id:
            raise ValueError("receipt_id does not match the exact transaction scope")
        if self.receipt_hash is not None and self.receipt_hash != expected_receipt_hash:
            raise ValueError("receipt_hash does not match the exact durable receipt")
        object.__setattr__(self, "receipt_id", expected_receipt_id)
        object.__setattr__(self, "receipt_hash", expected_receipt_hash)
        return self


class ImmutableRecordPersistenceError(RuntimeError):
    """A durable immutable-record operation failed closed."""


class ImmutableRecordReplayConflict(ImmutableRecordPersistenceError):
    """A stable record or transaction identity already binds different material."""


class ImmutableRecordPreconditionFailed(ImmutableRecordPersistenceError):
    """A required governed-state head was absent or no longer exact."""


class ImmutableRecordScopeError(ImmutableRecordPersistenceError):
    """A record was requested outside its exact product or record space."""


class ImmutableRecordStore(Protocol):
    """Core port implemented by one transaction-capable persistence adapter."""

    async def append(self, request: AppendOnlyTransactionRequestV1) -> AppendOnlyTransactionReceiptV1: ...

    async def load_record(
        self,
        storage_id: str,
        *,
        product_id: str,
        record_space: str,
        record_kind: str,
    ) -> ImmutableRecordV1 | None: ...

    async def load_transaction_receipt(
        self,
        *,
        product_id: str,
        record_space: str,
        transaction_key: str,
    ) -> AppendOnlyTransactionReceiptV1 | None: ...

    async def read_as_of(
        self,
        *,
        product_id: str,
        record_space: str,
        record_kind: str,
        available_at: datetime,
    ) -> tuple[ImmutableRecordV1, ...]: ...

    async def count_as_of(
        self,
        *,
        product_id: str,
        record_space: str,
        record_kind: str,
        available_at: datetime,
    ) -> int: ...

    async def scan_product_records(self, *, product_id: str) -> tuple[ImmutableRecordV1, ...]:
        """Return exact records inside one product fence for rebuildable projections and lifecycle work."""
        ...


__all__ = [
    "APPEND_ONLY_TRANSACTION_RECEIPT_VERSION",
    "APPEND_ONLY_TRANSACTION_VERSION",
    "IMMUTABLE_RECORD_REFERENCE_VERSION",
    "IMMUTABLE_RECORD_VERSION",
    "AppendOnlyTransactionReceiptV1",
    "AppendOnlyTransactionRequestV1",
    "ImmutableRecordPersistenceError",
    "ImmutableRecordPreconditionFailed",
    "ImmutableRecordReferenceV1",
    "ImmutableRecordReplayConflict",
    "ImmutableRecordScopeError",
    "ImmutableRecordStore",
    "ImmutableRecordV1",
    "append_only_receipt_id",
    "append_only_transaction_id",
    "immutable_record_storage_id",
]
