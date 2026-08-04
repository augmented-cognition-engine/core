"""Deterministic, provider-free TP2 bounded batch ingestion service."""

from __future__ import annotations

import asyncio
import hashlib
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import ValidationError

from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.ingestion_contracts import (
    RECORD_MODEL_BY_KIND,
    BatchIngestionReceiptV1,
    BoundedBatchManifestV1,
    EventParticipantV1,
    EvidenceRelationV1,
    GroundedIngestionItemV1,
    GroundedRecordCountsV1,
    GroundedRecordKind,
    GroundedSemanticRecordV1,
    IngestionDisposition,
    IngestionDispositionCountsV1,
    IngestionItemReceiptV1,
    RawAliasV1,
    RecordIngestionResultV1,
    SourceClaimV1,
    build_batch_receipt_id,
    build_item_receipt_id,
)
from core.engine.grounded_state.operations import StateEngineOperationsService
from core.engine.grounded_state.persistence import (
    GroundedStateProductScopeError,
    GroundedStateStore,
)

_INGEST_LOCK = asyncio.Lock()
_FORBIDDEN_ADAPTER_FIELDS = frozenset({"product", "product_id", "record_id", "idempotency_key"})
_KIND_ORDER = {
    GroundedRecordKind.SOURCE: 0,
    GroundedRecordKind.ENTITY: 1,
    GroundedRecordKind.CLAIM: 2,
    GroundedRecordKind.EVENT: 3,
    GroundedRecordKind.ALIAS: 4,
    GroundedRecordKind.EVENT_PARTICIPANT: 5,
    GroundedRecordKind.RELATION: 6,
    GroundedRecordKind.EXTRACTION_FAILURE: 7,
}


class _TransactionConnection:
    """Bind ordinary store queries to one SurrealDB client transaction."""

    def __init__(self, connection, transaction_id) -> None:
        self._connection = connection
        self._transaction_id = transaction_id

    async def query(self, query: str, params: dict[str, Any] | None = None):
        return await self._connection.query(query, params or {}, txn_id=self._transaction_id)


@asynccontextmanager
async def _item_transaction(connection):
    """Commit semantic children and their green item receipt as one unit."""
    transaction_id = await connection.begin()
    transaction = _TransactionConnection(connection, transaction_id)
    try:
        yield transaction
        await connection.commit(transaction_id)
    except BaseException:
        try:
            await connection.cancel(transaction_id)
        except Exception:
            # Preserve the original failure. A dead connection/database cannot
            # acknowledge cancellation, but an uncommitted server transaction
            # still cannot produce a green receipt.
            pass
        raise


def _reason(exc: Exception) -> str:
    return " ".join(str(exc).split())[:1_000] or type(exc).__name__


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _derive_content_hash(kind: GroundedRecordKind, data: dict[str, Any]) -> str | None:
    if kind is GroundedRecordKind.SOURCE:
        content = data.get("content")
        return _sha256(content) if isinstance(content, str) else None
    if kind is GroundedRecordKind.ENTITY:
        return canonical_hash(
            {
                "canonical_name": data.get("canonical_name"),
                "entity_type": data.get("entity_type"),
                "attributes": data.get("attributes") or {},
            }
        )
    if kind is GroundedRecordKind.ALIAS:
        value = data.get("raw_surface_form")
        return _sha256(value) if isinstance(value, str) else None
    if kind is GroundedRecordKind.CLAIM:
        value = data.get("claim_text")
        return _sha256(value) if isinstance(value, str) else None
    if kind is GroundedRecordKind.EVENT:
        value = data.get("description")
        return _sha256(value) if isinstance(value, str) else None
    if kind is GroundedRecordKind.EVENT_PARTICIPANT:
        return canonical_hash(
            {
                "event_id": data.get("event_id"),
                "entity_id": data.get("entity_id"),
                "role": data.get("role"),
                "raw_surface_form": data.get("raw_surface_form"),
            }
        )
    if kind is GroundedRecordKind.RELATION:
        return canonical_hash(
            {
                "relation": data.get("relation"),
                "subject_id": data.get("subject_id"),
                "object_id": data.get("object_id"),
                "basis": data.get("basis"),
            }
        )
    if kind is GroundedRecordKind.EXTRACTION_FAILURE:
        value = data.get("input_hash")
        return value if isinstance(value, str) else None
    return None


