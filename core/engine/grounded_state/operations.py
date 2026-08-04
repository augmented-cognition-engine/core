"""TP8 append-only lifecycle and operational receipt service."""

from __future__ import annotations

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.grounded_state.operational_contracts import (
    OperationalReceiptV1,
    ProductLifecycleReceiptV1,
    ProductLifecycleState,
)


class GroundedProductArchivedError(RuntimeError):
    """A supported live operation targeted an archived product."""


def _record_key(value: str) -> str:
    table, separator, key = value.partition(":")
    if not separator or not table or not key:
        raise ValueError("operational identities require table:key form")
    return key


class StateEngineOperationsService:
    def __init__(self, pool) -> None:
        self.pool = pool

    async def latest_lifecycle(self, *, product_id: str) -> ProductLifecycleReceiptV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload, occurred_at, receipt_id FROM grounded_product_lifecycle "
                    "WHERE product = $product ORDER BY occurred_at DESC, receipt_id DESC LIMIT 1",
                    {"product": parse_record_id(product_id)},
                )
            )
        if not row or not isinstance(row.get("payload"), dict):
            return None
        return ProductLifecycleReceiptV1.model_validate(row["payload"])

    async def assert_active(self, *, product_id: str) -> None:
        latest = await self.latest_lifecycle(product_id=product_id)
        if latest is not None and latest.state is ProductLifecycleState.ARCHIVED:
            raise GroundedProductArchivedError(f"grounded-state product is archived: {product_id}")

    async def record_lifecycle(self, receipt: ProductLifecycleReceiptV1) -> ProductLifecycleReceiptV1:
        prior = await self.latest_lifecycle(product_id=receipt.product_id)
        prior_id = str(prior.receipt_id) if prior is not None else None
        if receipt.prior_receipt_id != prior_id:
            raise ValueError("product lifecycle transition must extend the exact latest receipt")
        if prior is not None and prior.state is receipt.state:
            raise ValueError("product lifecycle transition must change state")
        content = {
            "contract_version": receipt.contract_version,
            "product": parse_record_id(receipt.product_id),
            "receipt_id": receipt.receipt_id,
            "lifecycle_state": receipt.state.value,
            "prior_receipt_id": receipt.prior_receipt_id,
            "actor_ref": receipt.actor_ref,
            "reason": receipt.reason,
            "occurred_at": receipt.occurred_at,
            "payload": receipt.model_dump(mode="python"),
        }
        async with self.pool.connection() as db:
            result = await db.query(
                "CREATE ONLY type::record('grounded_product_lifecycle', $key) CONTENT $content",
                {"key": _record_key(str(receipt.receipt_id)), "content": content},
            )
        if isinstance(result, str):
            raise RuntimeError(f"product lifecycle persistence failed closed: {result[:240]}")
        return receipt

    async def persist_operation(self, receipt: OperationalReceiptV1) -> OperationalReceiptV1:
        content = {
            "contract_version": receipt.contract_version,
            "product": parse_record_id(receipt.product_id),
            "receipt_id": receipt.receipt_id,
            "run_id": receipt.run_id,
            "operation_id": receipt.operation_id,
            "operation_kind": receipt.operation_kind,
            "status": receipt.status.value,
            "started_at": receipt.started_at,
            "finished_at": receipt.finished_at,
            "material_hash": receipt.receipt_hash,
            "payload": receipt.model_dump(mode="python"),
        }
        async with self.pool.connection() as db:
            existing = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('grounded_operational_receipt', $key) "
                    "WHERE product = $product LIMIT 1",
                    {
                        "key": _record_key(str(receipt.receipt_id)),
                        "product": parse_record_id(receipt.product_id),
                    },
                )
            )
            if existing:
                stored = OperationalReceiptV1.model_validate(existing["payload"])
                if stored == receipt:
                    return receipt
                raise RuntimeError("operational receipt stable identity contains different material")
            result = await db.query(
                "CREATE ONLY type::record('grounded_operational_receipt', $key) CONTENT $content",
                {"key": _record_key(str(receipt.receipt_id)), "content": content},
            )
        if isinstance(result, str):
            raise RuntimeError(f"operational receipt persistence failed closed: {result[:240]}")
        return receipt

    async def operations(self, *, product_id: str, run_id: str) -> list[OperationalReceiptV1]:
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT payload, started_at, receipt_id FROM grounded_operational_receipt "
                    "WHERE product = $product AND run_id = $run_id ORDER BY started_at, receipt_id",
                    {"product": parse_record_id(product_id), "run_id": run_id},
                )
            )
        return [
            OperationalReceiptV1.model_validate(row["payload"]) for row in rows if isinstance(row.get("payload"), dict)
        ]
