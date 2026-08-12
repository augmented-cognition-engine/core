"""SurrealDB adapter for Core's domain-neutral immutable-record port."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ace.core.contracts import canonical_hash, canonical_json, stable_id
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordPreconditionFailed,
    ImmutableRecordReferenceV1,
    ImmutableRecordReplayConflict,
    ImmutableRecordScopeError,
    ImmutableRecordV1,
    append_only_receipt_id,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from core.engine.core.db import parse_one, parse_record_id, parse_rows


def _record_key(value: str) -> str:
    _, separator, key = value.partition(":")
    if not separator or not key:
        raise ValueError("immutable storage identities must use a table-prefixed value")
    return key


def _query_errors(result: Any) -> list[str]:
    if isinstance(result, str):
        return [result]
    if isinstance(result, dict) and result.get("error"):
        error = result["error"]
        return [str(error.get("message", error) if isinstance(error, dict) else error)]
    entries = result.get("result", []) if isinstance(result, dict) else result
    errors: list[str] = []
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, str):
                errors.append(item)
            elif isinstance(item, dict) and str(item.get("status", "")).upper() == "ERR":
                errors.append(str(item.get("result") or item.get("detail") or item))
    return errors


def _raise_query_errors(result: Any) -> None:
    errors = _query_errors(result)
    if not errors:
        return
    detail = " | ".join(errors)[:1_000]
    if "immutable_record_replay_conflict" in detail:
        raise ImmutableRecordReplayConflict("immutable_record_replay_conflict")
    if "immutable_record_governed_state_precondition_failed" in detail:
        raise ImmutableRecordPreconditionFailed("immutable_record_governed_state_precondition_failed")
    raise ImmutableRecordPersistenceError("immutable-record transaction failed")


class SurrealImmutableRecordStore:
    """Linearizable append identity, exact replay, and availability-time reads."""

    def __init__(
        self,
        pool: Any,
        *,
        simulate_failure_after_records: int | None = None,
    ) -> None:
        if simulate_failure_after_records is not None and simulate_failure_after_records < 1:
            raise ValueError("simulate_failure_after_records must be positive")
        self.pool = pool
        self.simulate_failure_after_records = simulate_failure_after_records

    async def _classify_possible_winner(
        self,
        *,
        expected: AppendOnlyTransactionReceiptV1,
        original: Exception,
    ) -> AppendOnlyTransactionReceiptV1:
        """Classify one failed attempt only from its full durable receipt identity."""

        try:
            replay = await self._load_receipt_by_id(
                str(expected.receipt_id),
                product_id=expected.product_id,
                record_space=expected.record_space,
            )
        except Exception:
            raise ImmutableRecordPersistenceError("possible append winner failed exact receipt reload") from None
        if replay is None:
            raise original
        if replay == expected:
            return replay
        raise ImmutableRecordReplayConflict("stable transaction identity already binds different material") from None

    async def load_record(
        self,
        storage_id: str,
        *,
        product_id: str,
        record_space: str,
        record_kind: str,
    ) -> ImmutableRecordV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload_json FROM ONLY type::record('immutable_record', $record_key) "
                    "WHERE product = $product AND record_space = $record_space "
                    "AND record_kind = $record_kind LIMIT 1",
                    {
                        "record_key": _record_key(storage_id),
                        "product": parse_record_id(product_id),
                        "record_space": record_space,
                        "record_kind": record_kind,
                    },
                )
            )
        if row is None:
            return None
        payload_json = row.get("payload_json")
        if not isinstance(payload_json, str):
            raise ImmutableRecordPersistenceError("stored immutable record is missing its canonical payload")
        try:
            record = ImmutableRecordV1.model_validate_json(payload_json)
        except (TypeError, ValueError) as exc:
            raise ImmutableRecordPersistenceError("stored immutable record failed exact revalidation") from exc
        if (
            record.storage_id != storage_id
            or record.product_id != product_id
            or record.record_space != record_space
            or record.record_kind != record_kind
        ):
            raise ImmutableRecordScopeError("stored immutable record crossed its exact requested scope")
        return record

    async def _load_receipt_by_id(
        self,
        receipt_id: str,
        *,
        product_id: str,
        record_space: str,
    ) -> AppendOnlyTransactionReceiptV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload_json FROM ONLY "
                    "type::record('append_only_transaction_receipt', $record_key) "
                    "WHERE product = $product AND record_space = $record_space LIMIT 1",
                    {
                        "record_key": _record_key(receipt_id),
                        "product": parse_record_id(product_id),
                        "record_space": record_space,
                    },
                )
            )
        if row is None:
            return None
        payload_json = row.get("payload_json")
        if not isinstance(payload_json, str):
            raise ImmutableRecordPersistenceError("stored append receipt is missing its canonical payload")
        try:
            receipt = AppendOnlyTransactionReceiptV1.model_validate_json(payload_json)
        except (TypeError, ValueError) as exc:
            raise ImmutableRecordPersistenceError("stored append receipt failed exact revalidation") from exc
        if receipt.receipt_id != receipt_id or receipt.product_id != product_id or receipt.record_space != record_space:
            raise ImmutableRecordScopeError("stored append receipt crossed its exact requested scope")
        return receipt

    async def load_transaction_receipt(
        self,
        *,
        product_id: str,
        record_space: str,
        transaction_key: str,
    ) -> AppendOnlyTransactionReceiptV1 | None:
        return await self._load_receipt_by_id(
            append_only_receipt_id(
                product_id=product_id,
                record_space=record_space,
                transaction_key=transaction_key,
            ),
            product_id=product_id,
            record_space=record_space,
        )

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
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT payload_json, available_at, stable_id FROM immutable_record "
                    "WHERE product = $product "
                    "AND record_space = $record_space AND record_kind = $record_kind "
                    "AND available_at <= $available_at ORDER BY available_at, stable_id",
                    {
                        "product": parse_record_id(product_id),
                        "record_space": record_space,
                        "record_kind": record_kind,
                        "available_at": available_at.astimezone(UTC),
                    },
                )
            )
        records: list[ImmutableRecordV1] = []
        for row in rows:
            payload_json = row.get("payload_json")
            if not isinstance(payload_json, str):
                raise ImmutableRecordPersistenceError("historical read encountered a record without canonical payload")
            try:
                record = ImmutableRecordV1.model_validate_json(payload_json)
            except (TypeError, ValueError) as exc:
                raise ImmutableRecordPersistenceError(
                    "historical read encountered an invalid immutable record"
                ) from exc
            if (
                record.product_id != product_id
                or record.record_space != record_space
                or record.record_kind != record_kind
                or record.available_at > available_at.astimezone(UTC)
            ):
                raise ImmutableRecordScopeError(
                    "historical record crossed its exact query scope or availability cutoff"
                )
            records.append(record)
        return tuple(records)

    async def count_as_of(
        self,
        *,
        product_id: str,
        record_space: str,
        record_kind: str,
        available_at: datetime,
    ) -> int:
        if available_at.tzinfo is None or available_at.utcoffset() is None:
            raise ValueError("available_at must include a timezone")
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT count() AS total FROM immutable_record WHERE product = $product "
                    "AND record_space = $record_space AND record_kind = $record_kind "
                    "AND available_at <= $available_at GROUP ALL",
                    {
                        "product": parse_record_id(product_id),
                        "record_space": record_space,
                        "record_kind": record_kind,
                        "available_at": available_at.astimezone(UTC),
                    },
                )
            )
        return int(row.get("total", 0)) if row else 0

    async def scan_product_records(self, *, product_id: str) -> tuple[ImmutableRecordV1, ...]:
        """Return all exact immutable records inside one product fence for AM4."""

        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT payload_json, stable_id FROM immutable_record WHERE product = $product ORDER BY stable_id",
                    {"product": parse_record_id(product_id)},
                )
            )
        records: list[ImmutableRecordV1] = []
        for row in rows:
            payload_json = row.get("payload_json")
            if not isinstance(payload_json, str):
                raise ImmutableRecordPersistenceError("product scan encountered a record without canonical payload")
            try:
                record = ImmutableRecordV1.model_validate_json(payload_json)
            except (TypeError, ValueError) as exc:
                raise ImmutableRecordPersistenceError("product scan encountered an invalid immutable record") from exc
            if record.product_id != product_id:
                raise ImmutableRecordScopeError("product scan crossed its exact product fence")
            records.append(record)
        records.sort(key=lambda item: str(item.storage_id))
        return tuple(records)

    async def erase_records_atomically(
        self,
        *,
        product_id: str,
        expected_records: tuple[ImmutableRecordReferenceV1, ...],
        receipt_request: AppendOnlyTransactionRequestV1,
    ) -> AppendOnlyTransactionReceiptV1:
        """Delete exact content records and append content-free proof in one transaction."""

        try:
            validated = AppendOnlyTransactionRequestV1.model_validate(receipt_request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ImmutableRecordPersistenceError("erasure request failed exact revalidation") from exc
        if validated.product_id != product_id:
            raise ImmutableRecordScopeError("erasure request crossed its exact product scope")
        expected = validated.receipt()
        existing = await self._load_receipt_by_id(
            str(expected.receipt_id), product_id=product_id, record_space=validated.record_space
        )
        if existing is not None:
            if existing == expected:
                return existing
            raise ImmutableRecordReplayConflict("stable erasure transaction identity binds different material")

        delete_ids: set[str] = set()
        for reference in expected_records:
            if reference.product_id != product_id:
                raise ImmutableRecordScopeError("erasure dependency crossed its exact product scope")
            current = await self.load_record(
                reference.storage_id,
                product_id=reference.product_id,
                record_space=reference.record_space,
                record_kind=reference.record_kind,
            )
            if current is None or current.reference() != reference:
                raise ImmutableRecordPreconditionFailed("erasure dependency snapshot is stale")
            delete_ids.add(reference.storage_id)
        if any(str(record.storage_id) in delete_ids for record in validated.records):
            raise ImmutableRecordScopeError("erasure proof cannot reuse a deleted record identity")

        params: dict[str, Any] = {
            "receipt_key": _record_key(str(expected.receipt_id)),
            "receipt_content": {
                "contract_version": expected.contract,
                "product": parse_record_id(expected.product_id),
                "record_space": expected.record_space,
                "transaction_key": expected.transaction_key,
                "transaction_id": expected.transaction_id,
                "stable_id": expected.receipt_id,
                "request_hash": expected.request_hash,
                "material_hash": expected.receipt_hash,
                "record_ids": [reference.storage_id for reference in expected.records],
                "payload": {},
                "payload_json": canonical_json(expected),
                "created_at": expected.committed_at,
            },
        }
        statements = ["BEGIN TRANSACTION;"]
        for index, precondition in enumerate(validated.governed_state_preconditions):
            params[f"head_key_{index}"] = _record_key(
                stable_id(
                    "governed_state_head",
                    {
                        "state_kind": precondition.state_kind,
                        "product_id": precondition.product_id,
                        "state_id": precondition.state_id,
                    },
                )
            )
            params[f"head_product_{index}"] = parse_record_id(precondition.product_id)
            params[f"head_state_kind_{index}"] = precondition.state_kind
            params[f"head_state_id_{index}"] = precondition.state_id
            params[f"head_sequence_{index}"] = precondition.sequence
            params[f"head_revision_id_{index}"] = precondition.revision_id
            params[f"head_commit_receipt_id_{index}"] = precondition.commit_receipt_id
            statements.extend(
                (
                    f"LET $governed_head_{index} = SELECT sequence, revision_id, commit_receipt_id "
                    f"FROM ONLY type::record('governed_state_head', $head_key_{index}) "
                    f"WHERE product = $head_product_{index} "
                    f"AND state_kind = $head_state_kind_{index} AND state_id = $head_state_id_{index};",
                    f"IF $governed_head_{index} = NONE "
                    f"OR $governed_head_{index}.sequence != $head_sequence_{index} "
                    f"OR $governed_head_{index}.revision_id != $head_revision_id_{index} "
                    f"OR $governed_head_{index}.commit_receipt_id != $head_commit_receipt_id_{index} "
                    "{ THROW 'immutable_record_governed_state_precondition_failed'; };",
                )
            )
        for index, reference in enumerate(expected_records):
            params[f"delete_key_{index}"] = _record_key(reference.storage_id)
            params[f"delete_product_{index}"] = parse_record_id(product_id)
            params[f"delete_space_{index}"] = reference.record_space
            params[f"delete_kind_{index}"] = reference.record_kind
            params[f"delete_hash_{index}"] = reference.material_hash
            statements.extend(
                (
                    f"LET $delete_match_{index} = SELECT material_hash FROM ONLY "
                    f"type::record('immutable_record', $delete_key_{index}) "
                    f"WHERE product = $delete_product_{index} AND record_space = $delete_space_{index} "
                    f"AND record_kind = $delete_kind_{index} AND material_hash = $delete_hash_{index};",
                    f"IF $delete_match_{index} = NONE {{ THROW 'immutable_record_erasure_snapshot_stale'; }};",
                    f"DELETE type::record('immutable_record', $delete_key_{index});",
                )
            )
        for index, record in enumerate(validated.records):
            params[f"record_key_{index}"] = _record_key(str(record.storage_id))
            params[f"record_content_{index}"] = {
                "contract_version": record.contract,
                "product": parse_record_id(record.product_id),
                "record_space": record.record_space,
                "record_kind": record.record_kind,
                "record_key": record.record_key,
                "stable_id": record.storage_id,
                "material_hash": record.material_hash,
                "transaction_id": expected.transaction_id,
                "payload_contract": record.payload_contract,
                "as_of": record.as_of,
                "available_at": record.available_at,
                "processing_order": record.processing_order,
                "payload": {},
                "payload_json": canonical_json(record),
                "created_at": expected.committed_at,
            }
            statements.append(
                f"CREATE ONLY type::record('immutable_record', $record_key_{index}) CONTENT $record_content_{index};"
            )
            if self.simulate_failure_after_records == index + 1:
                statements.append("THROW 'immutable_record_simulated_erasure_failure';")
        statements.extend(
            (
                "CREATE ONLY type::record('append_only_transaction_receipt', $receipt_key) CONTENT $receipt_content;",
                "COMMIT TRANSACTION;",
            )
        )
        try:
            async with self.pool.connection() as db:
                raw = await db.query_raw("\n".join(statements), params)
                _raise_query_errors(raw)
        except Exception as exc:
            original = (
                exc
                if isinstance(exc, ImmutableRecordPersistenceError)
                else ImmutableRecordPersistenceError("immutable-record erasure transaction failed")
            )
            return await self._classify_possible_winner(expected=expected, original=original)
        return expected

    async def import_records_atomically(
        self,
        *,
        product_id: str,
        transaction_key: str,
        records: tuple[ImmutableRecordV1, ...],
        submitted_at: datetime,
        governed_state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> str:
        """Atomically restore exact records across original AM1-AM4 spaces."""

        if submitted_at.tzinfo is None or submitted_at.utcoffset() is None or not records:
            raise ImmutableRecordPersistenceError("administrative import requires time and records")
        validated = tuple(ImmutableRecordV1.model_validate(item.model_dump(mode="python")) for item in records)
        if any(item.product_id != product_id for item in validated):
            raise ImmutableRecordScopeError("administrative import crossed its exact product scope")
        transaction_id = stable_id(
            "agent_memory_admin_import", {"product_id": product_id, "transaction_key": transaction_key}
        )
        request_hash = f"sha256:{canonical_hash(tuple((item.storage_id, item.material_hash) for item in validated))}"
        receipt_ref = stable_id(
            "agent_memory_admin_import_receipt",
            {"transaction_id": transaction_id, "request_hash": request_hash},
        )

        async def classify_existing() -> bool:
            matched = 0
            for record in validated:
                prior = await self.load_record(
                    str(record.storage_id),
                    product_id=record.product_id,
                    record_space=record.record_space,
                    record_kind=record.record_kind,
                )
                if prior is None:
                    continue
                if prior != record:
                    raise ImmutableRecordReplayConflict("administrative import collided with existing material")
                matched += 1
            if matched not in (0, len(validated)):
                raise ImmutableRecordPersistenceError("administrative import found an impossible partial transaction")
            return matched == len(validated)

        if await classify_existing():
            return receipt_ref

        params: dict[str, Any] = {}
        statements = ["BEGIN TRANSACTION;"]
        for index, precondition in enumerate(governed_state_preconditions):
            params[f"head_key_{index}"] = _record_key(
                stable_id(
                    "governed_state_head",
                    {
                        "state_kind": precondition.state_kind,
                        "product_id": precondition.product_id,
                        "state_id": precondition.state_id,
                    },
                )
            )
            params[f"head_product_{index}"] = parse_record_id(precondition.product_id)
            params[f"head_state_kind_{index}"] = precondition.state_kind
            params[f"head_state_id_{index}"] = precondition.state_id
            params[f"head_sequence_{index}"] = precondition.sequence
            params[f"head_revision_id_{index}"] = precondition.revision_id
            params[f"head_commit_receipt_id_{index}"] = precondition.commit_receipt_id
            statements.extend(
                (
                    f"LET $governed_head_{index} = SELECT sequence, revision_id, commit_receipt_id "
                    f"FROM ONLY type::record('governed_state_head', $head_key_{index}) "
                    f"WHERE product = $head_product_{index} "
                    f"AND state_kind = $head_state_kind_{index} AND state_id = $head_state_id_{index};",
                    f"IF $governed_head_{index} = NONE "
                    f"OR $governed_head_{index}.sequence != $head_sequence_{index} "
                    f"OR $governed_head_{index}.revision_id != $head_revision_id_{index} "
                    f"OR $governed_head_{index}.commit_receipt_id != $head_commit_receipt_id_{index} "
                    "{ THROW 'immutable_record_governed_state_precondition_failed'; };",
                )
            )
        for index, record in enumerate(validated):
            params[f"record_key_{index}"] = _record_key(str(record.storage_id))
            params[f"record_content_{index}"] = {
                "contract_version": record.contract,
                "product": parse_record_id(record.product_id),
                "record_space": record.record_space,
                "record_kind": record.record_kind,
                "record_key": record.record_key,
                "stable_id": record.storage_id,
                "material_hash": record.material_hash,
                "transaction_id": transaction_id,
                "payload_contract": record.payload_contract,
                "as_of": record.as_of,
                "available_at": record.available_at,
                "processing_order": record.processing_order,
                "payload": {},
                "payload_json": canonical_json(record),
                "created_at": submitted_at.astimezone(UTC),
            }
            statements.append(
                f"CREATE ONLY type::record('immutable_record', $record_key_{index}) CONTENT $record_content_{index};"
            )
            if self.simulate_failure_after_records == index + 1:
                statements.append("THROW 'immutable_record_simulated_import_failure';")
        statements.extend(("COMMIT TRANSACTION;",))
        try:
            async with self.pool.connection() as db:
                raw = await db.query_raw("\n".join(statements), params)
                _raise_query_errors(raw)
        except Exception as exc:
            if await classify_existing():
                return receipt_ref
            if isinstance(exc, ImmutableRecordPersistenceError):
                raise
            raise ImmutableRecordPersistenceError("administrative import transaction failed") from exc
        return receipt_ref

    async def append(
        self,
        request: AppendOnlyTransactionRequestV1,
    ) -> AppendOnlyTransactionReceiptV1:
        try:
            validated = AppendOnlyTransactionRequestV1.model_validate(request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ImmutableRecordPersistenceError("append request failed exact revalidation") from exc
        expected = validated.receipt()
        existing = await self._load_receipt_by_id(
            str(expected.receipt_id),
            product_id=validated.product_id,
            record_space=validated.record_space,
        )
        if existing is not None:
            if existing == expected:
                return existing
            raise ImmutableRecordReplayConflict("stable transaction identity already binds different material")

        for record in validated.records:
            prior = await self.load_record(
                str(record.storage_id),
                product_id=record.product_id,
                record_space=record.record_space,
                record_kind=record.record_kind,
            )
            if prior is not None:
                return await self._classify_possible_winner(
                    expected=expected,
                    original=ImmutableRecordReplayConflict(
                        "immutable record already exists without the exact transaction receipt"
                    ),
                )

        params: dict[str, Any] = {
            "receipt_key": _record_key(str(expected.receipt_id)),
            "receipt_content": {
                "contract_version": expected.contract,
                "product": parse_record_id(expected.product_id),
                "record_space": expected.record_space,
                "transaction_key": expected.transaction_key,
                "transaction_id": expected.transaction_id,
                "stable_id": expected.receipt_id,
                "request_hash": expected.request_hash,
                "material_hash": expected.receipt_hash,
                "record_ids": [reference.storage_id for reference in expected.records],
                "payload": {},
                "payload_json": canonical_json(expected),
                "created_at": expected.committed_at,
            },
        }
        statements = ["BEGIN TRANSACTION;"]
        for index, precondition in enumerate(validated.governed_state_preconditions):
            params[f"head_key_{index}"] = _record_key(
                stable_id(
                    "governed_state_head",
                    {
                        "state_kind": precondition.state_kind,
                        "product_id": precondition.product_id,
                        "state_id": precondition.state_id,
                    },
                )
            )
            params[f"head_product_{index}"] = parse_record_id(precondition.product_id)
            params[f"head_state_kind_{index}"] = precondition.state_kind
            params[f"head_state_id_{index}"] = precondition.state_id
            params[f"head_sequence_{index}"] = precondition.sequence
            params[f"head_revision_id_{index}"] = precondition.revision_id
            params[f"head_commit_receipt_id_{index}"] = precondition.commit_receipt_id
            statements.extend(
                (
                    f"LET $governed_head_{index} = SELECT sequence, revision_id, commit_receipt_id "
                    f"FROM ONLY type::record('governed_state_head', $head_key_{index}) "
                    f"WHERE product = $head_product_{index} "
                    f"AND state_kind = $head_state_kind_{index} AND state_id = $head_state_id_{index};",
                    f"IF $governed_head_{index} = NONE "
                    f"OR $governed_head_{index}.sequence != $head_sequence_{index} "
                    f"OR $governed_head_{index}.revision_id != $head_revision_id_{index} "
                    f"OR $governed_head_{index}.commit_receipt_id != $head_commit_receipt_id_{index} "
                    "{ THROW 'immutable_record_governed_state_precondition_failed'; };",
                )
            )
        for index, record in enumerate(validated.records):
            params[f"record_key_{index}"] = _record_key(str(record.storage_id))
            params[f"record_content_{index}"] = {
                "contract_version": record.contract,
                "product": parse_record_id(record.product_id),
                "record_space": record.record_space,
                "record_kind": record.record_kind,
                "record_key": record.record_key,
                "stable_id": record.storage_id,
                "material_hash": record.material_hash,
                "transaction_id": expected.transaction_id,
                "payload_contract": record.payload_contract,
                "as_of": record.as_of,
                "available_at": record.available_at,
                "processing_order": record.processing_order,
                "payload": {},
                "payload_json": canonical_json(record),
                "created_at": expected.committed_at,
            }
            statements.append(
                f"CREATE ONLY type::record('immutable_record', $record_key_{index}) CONTENT $record_content_{index};"
            )
            if self.simulate_failure_after_records == index + 1:
                statements.append("THROW 'immutable_record_simulated_failure';")
        statements.extend(
            (
                "CREATE ONLY type::record('append_only_transaction_receipt', $receipt_key) CONTENT $receipt_content;",
                "COMMIT TRANSACTION;",
            )
        )

        try:
            async with self.pool.connection() as db:
                raw = await db.query_raw("\n".join(statements), params)
                _raise_query_errors(raw)
        except Exception as exc:
            original = (
                exc
                if isinstance(exc, ImmutableRecordPersistenceError)
                else ImmutableRecordPersistenceError("immutable-record transaction failed")
            )
            return await self._classify_possible_winner(
                expected=expected,
                original=original,
            )
        return expected


__all__ = ["SurrealImmutableRecordStore"]