def _resolve_local_ref(value: Any, local_refs: dict[str, str], *, name: str) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if value in local_refs:
        return local_refs[value]
    if value.startswith("local:"):
        raise ValueError(f"{name} references unknown item-local identity {value}")
    return value


@dataclass(frozen=True)
class _Proposal:
    ordinal: int
    kind: GroundedRecordKind
    raw: dict[str, Any]


@dataclass(frozen=True)
class _BuiltRecord:
    ordinal: int
    input_hash: str
    record: GroundedSemanticRecordV1


def _proposal_kind(raw: dict[str, Any]) -> GroundedRecordKind:
    value = raw.get("kind", raw.get("record_kind"))
    return GroundedRecordKind(value)


def _prepare_data(
    proposal: _Proposal,
    *,
    product_id: str,
    local_refs: dict[str, str],
) -> dict[str, Any]:
    forbidden = _FORBIDDEN_ADAPTER_FIELDS & set(proposal.raw)
    if forbidden:
        raise ValueError(f"adapter output cannot set Core-owned fields: {sorted(forbidden)}")
    data = dict(proposal.raw)
    data.pop("kind", None)
    data.pop("record_kind", None)
    data["product_id"] = product_id

    if "source_id" in data and "source_external_id" not in data:
        data["source_external_id"] = data.pop("source_id")

    kind = proposal.kind
    if kind is GroundedRecordKind.ALIAS:
        value = data.pop("entity_local_id", data.get("entity_id"))
        data["entity_id"] = _resolve_local_ref(value, local_refs, name="entity_id")
    elif kind is GroundedRecordKind.CLAIM:
        values = data.pop("entity_local_ids", data.get("entity_ids", ()))
        data["entity_ids"] = tuple(_resolve_local_ref(value, local_refs, name="entity_ids") for value in values or ())
    elif kind is GroundedRecordKind.EVENT_PARTICIPANT:
        event = data.pop("event_local_id", data.get("event_id"))
        entity = data.pop("entity_local_id", data.get("entity_id"))
        data["event_id"] = _resolve_local_ref(event, local_refs, name="event_id")
        data["entity_id"] = _resolve_local_ref(entity, local_refs, name="entity_id")
    elif kind is GroundedRecordKind.RELATION:
        subject = data.pop("subject_local_id", data.get("subject_id"))
        object_ = data.pop("object_local_id", data.get("object_id"))
        data["subject_id"] = _resolve_local_ref(subject, local_refs, name="subject_id")
        data["object_id"] = _resolve_local_ref(object_, local_refs, name="object_id")

    if "supersedes_local_ids" in data:
        supplied = list(data.pop("supersedes_local_ids") or [])
        supplied.extend(data.get("supersedes") or [])
        data["supersedes"] = tuple(_resolve_local_ref(value, local_refs, name="supersedes") for value in supplied)
    derived_hash = _derive_content_hash(kind, data)
    if data.get("content_hash") is None and derived_hash is not None:
        data["content_hash"] = derived_hash
    return data


