"""Append-only TP7 persistence over ACE's existing cognitive-memory table."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, TypeVar

from pydantic import BaseModel

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.promotion_contracts import (
    PromotedMemoryProjectionV1,
    PromotionDisposition,
    PromotionEffectiveState,
    PromotionMemoryLineageV1,
    PromotionProposalV1,
    PromotionReceiptV1,
    PromotionReviewV1,
)


class PromotionReplayConflict(RuntimeError):
    """A stable TP7 identity was replayed with different immutable material."""


class PromotionProductScopeError(RuntimeError):
    """TP7 material was unavailable in the requested product scope."""


class PromotionPersistenceError(RuntimeError):
    """An atomic TP7 write failed closed."""


TP7Model = PromotionProposalV1 | PromotionReviewV1 | PromotionReceiptV1 | PromotionMemoryLineageV1
ModelT = TypeVar("ModelT", bound=BaseModel)

_MODEL_TABLE: dict[type[BaseModel], str] = {
    PromotionProposalV1: "grounded_promotion_proposal",
    PromotionReviewV1: "grounded_promotion_review",
    PromotionReceiptV1: "grounded_promotion_receipt",
    PromotionMemoryLineageV1: "grounded_promotion_memory_lineage",
}


def _stable_id(record: TP7Model) -> str:
    if isinstance(record, PromotionProposalV1):
        return str(record.proposal_id)
    if isinstance(record, PromotionReviewV1):
        return str(record.review_id)
    if isinstance(record, PromotionReceiptV1):
        return str(record.receipt_id)
    if isinstance(record, PromotionMemoryLineageV1):
        return str(record.lineage_id)
    raise TypeError(f"unsupported TP7 stable identity: {type(record).__name__}")


def _material_hash(record: TP7Model) -> str:
    if isinstance(record, PromotionProposalV1):
        return str(record.proposal_hash)
    if isinstance(record, PromotionReviewV1):
        return str(record.review_hash)
    if isinstance(record, PromotionReceiptV1):
        return str(record.receipt_hash)
    if isinstance(record, PromotionMemoryLineageV1):
        return str(record.lineage_hash)
    raise TypeError(f"unsupported TP7 material hash: {type(record).__name__}")


def _record_key(stable_id: str) -> str:
    _, separator, key = stable_id.partition(":")
    if not separator or not key:
        raise ValueError("TP7 records require a bounded table-prefixed stable identity")
    return key


def _specific_fields(record: TP7Model) -> dict[str, Any]:
    if isinstance(record, PromotionProposalV1):
        return {
            "task_id": record.task_id,
            "target_kind": record.material.target_kind.value,
            "content_hash": record.material.content_hash,
            "evidence_pack_id": record.evidence_pack_id,
            "rollout_revision_id": record.rollout_revision_id,
            "proposed_at": record.proposed_at,
        }
    if isinstance(record, PromotionReviewV1):
        return {
            "proposal_id": record.proposal_id,
            "disposition": record.disposition.value,
            "authority": record.authority.value,
            "reviewed_at": record.reviewed_at,
        }
    if isinstance(record, PromotionReceiptV1):
        return {
            "proposal_id": record.proposal_id,
            "review_id": record.review_id,
            "disposition": record.disposition.value,
            "memory_id": record.memory_id,
            "supersedes_receipt_ids": list(record.supersedes_receipt_ids),
            "invalidates_receipt_ids": list(record.invalidates_receipt_ids),
            "contests_receipt_ids": list(record.contests_receipt_ids),
            "expires_at": record.expires_at,
            "effective_at": record.effective_at,
        }
    if isinstance(record, PromotionMemoryLineageV1):
        return {
            "memory_id": record.memory_id,
            "proposal_id": record.proposal_id,
            "receipt_id": record.receipt_id,
            "task_id": record.task_id,
            "evidence_pack_id": record.evidence_pack_id,
            "rollout_revision_id": record.rollout_revision_id,
            "created_at": record.created_at,
        }
    raise TypeError(f"unsupported TP7 persistence model: {type(record).__name__}")


def _content(record: TP7Model) -> dict[str, Any]:
    return {
        "contract_version": record.contract_version,
        "product": parse_record_id(record.product_id),
        "stable_id": _stable_id(record),
        "material_hash": _material_hash(record),
        "payload": record.model_dump(mode="python"),
        **_specific_fields(record),
    }


async def _query_or_raise(db, query: str, params: dict[str, Any]) -> Any:
    result = await db.query(query, params)
    if isinstance(result, str):
        raise PromotionPersistenceError(f"TP7 persistence failed closed: {result[:240]}")
    return result


class PromotionStore:
    """Durable product-scoped store for TP7 proposals and lifecycle receipts."""

    def __init__(self, pool) -> None:
        self.pool = pool

    async def _existing(self, db, record: TP7Model) -> bool:
        table = _MODEL_TABLE[type(record)]
        stable_id = _stable_id(record)
        row = parse_one(
            await db.query(
                f"SELECT material_hash, payload FROM ONLY type::record('{table}', $record_key) "
                "WHERE product = $product LIMIT 1",
                {
                    "record_key": _record_key(stable_id),
                    "product": parse_record_id(record.product_id),
                },
            )
        )
        if not row:
            return False
        payload = row.get("payload")
        stored = type(record).model_validate(payload) if isinstance(payload, dict) else None
        if (
            str(row.get("material_hash")) == _material_hash(record)
            and stored is not None
            and canonical_hash(stored) == canonical_hash(record)
        ):
            return True
        raise PromotionReplayConflict(f"stable TP7 identity {stable_id} contains different material")

    async def persist(self, record: TP7Model, *, db=None) -> TP7Model:
        async def write(connection):
            if await self._existing(connection, record):
                return record
            table = _MODEL_TABLE[type(record)]
            await _query_or_raise(
                connection,
                f"CREATE ONLY type::record('{table}', $record_key) CONTENT $content",
                {"record_key": _record_key(_stable_id(record)), "content": _content(record)},
            )
            return record

        if db is not None:
            return await write(db)
        async with self.pool.connection() as connection:
            return await write(connection)

    async def persist_all(self, records: Iterable[TP7Model]) -> tuple[TP7Model, ...]:
        normalized = tuple(sorted(records, key=_stable_id))
        if not normalized:
            return ()
        if len({record.product_id for record in normalized}) != 1:
            raise PromotionProductScopeError("one TP7 persistence batch cannot cross product scope")
        async with self.pool.connection() as db:
            missing = [record for record in normalized if not await self._existing(db, record)]
            if missing:
                statements = ["BEGIN TRANSACTION"]
                params: dict[str, Any] = {}
                for index, record in enumerate(missing):
                    params[f"record_key_{index}"] = _record_key(_stable_id(record))
                    params[f"content_{index}"] = _content(record)
                    statements.append(
                        f"CREATE ONLY type::record('{_MODEL_TABLE[type(record)]}', $record_key_{index}) "
                        f"CONTENT $content_{index}"
                    )
                statements.append("COMMIT TRANSACTION")
                await _query_or_raise(db, ";\n".join(statements) + ";", params)
        return normalized

    async def persist_disposition(
        self,
        *,
        review: PromotionReviewV1,
        receipt: PromotionReceiptV1,
        lineage: PromotionMemoryLineageV1 | None,
        memory: dict[str, Any] | None,
    ) -> PromotionReceiptV1:
        """Atomically write review, receipt, lineage, and existing-memory row."""
        records: tuple[TP7Model, ...] = (review, receipt, *((lineage,) if lineage is not None else ()))
        if len({record.product_id for record in records}) != 1:
            raise PromotionProductScopeError("promotion disposition cannot cross product scope")
        if (lineage is None) != (memory is None):
            raise PromotionPersistenceError("memory and lineage must be written together")
        if receipt.disposition is PromotionDisposition.ACCEPTED and lineage is None:
            raise PromotionPersistenceError("accepted promotion requires atomic memory lineage")
        if receipt.disposition is not PromotionDisposition.ACCEPTED and lineage is not None:
            raise PromotionPersistenceError("non-accepted promotion cannot write memory")

        async with self.pool.connection() as db:
            proposal = await self.load(
                PromotionProposalV1,
                receipt.proposal_id,
                product_id=receipt.product_id,
                db=db,
            )
            if proposal is None or proposal.proposal_hash != receipt.proposal_hash:
                raise PromotionProductScopeError("authoritative disposition requires the exact persisted proposal")

            existence = [await self._existing(db, record) for record in records]
            memory_exists = False
            if memory is not None:
                existing_memory = parse_one(
                    await db.query(
                        "SELECT product, content, source_kind, source_ref, promotion_material_hash "
                        "FROM ONLY <record>$memory_id WHERE product = $product LIMIT 1",
                        {
                            "memory_id": parse_record_id(str(memory["id"])),
                            "product": parse_record_id(receipt.product_id),
                        },
                    )
                )
                if existing_memory:
                    expected = {
                        "content": memory["content"],
                        "source_kind": "grounded_promotion",
                        "source_ref": receipt.receipt_id,
                        "promotion_material_hash": receipt.memory_hash,
                    }
                    actual = {
                        key: str(existing_memory.get(key)) if key == "source_ref" else existing_memory.get(key)
                        for key in expected
                    }
                    if actual != expected:
                        raise PromotionReplayConflict(
                            f"stable TP7 memory identity {memory['id']} contains different material"
                        )
                    memory_exists = True

            if all(existence) and (memory is None or memory_exists):
                return receipt
            if any(existence) or memory_exists:
                raise PromotionReplayConflict("partial TP7 disposition chain exists; atomic replay fails closed")

            statements = ["BEGIN TRANSACTION"]
            params: dict[str, Any] = {}
            for index, record in enumerate(records):
                params[f"record_key_{index}"] = _record_key(_stable_id(record))
                params[f"content_{index}"] = _content(record)
                statements.append(
                    f"CREATE ONLY type::record('{_MODEL_TABLE[type(record)]}', $record_key_{index}) "
                    f"CONTENT $content_{index}"
                )
            if memory is not None:
                params["memory_id"] = parse_record_id(str(memory["id"]))
                params["memory"] = {key: value for key, value in memory.items() if key != "id"}
                params["memory"]["product"] = parse_record_id(receipt.product_id)
                statements.append("CREATE ONLY <record>$memory_id CONTENT $memory")
            statements.append("COMMIT TRANSACTION")
            await _query_or_raise(db, ";\n".join(statements) + ";", params)
        return receipt

    async def load(
        self,
        model: type[ModelT],
        stable_id: str,
        *,
        product_id: str,
        db=None,
    ) -> ModelT | None:
        table = _MODEL_TABLE[model]

        async def read(connection):
            row = parse_one(
                await connection.query(
                    f"SELECT payload FROM ONLY type::record('{table}', $record_key) WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(stable_id),
                        "product": parse_record_id(product_id),
                    },
                )
            )
            if not row or not isinstance(row.get("payload"), dict):
                return None
            return model.model_validate(row["payload"])

        if db is not None:
            return await read(db)
        async with self.pool.connection() as connection:
            return await read(connection)

    async def require(self, model: type[ModelT], stable_id: str, *, product_id: str) -> ModelT:
        record = await self.load(model, stable_id, product_id=product_id)
        if record is None:
            raise PromotionProductScopeError(f"TP7 record is unavailable in product scope: {stable_id}")
        return record

    async def list_records(self, model: type[ModelT], *, product_id: str) -> list[ModelT]:
        table = _MODEL_TABLE[model]
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    f"SELECT payload, stable_id FROM {table} WHERE product = $product ORDER BY stable_id",
                    {"product": parse_record_id(product_id)},
                )
            )
        return [model.model_validate(row["payload"]) for row in rows if isinstance(row.get("payload"), dict)]

    async def effective_states(
        self,
        *,
        product_id: str,
        now: datetime | None = None,
    ) -> dict[str, PromotionEffectiveState]:
        receipts = await self.list_records(PromotionReceiptV1, product_id=product_id)
        states = {
            str(receipt.receipt_id): (
                PromotionEffectiveState.ACTIVE
                if receipt.disposition is PromotionDisposition.ACCEPTED
                else PromotionEffectiveState(receipt.disposition.value)
            )
            for receipt in receipts
        }
        reference = now or datetime.now(timezone.utc)
        for receipt in receipts:
            if receipt.expires_at is not None and receipt.expires_at <= reference:
                states[str(receipt.receipt_id)] = PromotionEffectiveState.EXPIRED
            for related in receipt.supersedes_receipt_ids:
                if related in states:
                    states[related] = PromotionEffectiveState.SUPERSEDED
            for related in receipt.invalidates_receipt_ids:
                if related in states:
                    states[related] = PromotionEffectiveState.INVALIDATED
            for related in receipt.contests_receipt_ids:
                if related in states and states[related] is PromotionEffectiveState.ACTIVE:
                    states[related] = PromotionEffectiveState.CONTESTED
        return {key: states[key] for key in sorted(states)}

    async def list_authoritative_memories(
        self,
        *,
        product_id: str,
        domain_path: str | None = None,
        limit: int = 20,
    ) -> list[PromotedMemoryProjectionV1]:
        states = await self.effective_states(product_id=product_id)
        lineages = await self.list_records(PromotionMemoryLineageV1, product_id=product_id)
        receipts = {
            str(item.receipt_id): item for item in await self.list_records(PromotionReceiptV1, product_id=product_id)
        }
        proposals = {
            str(item.proposal_id): item for item in await self.list_records(PromotionProposalV1, product_id=product_id)
        }
        projections: list[PromotedMemoryProjectionV1] = []
        async with self.pool.connection() as db:
            for lineage in lineages:
                if states.get(lineage.receipt_id) is not PromotionEffectiveState.ACTIVE:
                    continue
                receipt = receipts.get(lineage.receipt_id)
                proposal = proposals.get(lineage.proposal_id)
                if receipt is None or proposal is None:
                    missing = [name for name, value in (("receipt", receipt), ("proposal", proposal)) if value is None]
                    raise PromotionPersistenceError(
                        f"promotion memory lineage has missing immutable inputs: {', '.join(missing)}"
                    )
                if domain_path and proposal.material.domain_path != domain_path:
                    continue
                memory = parse_one(
                    await db.query(
                        "SELECT id, product, content, promotion_material_hash FROM ONLY <record>$memory_id "
                        "WHERE product = $product AND source_kind = 'grounded_promotion' "
                        "AND source_ref = $receipt_id LIMIT 1",
                        {
                            "memory_id": parse_record_id(lineage.memory_id),
                            "product": parse_record_id(product_id),
                            "receipt_id": receipt.receipt_id,
                        },
                    )
                )
                if not memory:
                    raise PromotionPersistenceError("authoritative promotion lineage is missing its cognitive memory")
                if (
                    str(memory.get("promotion_material_hash")) != lineage.memory_hash
                    or str(memory.get("id")) != lineage.memory_id
                    or memory.get("content") != proposal.material.content
                ):
                    raise PromotionReplayConflict("promoted cognitive memory does not match immutable lineage")
                projections.append(
                    PromotedMemoryProjectionV1(
                        product_id=product_id,
                        memory_id=lineage.memory_id,
                        memory_hash=lineage.memory_hash,
                        receipt_id=lineage.receipt_id,
                        receipt_hash=lineage.receipt_hash,
                        lineage_id=str(lineage.lineage_id),
                        target_kind=proposal.material.target_kind,
                        memory_meaning=proposal.material.memory_meaning,
                        content=proposal.material.content,
                        content_hash=str(proposal.material.content_hash),
                        domain_path=proposal.material.domain_path,
                        tags=proposal.material.tags,
                        effective_state=PromotionEffectiveState.ACTIVE,
                        evidence_pack_id=lineage.evidence_pack_id,
                        evidence_pack_hash=lineage.evidence_pack_hash,
                        created_at=lineage.created_at,
                    )
                )
        projections.sort(key=lambda item: (item.created_at, item.memory_id), reverse=True)
        return projections[: max(1, min(limit, 20))]
