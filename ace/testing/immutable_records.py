"""In-memory Core-port conformance seam with atomic failure injection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from ace.application.intelligence_ledger import (
    PreparedIntelligenceAdmission,
    PreparedIntelligenceLedgerService,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordPreconditionFailed,
    ImmutableRecordReplayConflict,
    ImmutableRecordV1,
    append_only_receipt_id,
)
from ace.core.state import GovernedStateHeadV1
from ace.intelligence.contracts.ledger import PreparedResourceAdmissionV1Alpha1


class InMemoryImmutableRecordStore:
    """Reference port implementation for fast conformance and fault tests.

    This is not a production source of truth. External packages can exercise
    public service contracts without importing ``core.engine``; production hosts
    must supply Core's database-backed adapter.
    """

    def __init__(
        self,
        *,
        fail_after_records: int | None = None,
        governed_state_heads: dict[tuple[str, str, str], GovernedStateHeadV1] | None = None,
    ) -> None:
        if fail_after_records is not None and fail_after_records < 1:
            raise ValueError("fail_after_records must be positive")
        self.fail_after_records = fail_after_records
        self.records: dict[str, ImmutableRecordV1] = {}
        self.receipts: dict[str, AppendOnlyTransactionReceiptV1] = {}
        self.governed_state_heads = governed_state_heads if governed_state_heads is not None else {}
        self._lock = asyncio.Lock()

    def set_governed_state_head(self, head: GovernedStateHeadV1) -> None:
        """Install or replace one exact head for public atomic-conformance tests."""

        validated = GovernedStateHeadV1.model_validate(head.model_dump(mode="python"))
        self.governed_state_heads[(validated.state_kind, validated.product_id, validated.state_id)] = validated

    async def append(
        self,
        request: AppendOnlyTransactionRequestV1,
    ) -> AppendOnlyTransactionReceiptV1:
        try:
            validated = AppendOnlyTransactionRequestV1.model_validate(request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ImmutableRecordPersistenceError("append request failed exact revalidation") from exc
        expected = validated.receipt()
        async with self._lock:
            existing_receipt = self.receipts.get(str(expected.receipt_id))
            if existing_receipt is not None:
                if existing_receipt == expected:
                    return existing_receipt
                raise ImmutableRecordReplayConflict("stable transaction identity already binds different material")
            for precondition in validated.governed_state_preconditions:
                current = self.governed_state_heads.get(
                    (precondition.state_kind, precondition.product_id, precondition.state_id)
                )
                if current is None or (
                    current.sequence != precondition.sequence
                    or current.revision_id != precondition.revision_id
                    or current.commit_receipt_id != precondition.commit_receipt_id
                ):
                    raise ImmutableRecordPreconditionFailed("immutable_record_governed_state_precondition_failed")
            conflicting = [
                str(record.storage_id) for record in validated.records if str(record.storage_id) in self.records
            ]
            if conflicting:
                raise ImmutableRecordReplayConflict(
                    f"immutable records already exist without the exact receipt: {sorted(conflicting)}"
                )

            staged: dict[str, ImmutableRecordV1] = {}
            for index, record in enumerate(validated.records, start=1):
                staged[str(record.storage_id)] = record
                if self.fail_after_records == index:
                    raise ImmutableRecordPersistenceError("simulated interruption before atomic transaction commit")
            self.records.update(staged)
            self.receipts[str(expected.receipt_id)] = expected
            return expected

    async def load_record(
        self,
        storage_id: str,
        *,
        product_id: str,
        record_space: str,
        record_kind: str,
    ) -> ImmutableRecordV1 | None:
        record = self.records.get(storage_id)
        if record is None or (
            record.product_id != product_id or record.record_space != record_space or record.record_kind != record_kind
        ):
            return None
        return ImmutableRecordV1.model_validate(record.model_dump(mode="python"))

    async def load_transaction_receipt(
        self,
        *,
        product_id: str,
        record_space: str,
        transaction_key: str,
    ) -> AppendOnlyTransactionReceiptV1 | None:
        receipt_id = append_only_receipt_id(
            product_id=product_id,
            record_space=record_space,
            transaction_key=transaction_key,
        )
        receipt = self.receipts.get(receipt_id)
        if receipt is None or (receipt.product_id != product_id or receipt.record_space != record_space):
            return None
        return AppendOnlyTransactionReceiptV1.model_validate(receipt.model_dump(mode="python"))

    async def read_as_of(
        self,
        *,
        product_id: str,
        record_space: str,
        record_kind: str,
        available_at: datetime,
    ) -> tuple[ImmutableRecordV1, ...]:
        if available_at.tzinfo is None or available_at.utcoffset() is None:
            raise ValueError("available_at must include a timezone")
        cutoff = available_at.astimezone(UTC)
        matches = [
            record
            for record in self.records.values()
            if record.product_id == product_id
            and record.record_space == record_space
            and record.record_kind == record_kind
            and record.available_at <= cutoff
        ]
        matches.sort(key=lambda record: (record.available_at, str(record.storage_id)))
        return tuple(ImmutableRecordV1.model_validate(record.model_dump(mode="python")) for record in matches)

    async def count_as_of(
        self,
        *,
        product_id: str,
        record_space: str,
        record_kind: str,
        available_at: datetime,
    ) -> int:
        return len(
            await self.read_as_of(
                product_id=product_id,
                record_space=record_space,
                record_kind=record_kind,
                available_at=available_at,
            )
        )


@dataclass(frozen=True, slots=True)
class PreparedLedgerConformanceResult:
    first: PreparedIntelligenceAdmission
    exact_replay: PreparedIntelligenceAdmission
    restarted_replay: PreparedIntelligenceAdmission


async def exercise_prepared_ledger_restart(
    *,
    first_service: PreparedIntelligenceLedgerService,
    restarted_service: PreparedIntelligenceLedgerService,
    batch: PreparedResourceAdmissionV1Alpha1,
) -> PreparedLedgerConformanceResult:
    """Assert exact append replay and fresh-service replay through public seams."""

    first = await first_service.admit(batch)
    exact_replay = await first_service.admit(batch)
    restarted_replay = await restarted_service.replay(derivation_key=batch.derivation_key)
    if restarted_replay is None:
        raise AssertionError("fresh service could not reopen the durable transaction")
    if first != exact_replay or first != restarted_replay:
        raise AssertionError("prepared ledger replay changed resources or durable receipts")
    return PreparedLedgerConformanceResult(
        first=first,
        exact_replay=exact_replay,
        restarted_replay=restarted_replay,
    )


__all__ = [
    "InMemoryImmutableRecordStore",
    "PreparedLedgerConformanceResult",
    "exercise_prepared_ledger_restart",
]