def _build_records(
    item: GroundedIngestionItemV1,
    *,
    product_id: str,
) -> tuple[list[_BuiltRecord], list[RecordIngestionResultV1]]:
    proposals: list[_Proposal] = []
    rejected: list[RecordIngestionResultV1] = []
    for ordinal, raw in enumerate(item.records):
        input_hash = canonical_hash(raw)
        try:
            kind = _proposal_kind(raw)
        except (TypeError, ValueError) as exc:
            rejected.append(
                RecordIngestionResultV1(
                    ordinal=ordinal,
                    disposition=IngestionDisposition.REJECTED,
                    input_hash=input_hash,
                    reasons=(f"unsupported or missing record kind: {_reason(exc)}",),
                )
            )
            continue
        proposals.append(_Proposal(ordinal=ordinal, kind=kind, raw=raw))

    proposals.sort(
        key=lambda value: (
            _KIND_ORDER[value.kind],
            str(value.raw.get("source_external_id") or value.raw.get("source_id") or ""),
            str(value.raw.get("local_id") or ""),
            str(value.raw.get("source_version") or ""),
            canonical_hash(value.raw),
        )
    )
    local_refs: dict[str, str] = {}
    records: list[_BuiltRecord] = []
    for proposal in proposals:
        input_hash = canonical_hash(proposal.raw)
        try:
            data = _prepare_data(proposal, product_id=product_id, local_refs=local_refs)
            model = RECORD_MODEL_BY_KIND[proposal.kind]
            record = model.model_validate(data)
            local_id = record.local_id
            prior = local_refs.get(local_id)
            if prior is not None and prior != record.record_id:
                raise ValueError(f"item-local identity {local_id} maps to more than one Core record")
            local_refs[local_id] = str(record.record_id)
            if not local_id.startswith("local:"):
                local_refs[f"local:{local_id}"] = str(record.record_id)
            records.append(_BuiltRecord(ordinal=proposal.ordinal, input_hash=input_hash, record=record))
        except (TypeError, ValueError, ValidationError) as exc:
            rejected.append(
                RecordIngestionResultV1(
                    ordinal=proposal.ordinal,
                    kind=proposal.kind,
                    disposition=IngestionDisposition.REJECTED,
                    input_hash=input_hash,
                    reasons=(_reason(exc),),
                )
            )
    return records, rejected


async def _references_for(record: GroundedSemanticRecordV1) -> tuple[str, ...]:
    refs: list[str] = list(record.supersedes)
    if isinstance(record, RawAliasV1):
        refs.append(record.entity_id)
    elif isinstance(record, SourceClaimV1):
        refs.extend(record.entity_ids)
    elif isinstance(record, EventParticipantV1):
        refs.extend((record.event_id, record.entity_id))
    elif isinstance(record, EvidenceRelationV1):
        refs.extend((record.subject_id, record.object_id))
    return tuple(sorted(set(refs)))


def _item_disposition(results: list[RecordIngestionResultV1]) -> IngestionDisposition:
    present = {result.disposition for result in results}
    for value in (
        IngestionDisposition.FAILED,
        IngestionDisposition.REJECTED,
        IngestionDisposition.SUPERSEDING,
        IngestionDisposition.ACCEPTED,
        IngestionDisposition.DUPLICATE,
    ):
        if value in present:
            return value
    raise ValueError("an item receipt requires at least one record result")


