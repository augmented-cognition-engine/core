"""Storage-neutral Core ports and failure semantics for Agent Memory."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from ace.core.agent_memory import (
    AgentMemoryLedgerReadV1Alpha1,
    AgentMemoryScopeV1Alpha1,
    ErasureDependencyProofV1Alpha1,
    LedgerCoordinateV1Alpha1,
    LifecycleEventV1Alpha1,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReferenceV1,
    ImmutableRecordV1,
)


class AgentMemoryPortFailureCode(StrEnum):
    INVALID_CONTRACT = "invalid_contract"
    UNAUTHORIZED = "unauthorized"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"
    DEPENDENCY_INCOMPLETE = "dependency_incomplete"


class AgentMemoryPortError(RuntimeError):
    """Typed fail-closed adapter error with explicit retry semantics."""

    def __init__(
        self,
        code: AgentMemoryPortFailureCode,
        message: str,
        *,
        retry_safe: bool,
        receipt_ref: str | None = None,
    ) -> None:
        if code is AgentMemoryPortFailureCode.INDETERMINATE:
            if retry_safe:
                raise ValueError("indeterminate outcomes are never safe for blind retry")
            if receipt_ref is None:
                raise ValueError("indeterminate outcomes require an exact receipt lookup reference")
        super().__init__(message)
        self.code = code
        self.retry_safe = retry_safe
        self.receipt_ref = receipt_ref

    @property
    def receipt_lookup_required(self) -> bool:
        """Whether recovery must resolve the durable receipt before another append."""

        return self.code is AgentMemoryPortFailureCode.INDETERMINATE


@runtime_checkable
class AgentMemoryLedgerWriter(Protocol):
    """Append memory events through Core's existing atomic record contract."""

    async def append(self, request: AppendOnlyTransactionRequestV1) -> AppendOnlyTransactionReceiptV1: ...

    async def load_transaction_receipt(
        self,
        *,
        product_id: str,
        record_space: str,
        transaction_key: str,
    ) -> AppendOnlyTransactionReceiptV1 | None: ...


@runtime_checkable
class AgentMemoryLedgerReader(Protocol):
    """Read only after an authenticated scope and temporal query are resolved."""

    async def load(
        self,
        record_ref: str,
        *,
        scope: AgentMemoryScopeV1Alpha1,
        ledger_at: LedgerCoordinateV1Alpha1 | None = None,
    ) -> ImmutableRecordV1 | None: ...

    async def query(self, request: AgentMemoryLedgerReadV1Alpha1) -> tuple[ImmutableRecordReferenceV1, ...]: ...


@runtime_checkable
class MemoryDependencyIndex(Protocol):
    """Track every primary and derived dependency required for hard erasure."""

    async def record_dependencies(
        self,
        *,
        scope: AgentMemoryScopeV1Alpha1,
        root_ref: str,
        dependent_refs: tuple[str, ...],
        idempotency_key: str,
    ) -> str: ...

    async def enumerate_dependencies(
        self,
        *,
        scope: AgentMemoryScopeV1Alpha1,
        root_ref: str,
    ) -> tuple[str, ...]: ...

    async def verify_erasure(self, event: LifecycleEventV1Alpha1) -> ErasureDependencyProofV1Alpha1: ...


__all__ = [
    "AgentMemoryLedgerReader",
    "AgentMemoryLedgerWriter",
    "AgentMemoryPortError",
    "AgentMemoryPortFailureCode",
    "MemoryDependencyIndex",
]
