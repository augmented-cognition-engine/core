"""SurrealDB adapter for domain-neutral Core governed-state commits."""

from __future__ import annotations

import asyncio
from typing import Any

from ace.core.contracts import stable_id
from ace.core.state import (
    GovernedStateCommitReceiptV1,
    GovernedStateCommitRequestV1,
    GovernedStateHeadV1,
    GovernedStateRevisionV1,
)
from core.engine.core.db import parse_one, parse_record_id, parse_rows


class GovernedStatePersistenceError(RuntimeError):
    """A governed-state durable operation failed closed."""


class GovernedStateHeadConflict(GovernedStatePersistenceError):
    """The caller's exact expected head is no longer current."""


class GovernedStateReplayConflict(GovernedStatePersistenceError):
    """A stable identity already exists with different or partial material."""


class GovernedStateScopeError(GovernedStatePersistenceError):
    """State was unavailable in the requested product scope."""


def _record_key(value: str) -> str:
    _, separator, key = value.partition(":")
    if not separator or not key:
        raise ValueError("governed state requires table-prefixed stable identities")
    return key


def _errors(result: Any) -> list[str]:
    if isinstance(result, str):
        return [result]
    if isinstance(result, dict):
        result = result.get("result", result)
    errors: list[str] = []
    if isinstance(result, list):
        for item in result:
            if isinstance(item, str):
                errors.append(item)
            elif isinstance(item, dict) and str(item.get("status", "")).upper() == "ERR":
                errors.append(str(item.get("result") or item.get("detail") or item))
    return errors


def _raise_query_errors(result: Any) -> None:
    errors = _errors(result)
    if not errors:
        return
    detail = " | ".join(errors)[:1_000]
    if "governed_state_head_conflict" in detail:
        raise GovernedStateHeadConflict("governed_state_head_conflict")
    raise GovernedStatePersistenceError(f"governed-state transaction failed: {detail}")