class GroundedStateIngestionService:
    """Core-owned deterministic ingestion; this class has no model-provider dependency."""

    primary_model_calls = 0

    def __init__(self, pool) -> None:
        self.store = GroundedStateStore(pool)
        self.pool = pool
        self.operations = StateEngineOperationsService(pool)

    async def _validate_references(
        self,
        records: list[_BuiltRecord],
        rejected: list[RecordIngestionResultV1],
        *,
        product_id: str,
        item: GroundedIngestionItemV1,
    ) -> list[_BuiltRecord]:
        del item
        known = {str(built.record.record_id) for built in records}
        referenced = {ref for built in records for ref in await _references_for(built.record) if ref not in known}
        existing_references = await self.store.existing_record_ids(
            referenced,
            product_id=product_id,
        )
        valid: list[_BuiltRecord] = []
        for built in records:
            record = built.record
            try:
                record_prefix = str(record.record_id).partition(":")[0] + ":"
                if any(not ref.startswith(record_prefix) for ref in record.supersedes):
                    raise ValueError("supersession lineage must remain within one grounded record kind")
                refs = await _references_for(record)
                missing = [ref for ref in refs if ref not in known and ref not in existing_references]
                if missing:
                    raise GroundedStateProductScopeError(
                        f"referenced identities are absent from product scope: {sorted(missing)}"
                    )
                valid.append(built)
            except (GroundedStateProductScopeError, ValueError) as exc:
                rejected.append(
                    RecordIngestionResultV1(
                        ordinal=built.ordinal,
                        kind=record.record_kind,
                        disposition=IngestionDisposition.REJECTED,
                        input_hash=built.input_hash,
                        reasons=(_reason(exc),),
                    )
                )
        return valid

    async def _persist_item(
        self,
        manifest: BoundedBatchManifestV1,
        item: GroundedIngestionItemV1,
        *,
        item_ordinal: int,
    ) -> IngestionItemReceiptV1:
        manifest_id = manifest.manifest_id()
        input_hash = canonical_hash(item.model_dump(mode="json"))
        receipt_id = build_item_receipt_id(
            manifest_id=manifest_id,
            item_ordinal=item_ordinal,
            input_hash=input_hash,
        )
        replay = await self.store.load_item_receipt(receipt_id, product_id=manifest.product_id)
        if replay is not None:
            return replay

        records, results = _build_records(item, product_id=manifest.product_id)
        records = await self._validate_references(
            records,
            results,
            product_id=manifest.product_id,
            item=item,
        )
        records.sort(
            key=lambda built: (
                _KIND_ORDER[built.record.record_kind],
                built.record.source_external_id,
                built.record.local_id,
                built.record.source_version,
                str(built.record.record_id),
            )
        )

        if results:
            rejected_ordinals = {result.ordinal for result in results}
            for built in records:
                if built.ordinal not in rejected_ordinals:
                    results.append(
                        RecordIngestionResultV1(
                            ordinal=built.ordinal,
                            kind=built.record.record_kind,
                            disposition=IngestionDisposition.REJECTED,
                            input_hash=built.input_hash,
                            reasons=("item rejected atomically because another child record was invalid",),
                        )
                    )
            receipt = IngestionItemReceiptV1(
                receipt_id=receipt_id,
                manifest_id=manifest_id,
                product_id=manifest.product_id,
                item_key=item.item_key,
                item_ordinal=item_ordinal,
                input_hash=input_hash,
                disposition=IngestionDisposition.REJECTED,
                record_results=tuple(sorted(results, key=lambda value: value.ordinal)),
            )
            async with self.pool.connection() as db:
                await self.store.create_item_receipt(db, receipt)
            return receipt

        successful_results: list[RecordIngestionResultV1] = []
        lineage_ids: list[str] = []
        try:
            async with self.pool.connection() as connection:
                async with _item_transaction(connection) as db:
                    item_records = [built.record for built in records]
                    preloaded_rows = await self.store.preload_record_rows(item_records, db=db)
                    predecessor_sets, existing_lineage_coordinates = await self.store.lineage_predecessors_for(
                        item_records,
                        db=db,
                    )
                    for built in records:
                        record = built.record
                        predecessors = predecessor_sets.get(str(record.record_id), ())
                        supersedes = tuple(sorted(set(record.supersedes) | set(predecessors)))
                        if supersedes != record.supersedes:
                            record = type(record).model_validate(
                                {**record.model_dump(mode="python"), "supersedes": supersedes}
                            )
                        created = await self.store.create_record(
                            db,
                            record,
                            preloaded_row=preloaded_rows.get(str(record.record_id)),
                            preflight_complete=True,
                        )
                        if created and record.supersedes:
                            disposition = IngestionDisposition.SUPERSEDING
                        elif created:
                            disposition = IngestionDisposition.ACCEPTED
                        else:
                            disposition = IngestionDisposition.DUPLICATE
                        if record.supersedes or str(record.record_id) in existing_lineage_coordinates:
                            lineage_ids.extend(await self.store.create_lineage_edges(db, record))
                        successful_results.append(
                            RecordIngestionResultV1(
                                ordinal=built.ordinal,
                                kind=record.record_kind,
                                disposition=disposition,
                                input_hash=built.input_hash,
                                record_id=record.record_id,
                            )
                        )
                    all_results = sorted([*results, *successful_results], key=lambda value: value.ordinal)
                    receipt = IngestionItemReceiptV1(
                        receipt_id=receipt_id,
                        manifest_id=manifest_id,
                        product_id=manifest.product_id,
                        item_key=item.item_key,
                        item_ordinal=item_ordinal,
                        input_hash=input_hash,
                        disposition=_item_disposition(all_results),
                        record_results=tuple(all_results),
                        lineage_ids=tuple(lineage_ids),
                    )
                    await self.store.create_item_receipt(db, receipt)
                return receipt
        except Exception as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            # The green receipt and every semantic child shared one transaction,
            # so no earlier in-memory "accepted" result may survive an aborted
            # or ambiguously acknowledged commit.
            failed = [
                RecordIngestionResultV1(
                    ordinal=built.ordinal,
                    kind=built.record.record_kind,
                    disposition=IngestionDisposition.FAILED,
                    input_hash=built.input_hash,
                    reasons=(_reason(exc),),
                )
                for built in records
            ]
            all_results = sorted(failed, key=lambda value: value.ordinal)
            receipt = IngestionItemReceiptV1(
                receipt_id=receipt_id,
                manifest_id=manifest_id,
                product_id=manifest.product_id,
                item_key=item.item_key,
                item_ordinal=item_ordinal,
                input_hash=input_hash,
                disposition=_item_disposition(all_results),
                record_results=tuple(all_results),
                lineage_ids=(),
            )
            async with self.pool.connection() as db:
                await self.store.create_item_receipt(db, receipt)
            return receipt

    async def _rejected_item_receipt(
        self,
        manifest: BoundedBatchManifestV1,
        raw: dict[str, Any],
        *,
        item_ordinal: int,
        error: Exception,
    ) -> IngestionItemReceiptV1:
        input_hash = canonical_hash(raw)
        manifest_id = manifest.manifest_id()
        receipt_id = build_item_receipt_id(
            manifest_id=manifest_id,
            item_ordinal=item_ordinal,
            input_hash=input_hash,
        )
        replay = await self.store.load_item_receipt(receipt_id, product_id=manifest.product_id)
        if replay is not None:
            return replay
        item_key = str(raw.get("item_key") or f"invalid-{input_hash[:12]}")[:240]
        result = RecordIngestionResultV1(
            ordinal=0,
            disposition=IngestionDisposition.REJECTED,
            input_hash=input_hash,
            reasons=(_reason(error),),
        )
        receipt = IngestionItemReceiptV1(
            receipt_id=receipt_id,
            manifest_id=manifest_id,
            product_id=manifest.product_id,
            item_key=item_key,
            item_ordinal=item_ordinal,
            input_hash=input_hash,
            disposition=IngestionDisposition.REJECTED,
            record_results=(result,),
        )
        async with self.pool.connection() as db:
            await self.store.create_item_receipt(db, receipt)
        return receipt

    async def ingest(
        self,
        manifest: BoundedBatchManifestV1 | Mapping[str, Any],
    ) -> BatchIngestionReceiptV1:
        """Ingest a bounded manifest and return its immutable reconciliation receipt."""
        validated = (
            manifest
            if isinstance(manifest, BoundedBatchManifestV1)
            else BoundedBatchManifestV1.model_validate(manifest)
        )
        await self.operations.assert_active(product_id=validated.product_id)
        receipt_id = build_batch_receipt_id(manifest_id=validated.manifest_id())
        existing = await self.store.load_batch_receipt(receipt_id, product_id=validated.product_id)
        if existing is not None:
            return existing

        async with _INGEST_LOCK:
            existing = await self.store.load_batch_receipt(receipt_id, product_id=validated.product_id)
            if existing is not None:
                return existing
            item_receipts: list[IngestionItemReceiptV1] = []
            for chunk_start in range(0, len(validated.items), validated.chunk_size):
                chunk = validated.items[chunk_start : chunk_start + validated.chunk_size]
                for offset, raw_item in enumerate(chunk):
                    ordinal = chunk_start + offset
                    try:
                        item = GroundedIngestionItemV1.model_validate(raw_item)
                    except (TypeError, ValueError, ValidationError) as exc:
                        receipt = await self._rejected_item_receipt(
                            validated,
                            raw_item,
                            item_ordinal=ordinal,
                            error=exc,
                        )
                    else:
                        receipt = await self._persist_item(validated, item, item_ordinal=ordinal)
                    item_receipts.append(receipt)

            item_counter = Counter(receipt.disposition for receipt in item_receipts)
            record_results = [result for receipt in item_receipts for result in receipt.record_results]
            record_counter = Counter(result.disposition for result in record_results)
            persisted_results = [
                result
                for result in record_results
                if result.disposition in {IngestionDisposition.ACCEPTED, IngestionDisposition.SUPERSEDING}
            ]
            kind_counter = Counter(result.kind for result in persisted_results)
            lineage_ids = tuple(sorted({lineage_id for receipt in item_receipts for lineage_id in receipt.lineage_ids}))
            receipt = BatchIngestionReceiptV1(
                receipt_id=receipt_id,
                manifest_id=validated.manifest_id(),
                manifest_hash=validated.manifest_hash(),
                product_id=validated.product_id,
                adapter_id=validated.adapter_id,
                adapter_version=validated.adapter_version,
                extraction_run_id=validated.extraction_run_id,
                submitted_at=validated.submitted_at,
                item_counts=IngestionDispositionCountsV1(
                    inputs=len(item_receipts),
                    accepted=item_counter[IngestionDisposition.ACCEPTED],
                    duplicate=item_counter[IngestionDisposition.DUPLICATE],
                    superseding=item_counter[IngestionDisposition.SUPERSEDING],
                    rejected=item_counter[IngestionDisposition.REJECTED],
                    failed=item_counter[IngestionDisposition.FAILED],
                    persisted=(
                        item_counter[IngestionDisposition.ACCEPTED] + item_counter[IngestionDisposition.SUPERSEDING]
                    ),
                ),
                record_counts=IngestionDispositionCountsV1(
                    inputs=len(record_results),
                    accepted=record_counter[IngestionDisposition.ACCEPTED],
                    duplicate=record_counter[IngestionDisposition.DUPLICATE],
                    superseding=record_counter[IngestionDisposition.SUPERSEDING],
                    rejected=record_counter[IngestionDisposition.REJECTED],
                    failed=record_counter[IngestionDisposition.FAILED],
                    persisted=len(persisted_results),
                ),
                persisted_by_kind=GroundedRecordCountsV1(
                    sources=kind_counter[GroundedRecordKind.SOURCE],
                    entities=kind_counter[GroundedRecordKind.ENTITY],
                    aliases=kind_counter[GroundedRecordKind.ALIAS],
                    claims=kind_counter[GroundedRecordKind.CLAIM],
                    events=kind_counter[GroundedRecordKind.EVENT],
                    event_participants=kind_counter[GroundedRecordKind.EVENT_PARTICIPANT],
                    relations=kind_counter[GroundedRecordKind.RELATION],
                    extraction_failures=kind_counter[GroundedRecordKind.EXTRACTION_FAILURE],
                ),
                item_receipt_ids=tuple(receipt.receipt_id for receipt in item_receipts),
                stable_record_ids=tuple(
                    str(result.record_id) for result in record_results if result.record_id is not None
                ),
                lineage_ids=lineage_ids,
                lineage_edges_persisted=len(lineage_ids),
            )
            return await self.store.create_batch_receipt(receipt)


async def ingest_grounded_state_batch(
    manifest: BoundedBatchManifestV1 | Mapping[str, Any],
    *,
    pool=None,
) -> BatchIngestionReceiptV1:
    """Convenience internal/Core API; intentionally not registered as a public MCP tool."""
    if pool is None:
        from core.engine.core.db import pool as pool
    return await GroundedStateIngestionService(pool).ingest(manifest)