class SurrealGovernedStateStore:
    """Atomic revision, head, receipt, and audit persistence on Core's pool."""

    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def load_head(
        self,
        *,
        state_kind: str,
        product_id: str,
        state_id: str,
    ) -> GovernedStateHeadV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('governed_state_head', $record_key) "
                    "WHERE product = $product AND state_kind = $state_kind "
                    "AND state_id = $state_id LIMIT 1",
                    {
                        "record_key": _record_key(
                            stable_id(
                                "governed_state_head",
                                {
                                    "state_kind": state_kind,
                                    "product_id": product_id,
                                    "state_id": state_id,
                                },
                            )
                        ),
                        "product": parse_record_id(product_id),
                        "state_kind": state_kind,
                        "state_id": state_id,
                    },
                )
            )
        return (
            GovernedStateHeadV1.model_validate(row["payload"]) if row and isinstance(row.get("payload"), dict) else None
        )

    async def load_revision(
        self,
        revision_id: str,
        *,
        product_id: str,
    ) -> GovernedStateRevisionV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('governed_state_revision', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(revision_id),
                        "product": parse_record_id(product_id),
                    },
                )
            )
        return (
            GovernedStateRevisionV1.model_validate(row["payload"])
            if row and isinstance(row.get("payload"), dict)
            else None
        )

    async def load_receipt(
        self,
        receipt_id: str,
        *,
        product_id: str,
    ) -> GovernedStateCommitReceiptV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('governed_state_commit_receipt', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(receipt_id),
                        "product": parse_record_id(product_id),
                    },
                )
            )
        return (
            GovernedStateCommitReceiptV1.model_validate(row["payload"])
            if row and isinstance(row.get("payload"), dict)
            else None
        )

    async def load_receipt_for_revision(
        self,
        revision_id: str,
        *,
        product_id: str,
    ) -> GovernedStateCommitReceiptV1 | None:
        """Resolve one exact historical commit without treating it as current authority."""

        async with self.pool.connection() as db:
            rows = await db.query(
                "SELECT payload FROM governed_state_commit_receipt "
                "WHERE product = $product AND revision_id = $revision_id LIMIT 2",
                {
                    "product": parse_record_id(product_id),
                    "revision_id": revision_id,
                },
            )
        result = parse_rows(rows)
        if len(result) > 1:
            raise GovernedStateReplayConflict("one revision resolved to multiple governed commit receipts")
        row = result[0] if result else None
        return (
            GovernedStateCommitReceiptV1.model_validate(row["payload"])
            if row and isinstance(row.get("payload"), dict)
            else None
        )

    async def commit(
        self,
        request: GovernedStateCommitRequestV1,
    ) -> GovernedStateCommitReceiptV1:
        receipt = request.receipt()
        revision = request.revision
        head = GovernedStateHeadV1(
            state_kind=revision.state_kind,
            product_id=revision.product_id,
            state_id=revision.state_id,
            sequence=revision.sequence,
            revision_id=revision.revision_id,
            commit_receipt_id=str(receipt.receipt_id),
            updated_at=request.committed_at,
        )
        async with self.pool.connection() as db:
            existing_receipt = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('governed_state_commit_receipt', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(str(receipt.receipt_id)),
                        "product": parse_record_id(revision.product_id),
                    },
                )
            )
            if existing_receipt:
                payload = existing_receipt.get("payload")
                stored = GovernedStateCommitReceiptV1.model_validate(payload) if isinstance(payload, dict) else None
                if stored == receipt:
                    return stored
                raise GovernedStateReplayConflict(
                    f"stable commit receipt {receipt.receipt_id} contains different material"
                )

            existing_revision = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('governed_state_revision', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(revision.revision_id),
                        "product": parse_record_id(revision.product_id),
                    },
                )
            )
            if existing_revision:
                raise GovernedStateReplayConflict("partial governed-state commit exists without its durable receipt")

            params = {
                "product": parse_record_id(revision.product_id),
                "state_kind": revision.state_kind,
                "state_id": revision.state_id,
                "expected_head": request.expected_head_revision_id,
                "revision_key": _record_key(revision.revision_id),
                "revision_content": {
                    "contract_version": revision.contract,
                    "product": parse_record_id(revision.product_id),
                    "state_kind": revision.state_kind,
                    "state_id": revision.state_id,
                    "sequence": revision.sequence,
                    "stable_id": revision.revision_id,
                    "material_hash": revision.material_hash,
                    "prior_revision_id": revision.prior_revision_id,
                    "approval_subject_ref": revision.approval_subject_ref,
                    "payload_contract": revision.payload_contract,
                    "payload": revision.model_dump(mode="python"),
                    "created_at": request.committed_at,
                },
                "head_key": _record_key(str(head.head_id)),
                "head_content": {
                    "contract_version": head.contract,
                    "product": parse_record_id(head.product_id),
                    "state_kind": head.state_kind,
                    "state_id": head.state_id,
                    "sequence": head.sequence,
                    "revision_id": head.revision_id,
                    "commit_receipt_id": head.commit_receipt_id,
                    "payload": head.model_dump(mode="python"),
                    "updated_at": head.updated_at,
                },
                "receipt_key": _record_key(str(receipt.receipt_id)),
                "receipt_content": {
                    "contract_version": receipt.contract,
                    "product": parse_record_id(receipt.product_id),
                    "state_kind": receipt.state_kind,
                    "state_id": receipt.state_id,
                    "sequence": receipt.sequence,
                    "stable_id": receipt.receipt_id,
                    "material_hash": receipt.receipt_hash,
                    "revision_id": receipt.revision_id,
                    "audit_id": receipt.audit_id,
                    "payload": receipt.model_dump(mode="python"),
                    "created_at": receipt.committed_at,
                },
                "audit_key": _record_key(str(receipt.audit_id)),
                "audit_content": {
                    "contract_version": receipt.contract,
                    "product": parse_record_id(receipt.product_id),
                    "state_kind": receipt.state_kind,
                    "state_id": receipt.state_id,
                    "sequence": receipt.sequence,
                    "stable_id": receipt.audit_id,
                    "revision_id": receipt.revision_id,
                    "commit_receipt_id": receipt.receipt_id,
                    "actor_ref": receipt.actor_ref,
                    "approval_receipt_ref": receipt.approval.receipt_ref,
                    "payload": {"commit_receipt": receipt.model_dump(mode="python")},
                    "created_at": receipt.committed_at,
                },
            }
            sql = """
                BEGIN TRANSACTION;
                LET $current = SELECT VALUE revision_id
                    FROM ONLY type::record('governed_state_head', $head_key)
                    WHERE product = $product AND state_kind = $state_kind AND state_id = $state_id;
                IF $current != $expected_head {
                    THROW 'governed_state_head_conflict';
                };
                CREATE ONLY type::record('governed_state_revision', $revision_key)
                    CONTENT $revision_content;
                CREATE ONLY type::record('governed_state_commit_receipt', $receipt_key)
                    CONTENT $receipt_content;
                CREATE ONLY type::record('governed_state_audit', $audit_key)
                    CONTENT $audit_content;
                IF $current = NONE {
                    CREATE ONLY type::record('governed_state_head', $head_key) CONTENT $head_content;
                } ELSE {
                    UPDATE ONLY type::record('governed_state_head', $head_key) CONTENT $head_content;
                };
                COMMIT TRANSACTION;
            """
            for conflict_attempt in range(3):
                try:
                    raw = await db.query_raw(sql, params)
                    _raise_query_errors(raw)
                    break
                except GovernedStateHeadConflict:
                    raise
                except Exception as exc:
                    message = str(exc).lower()
                    if "governed_state_head_conflict" in message:
                        raise GovernedStateHeadConflict("governed_state_head_conflict") from exc
                    if "transaction" not in message or "conflict" not in message or conflict_attempt == 2:
                        raise
                    await asyncio.sleep(0.005 * (conflict_attempt + 1))
        return receipt


__all__ = [
    "GovernedStateHeadConflict",
    "GovernedStatePersistenceError",
    "GovernedStateReplayConflict",
    "GovernedStateScopeError",
    "SurrealGovernedStateStore",
]
