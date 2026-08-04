"""Product-scoped append-only persistence for TP2 grounded-state records."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any, TypeVar

from pydantic import TypeAdapter

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.ingestion_contracts import (
    BatchIngestionReceiptV1,
    CanonicalEntityV1,
    EventParticipantV1,
    EvidenceRelationV1,
    ExtractionFailureV1,
    GroundedEventV1,
    GroundedRecordKind,
    GroundedSemanticRecordV1,
    IngestionItemReceiptV1,
    RawAliasV1,
    SourceClaimV1,
    SourceRecordV1,
    SupersessionLineageV1,
)

TRecord = TypeVar("TRecord", bound=GroundedSemanticRecordV1)

TABLE_BY_KIND: dict[GroundedRecordKind, str] = {
    GroundedRecordKind.SOURCE: "grounded_source",
    GroundedRecordKind.ENTITY: "grounded_entity",
    GroundedRecordKind.ALIAS: "grounded_alias",
    GroundedRecordKind.CLAIM: "grounded_claim",
    GroundedRecordKind.EVENT: "grounded_event",
    GroundedRecordKind.EVENT_PARTICIPANT: "grounded_event_participant",
    GroundedRecordKind.RELATION: "grounded_evidence_relation",
    GroundedRecordKind.EXTRACTION_FAILURE: "grounded_extraction_failure",
}

MODEL_BY_KIND: dict[GroundedRecordKind, type[GroundedSemanticRecordV1]] = {
    GroundedRecordKind.SOURCE: SourceRecordV1,
    GroundedRecordKind.ENTITY: CanonicalEntityV1,
    GroundedRecordKind.ALIAS: RawAliasV1,
    GroundedRecordKind.CLAIM: SourceClaimV1,
    GroundedRecordKind.EVENT: GroundedEventV1,
    GroundedRecordKind.EVENT_PARTICIPANT: EventParticipantV1,
    GroundedRecordKind.RELATION: EvidenceRelationV1,
    GroundedRecordKind.EXTRACTION_FAILURE: ExtractionFailureV1,
}


class GroundedStatePersistenceError(RuntimeError):
    """A grounded-state write failed and must not be presented as accepted."""


class GroundedStateReplayConflict(GroundedStatePersistenceError):
    """A stable coordinate already contains different immutable material."""


class GroundedStateProductScopeError(GroundedStatePersistenceError):
    """A referenced record is absent from the caller's product scope."""


async def _query_or_raise(db, query: str, params: dict[str, Any] | None = None):
    result = await db.query(query, params or {})
    if isinstance(result, str):
        raise GroundedStatePersistenceError(f"grounded-state persistence failed: {result[:500]}")
    return result


def _record_key(record_id: str) -> str:
    table, separator, key = record_id.partition(":")
    if not separator or not table or not key:
        raise ValueError("grounded-state identity must use table:key form")
    return key


def _version_key(value: str) -> tuple[tuple[int, int | str], ...]:
    """Natural, deterministic ordering for opaque-but-usually-versioned source labels."""
    return tuple((0, int(part)) if part.isdigit() else (1, part.lower()) for part in re.split(r"(\d+)", value))


def _semantic_replay_hash(value: GroundedSemanticRecordV1) -> str:
    """Compare immutable semantics while allowing duplicate delivery timestamps."""
    return canonical_hash(
        value.model_dump(
            mode="json",
            exclude={"record_id", "idempotency_key", "ingested_at", "extracted_at", "supersedes"},
        )
    )


def _semantic_content(record: GroundedSemanticRecordV1) -> dict[str, Any]:
    content: dict[str, Any] = {
        "contract_version": record.contract_version,
        "product": parse_record_id(record.product_id),
        "stable_id": record.record_id,
        "record_kind": record.record_kind.value,
        "external_id": record.external_id,
        "source_external_id": record.source_external_id,
        "source_version": record.source_version,
        "local_id": record.local_id,
        "content_hash": record.content_hash,
        "idempotency_key": record.idempotency_key,
        "supersedes": list(record.supersedes),
        "degraded_reasons": list(record.degraded_reasons),
        "published_at": record.published_at,
        "ingested_at": record.ingested_at,
        "extracted_at": record.extracted_at,
        "payload": record.model_dump(mode="python"),
    }
    if isinstance(record, RawAliasV1):
        content.update(entity=parse_record_id(record.entity_id), raw_surface_form=record.raw_surface_form)
    elif isinstance(record, SourceClaimV1):
        content.update(
            entity_ids=list(record.entity_ids),
            claim_text=record.claim_text,
            predicate=record.predicate,
        )
    elif isinstance(record, EventParticipantV1):
        content.update(event=parse_record_id(record.event_id), entity=parse_record_id(record.entity_id))
    elif isinstance(record, EvidenceRelationV1):
        content.update(
            relation=record.relation.value,
            subject_ref=record.subject_id,
            object_ref=record.object_id,
            relation_basis=record.basis,
        )
    elif isinstance(record, ExtractionFailureV1):
        content["failure_code"] = record.failure_code
    elif isinstance(record, SourceRecordV1):
        content["title"] = record.title
    elif isinstance(record, CanonicalEntityV1):
        content["canonical_name"] = record.canonical_name
    elif isinstance(record, GroundedEventV1):
        content["event_description"] = record.description
    return content


def _semantic_from_row(
    row: dict[str, Any] | None,
    model: type[TRecord],
) -> TRecord | None:
    if not row or not isinstance(row.get("payload"), dict):
        return None
    return model.model_validate(row["payload"])


def _with_lineage(
    record: TRecord | None,
    predecessors: Iterable[str],
) -> TRecord | None:
    if record is None:
        return None
    supersedes = tuple(sorted(set(record.supersedes) | set(predecessors)))
    if supersedes == record.supersedes:
        return record
    return type(record).model_validate({**record.model_dump(mode="python"), "supersedes": supersedes})


class GroundedStateStore:
    """The only Core persistence boundary for grounded temporal evidence."""

    def __init__(self, pool) -> None:
        self.pool = pool

    async def load_record(
        self,
        kind: GroundedRecordKind,
        record_id: str,
        *,
        product_id: str,
    ) -> GroundedSemanticRecordV1 | None:
        table = TABLE_BY_KIND[kind]
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    f"SELECT payload FROM ONLY type::record('{table}', $record_key) WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(record_id), "product": parse_record_id(product_id)},
                )
            )
            lineage = parse_rows(
                await db.query(
                    "SELECT predecessor_ref FROM grounded_supersession "
                    "WHERE product = $product AND successor_ref = $successor ORDER BY predecessor_ref ASC",
                    {"product": parse_record_id(product_id), "successor": record_id},
                )
            )
        return _with_lineage(
            _semantic_from_row(row, MODEL_BY_KIND[kind]),
            (str(item["predecessor_ref"]) for item in lineage if item.get("predecessor_ref")),
        )

    async def load_source(self, record_id: str, *, product_id: str) -> SourceRecordV1 | None:
        return await self.load_record(GroundedRecordKind.SOURCE, record_id, product_id=product_id)  # type: ignore[return-value]

    async def load_entity(self, record_id: str, *, product_id: str) -> CanonicalEntityV1 | None:
        return await self.load_record(GroundedRecordKind.ENTITY, record_id, product_id=product_id)  # type: ignore[return-value]

    async def load_alias(self, record_id: str, *, product_id: str) -> RawAliasV1 | None:
        return await self.load_record(GroundedRecordKind.ALIAS, record_id, product_id=product_id)  # type: ignore[return-value]

    async def load_claim(self, record_id: str, *, product_id: str) -> SourceClaimV1 | None:
        return await self.load_record(GroundedRecordKind.CLAIM, record_id, product_id=product_id)  # type: ignore[return-value]

    async def load_event(self, record_id: str, *, product_id: str) -> GroundedEventV1 | None:
        return await self.load_record(GroundedRecordKind.EVENT, record_id, product_id=product_id)  # type: ignore[return-value]

    async def load_event_participant(self, record_id: str, *, product_id: str) -> EventParticipantV1 | None:
        return await self.load_record(GroundedRecordKind.EVENT_PARTICIPANT, record_id, product_id=product_id)  # type: ignore[return-value]

    async def load_relation(self, record_id: str, *, product_id: str) -> EvidenceRelationV1 | None:
        return await self.load_record(GroundedRecordKind.RELATION, record_id, product_id=product_id)  # type: ignore[return-value]

    async def load_failure(self, record_id: str, *, product_id: str) -> ExtractionFailureV1 | None:
        return await self.load_record(GroundedRecordKind.EXTRACTION_FAILURE, record_id, product_id=product_id)  # type: ignore[return-value]

    async def list_records(
        self,
        kind: GroundedRecordKind,
        *,
        product_id: str,
    ) -> list[GroundedSemanticRecordV1]:
        table = TABLE_BY_KIND[kind]
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    f"SELECT stable_id, payload FROM {table} WHERE product = $product ORDER BY stable_id ASC",
                    {"product": parse_record_id(product_id)},
                )
            )
            lineage_rows = parse_rows(
                await db.query(
                    "SELECT successor_ref, predecessor_ref FROM grounded_supersession "
                    "WHERE product = $product AND record_kind = $kind",
                    {"product": parse_record_id(product_id), "kind": kind.value},
                )
            )
        model = MODEL_BY_KIND[kind]
        lineage: dict[str, list[str]] = {}
        for row in lineage_rows:
            if row.get("successor_ref") and row.get("predecessor_ref"):
                lineage.setdefault(str(row["successor_ref"]), []).append(str(row["predecessor_ref"]))
        return [
            record
            for row in rows
            if (raw := _semantic_from_row(row, model)) is not None
            and (record := _with_lineage(raw, lineage.get(str(raw.record_id), ()))) is not None
        ]

    async def load_any_record(
        self,
        record_id: str,
        *,
        product_id: str,
    ) -> GroundedSemanticRecordV1 | None:
        prefix = record_id.partition(":")[0]
        for kind, table in TABLE_BY_KIND.items():
            if table == prefix:
                return await self.load_record(kind, record_id, product_id=product_id)
        return None

    async def bounded_candidate_records(
        self,
        *,
        product_id: str,
        allowed_kinds: Iterable[GroundedRecordKind] | None,
        content_terms: Iterable[str],
        entity_ids: Iterable[str],
        source_ids: Iterable[str],
        max_records: int,
    ) -> list[GroundedSemanticRecordV1]:
        """Select a deterministic bounded pool without materializing the corpus."""
        if max_records < 1 or max_records > 200:
            raise ValueError("candidate preselection must remain between one and 200 records")
        requested = set(allowed_kinds or GroundedRecordKind)
        # Evidence-bearing records precede descriptive/edge records. This is a
        # deterministic preselection policy, not a semantic acceptance policy.
        kind_order = (
            GroundedRecordKind.CLAIM,
            GroundedRecordKind.EVENT,
            GroundedRecordKind.SOURCE,
            GroundedRecordKind.ENTITY,
            GroundedRecordKind.ALIAS,
            GroundedRecordKind.EVENT_PARTICIPANT,
            GroundedRecordKind.RELATION,
            GroundedRecordKind.EXTRACTION_FAILURE,
        )
        terms = tuple(sorted({item.lower() for item in content_terms if item}))[:8]
        entities = tuple(sorted(set(entity_ids)))[:200]
        sources = tuple(sorted(set(source_ids)))[:100]
        # The payload fallback preserves bounded retrieval for rows created by
        # schema v163-v167 before the additive v168 projection fields existed.
        text_fields = {
            GroundedRecordKind.CLAIM: ("claim_text", "payload.claim_text"),
            GroundedRecordKind.EVENT: ("event_description", "payload.description"),
            GroundedRecordKind.SOURCE: ("title", "payload.title"),
            GroundedRecordKind.ENTITY: ("canonical_name", "payload.canonical_name"),
            GroundedRecordKind.ALIAS: ("raw_surface_form", "payload.raw_surface_form"),
            GroundedRecordKind.RELATION: ("relation_basis", "payload.basis"),
        }
        entity_filters = {
            GroundedRecordKind.CLAIM: "entity_ids CONTAINSANY $entity_ids",
            GroundedRecordKind.ENTITY: "stable_id INSIDE $entity_ids",
            GroundedRecordKind.ALIAS: "string::concat('grounded_entity:', meta::id(entity)) INSIDE $entity_ids",
            GroundedRecordKind.EVENT_PARTICIPANT: (
                "string::concat('grounded_entity:', meta::id(entity)) INSIDE $entity_ids"
            ),
            GroundedRecordKind.RELATION: "subject_ref INSIDE $entity_ids OR object_ref INSIDE $entity_ids",
        }
        selected: list[GroundedSemanticRecordV1] = []
        async with self.pool.connection() as db:
            for kind in kind_order:
                if kind not in requested or len(selected) >= max_records:
                    continue
                clauses = ["product = $product"]
                if sources:
                    clauses.append(
                        "("
                        + " OR ".join(f"source_external_id = $source_id_{index}" for index in range(len(sources)))
                        + ")"
                    )
                if entities:
                    expression = entity_filters.get(kind)
                    if expression is None:
                        continue
                    clauses.append(f"({expression})")
                candidate_text_fields = text_fields.get(kind)
                if terms and candidate_text_fields:
                    clauses.append(
                        "("
                        + " OR ".join(
                            f"({text_field} IS NOT NONE AND string::lowercase({text_field}) CONTAINS $term_{index})"
                            for index in range(len(terms))
                            for text_field in candidate_text_fields
                        )
                        + ")"
                    )
                elif terms and kind not in {
                    GroundedRecordKind.EVENT_PARTICIPANT,
                    GroundedRecordKind.EXTRACTION_FAILURE,
                }:
                    continue
                params: dict[str, Any] = {
                    "product": parse_record_id(product_id),
                    "entity_ids": list(entities),
                    "limit": max_records - len(selected),
                }
                params.update({f"source_id_{index}": source for index, source in enumerate(sources)})
                params.update({f"term_{index}": term for index, term in enumerate(terms)})
                index_hint = (
                    " WITH INDEX idx_grounded_claim_product_source"
                    if kind is GroundedRecordKind.CLAIM and sources
                    else ""
                )
                rows = parse_rows(
                    await db.query(
                        f"SELECT stable_id, payload FROM {TABLE_BY_KIND[kind]}{index_hint} "
                        f"WHERE {' AND '.join(clauses)} ORDER BY stable_id LIMIT $limit",
                        params,
                    )
                )
                model = MODEL_BY_KIND[kind]
                selected.extend(record for row in rows if (record := _semantic_from_row(row, model)) is not None)
        return selected[:max_records]

    async def ace_created_times_for_ids(
        self,
        record_ids: Iterable[str],
        *,
        product_id: str,
    ) -> dict[str, datetime]:
        grouped: dict[str, list[str]] = {}
        for record_id in sorted(set(record_ids)):
            table, separator, _key = record_id.partition(":")
            if separator and table in TABLE_BY_KIND.values():
                grouped.setdefault(table, []).append(record_id)
        created: dict[str, datetime] = {}
        async with self.pool.connection() as db:
            for table, ids in grouped.items():
                rows = parse_rows(
                    await db.query(
                        f"SELECT stable_id, created_at FROM {table} "
                        "WHERE product = $product AND stable_id INSIDE $ids ORDER BY stable_id",
                        {"product": parse_record_id(product_id), "ids": ids},
                    )
                )
                for row in rows:
                    if row.get("stable_id") and row.get("created_at") is not None:
                        created[str(row["stable_id"])] = TypeAdapter(datetime).validate_python(row["created_at"])
        return created

    async def record_exists(self, record_id: str, *, product_id: str) -> bool:
        table = record_id.partition(":")[0]
        if table not in set(TABLE_BY_KIND.values()):
            return False
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    f"SELECT id FROM ONLY type::record('{table}', $record_key) WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(record_id), "product": parse_record_id(product_id)},
                )
            )
        return row is not None

    async def existing_record_ids(
        self,
        record_ids: Iterable[str],
        *,
        product_id: str,
        db=None,
    ) -> set[str]:
        """Resolve a bounded reference set with one query per record table."""
        grouped: dict[str, list[str]] = {}
        for record_id in sorted(set(record_ids)):
            table, separator, _key = record_id.partition(":")
            if separator and table in TABLE_BY_KIND.values():
                grouped.setdefault(table, []).append(record_id)
        found: set[str] = set()

        async def load(connection) -> None:
            for table, ids in grouped.items():
                rows = parse_rows(
                    await connection.query(
                        "SELECT stable_id, product FROM $records ORDER BY stable_id",
                        {"records": [parse_record_id(record_id) for record_id in ids]},
                    )
                )
                found.update(
                    str(row["stable_id"])
                    for row in rows
                    if row.get("stable_id") and str(row.get("product")) == product_id
                )

        if db is None:
            async with self.pool.connection() as connection:
                await load(connection)
        else:
            await load(db)
        return found

    async def preload_record_rows(
        self,
        records: Iterable[GroundedSemanticRecordV1],
        *,
        db,
    ) -> dict[str, dict[str, Any]]:
        """Load exact replay candidates once before an item writes its children."""
        grouped: dict[GroundedRecordKind, list[str]] = {}
        product_ids: set[str] = set()
        for record in records:
            grouped.setdefault(record.record_kind, []).append(str(record.record_id))
            product_ids.add(record.product_id)
        if len(product_ids) > 1:
            raise GroundedStateProductScopeError("one item cannot span grounded-state products")
        if not product_ids:
            return {}
        product_id = next(iter(product_ids))
        existing: dict[str, dict[str, Any]] = {}
        for _kind, ids in grouped.items():
            rows = parse_rows(
                await db.query(
                    "SELECT stable_id, product, payload FROM $records ORDER BY stable_id",
                    {"records": [parse_record_id(record_id) for record_id in sorted(set(ids))]},
                )
            )
            existing.update(
                (str(row["stable_id"]), row)
                for row in rows
                if row.get("stable_id")
                and str(row.get("product")) == product_id
                and isinstance(row.get("payload"), dict)
            )
        return existing

    async def lineage_predecessors_for(
        self,
        records: Iterable[GroundedSemanticRecordV1],
        *,
        db,
    ) -> tuple[dict[str, tuple[str, ...]], set[str]]:
        """Resolve predecessor sets in bounded table-level queries per item."""
        grouped: dict[GroundedRecordKind, list[GroundedSemanticRecordV1]] = {}
        product_ids: set[str] = set()
        for record in records:
            grouped.setdefault(record.record_kind, []).append(record)
            product_ids.add(record.product_id)
        if len(product_ids) > 1:
            raise GroundedStateProductScopeError("one item cannot span grounded-state products")
        if not product_ids:
            return {}, set()
        product_id = next(iter(product_ids))
        predecessors_by_id: dict[str, tuple[str, ...]] = {}
        existing_coordinates: set[str] = set()
        for kind, kind_records in grouped.items():
            ordered_records = sorted(
                kind_records,
                key=lambda record: (record.source_external_id, record.local_id, str(record.record_id)),
            )
            result_sets = await db.query(
                "RETURN array::map($coordinates, |$coordinate| "
                f"(SELECT stable_id, source_version, content_hash FROM {TABLE_BY_KIND[kind]} "
                "WHERE product = $product "
                "AND source_external_id = $coordinate.source_external_id "
                "AND local_id = $coordinate.local_id ORDER BY stable_id ASC));",
                {
                    "product": parse_record_id(product_id),
                    "coordinates": [
                        {
                            "source_external_id": record.source_external_id,
                            "local_id": record.local_id,
                        }
                        for record in ordered_records
                    ],
                },
            )
            if not isinstance(result_sets, list) or len(result_sets) != len(ordered_records):
                raise GroundedStatePersistenceError("bounded lineage preflight returned an invalid result shape")
            for record, raw_rows in zip(ordered_records, result_sets, strict=True):
                rows = raw_rows if isinstance(raw_rows, list) else []
                current_version = _version_key(record.source_version)
                predecessors: list[str] = []
                for row in rows:
                    stable_id = str(row.get("stable_id") or "")
                    if not stable_id or stable_id == record.record_id:
                        continue
                    existing_coordinates.add(str(record.record_id))
                    source_version = str(row.get("source_version") or "")
                    content_hash = str(row.get("content_hash") or "")
                    if source_version == record.source_version:
                        if content_hash != record.content_hash:
                            predecessors.append(stable_id)
                    elif _version_key(source_version) < current_version:
                        predecessors.append(stable_id)
                predecessors_by_id[str(record.record_id)] = tuple(predecessors)
        return predecessors_by_id, existing_coordinates

    async def lineage_predecessors(self, record: GroundedSemanticRecordV1, *, db=None) -> tuple[str, ...]:
        table = TABLE_BY_KIND[record.record_kind]
        params = {
            "product": parse_record_id(record.product_id),
            "source_external_id": record.source_external_id,
            "local_id": record.local_id,
            "stable_id": record.record_id,
        }
        query = (
            f"SELECT stable_id, source_version, content_hash FROM {table} "
            "WHERE product = $product "
            "AND source_external_id = $source_external_id "
            "AND local_id = $local_id AND stable_id != $stable_id "
            "ORDER BY stable_id ASC"
        )
        if db is None:
            async with self.pool.connection() as connection:
                rows = parse_rows(await connection.query(query, params))
        else:
            rows = parse_rows(await db.query(query, params))
        current_version = _version_key(record.source_version)
        predecessors: list[str] = []
        for row in rows:
            stable_id = row.get("stable_id")
            source_version = str(row.get("source_version") or "")
            content_hash = str(row.get("content_hash") or "")
            if not stable_id:
                continue
            if source_version == record.source_version:
                if content_hash != record.content_hash:
                    predecessors.append(str(stable_id))
            elif _version_key(source_version) < current_version:
                predecessors.append(str(stable_id))
        return tuple(predecessors)

    async def create_record(
        self,
        db,
        record: GroundedSemanticRecordV1,
        *,
        preloaded_row: dict[str, Any] | None = None,
        preflight_complete: bool = False,
    ) -> bool:
        """Create one immutable row; return False only for an exact replay."""
        table = TABLE_BY_KIND[record.record_kind]
        existing = preloaded_row
        if not preflight_complete:
            existing = parse_one(
                await db.query(
                    f"SELECT payload FROM ONLY type::record('{table}', $record_key) WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(str(record.record_id)),
                        "product": parse_record_id(record.product_id),
                    },
                )
            )
        if existing:
            stored = _semantic_from_row(existing, type(record))
            if stored is not None and _semantic_replay_hash(stored) == _semantic_replay_hash(record):
                return False
            raise GroundedStateReplayConflict(f"stable identity {record.record_id} contains different material")
        result = await db.query(
            f"CREATE ONLY type::record('{table}', $record_key) CONTENT $content",
            {
                "record_key": _record_key(str(record.record_id)),
                "content": _semantic_content(record),
            },
        )
        if isinstance(result, str):
            # Resolve a same-identity race by re-reading and comparing immutable payloads.
            raced = parse_one(
                await db.query(
                    f"SELECT payload FROM ONLY type::record('{table}', $record_key) WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(str(record.record_id)),
                        "product": parse_record_id(record.product_id),
                    },
                )
            )
            stored = _semantic_from_row(raced, type(record))
            if stored is not None and _semantic_replay_hash(stored) == _semantic_replay_hash(record):
                return False
            raise GroundedStateReplayConflict(f"create race for {record.record_id} failed closed")
        return True

    async def create_lineage_edges(
        self,
        db,
        record: GroundedSemanticRecordV1,
    ) -> tuple[str, ...]:
        """Append deterministic lineage edges for every known version/correction pair."""
        table = TABLE_BY_KIND[record.record_kind]
        rows = parse_rows(
            await db.query(
                f"SELECT payload FROM {table} WHERE product = $product "
                "AND source_external_id = $source_external_id AND local_id = $local_id",
                {
                    "product": parse_record_id(record.product_id),
                    "source_external_id": record.source_external_id,
                    "local_id": record.local_id,
                },
            )
        )
        model = MODEL_BY_KIND[record.record_kind]
        versions = [item for row in rows if (item := _semantic_from_row(row, model)) is not None]
        pairs: set[tuple[str, str]] = set()
        for index, left in enumerate(versions):
            for right in versions[index + 1 :]:
                left_id = str(left.record_id)
                right_id = str(right.record_id)
                if _version_key(left.source_version) != _version_key(right.source_version):
                    successor, predecessor = (
                        (left_id, right_id)
                        if _version_key(left.source_version) > _version_key(right.source_version)
                        else (right_id, left_id)
                    )
                    pairs.add((successor, predecessor))
                elif right_id in left.supersedes:
                    pairs.add((left_id, right_id))
                elif left_id in right.supersedes:
                    pairs.add((right_id, left_id))
                elif left.extracted_at and right.extracted_at and left.extracted_at != right.extracted_at:
                    successor, predecessor = (
                        (left_id, right_id) if left.extracted_at > right.extracted_at else (right_id, left_id)
                    )
                    pairs.add((successor, predecessor))
        for successor in versions:
            pairs.update((str(successor.record_id), predecessor) for predecessor in successor.supersedes)

        lineage_ids: list[str] = []
        for successor_id, predecessor_id in sorted(pairs):
            lineage = SupersessionLineageV1(
                product_id=record.product_id,
                record_kind=record.record_kind,
                successor_id=successor_id,
                predecessor_id=predecessor_id,
                source_external_id=record.source_external_id,
                local_id=record.local_id,
            )
            existing = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('grounded_supersession', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {
                        "record_key": _record_key(str(lineage.lineage_id)),
                        "product": parse_record_id(lineage.product_id),
                    },
                )
            )
            if existing:
                stored = SupersessionLineageV1.model_validate(existing["payload"])
                if canonical_hash(stored) != canonical_hash(lineage):
                    raise GroundedStateReplayConflict(
                        f"lineage identity {lineage.lineage_id} contains different material"
                    )
                lineage_ids.append(str(lineage.lineage_id))
                continue
            content = {
                "contract_version": lineage.contract_version,
                "product": parse_record_id(lineage.product_id),
                "lineage_id": lineage.lineage_id,
                "record_kind": lineage.record_kind.value,
                "successor_ref": lineage.successor_id,
                "predecessor_ref": lineage.predecessor_id,
                "source_external_id": lineage.source_external_id,
                "local_id": lineage.local_id,
                "policy_version": lineage.policy_version,
                "payload": lineage.model_dump(mode="python"),
            }
            await _query_or_raise(
                db,
                "CREATE ONLY type::record('grounded_supersession', $record_key) CONTENT $content",
                {"record_key": _record_key(str(lineage.lineage_id)), "content": content},
            )
            lineage_ids.append(str(lineage.lineage_id))
        return tuple(lineage_ids)

    async def list_supersessions(self, *, product_id: str) -> list[SupersessionLineageV1]:
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT lineage_id, payload FROM grounded_supersession "
                    "WHERE product = $product ORDER BY lineage_id ASC",
                    {"product": parse_record_id(product_id)},
                )
            )
        return [
            SupersessionLineageV1.model_validate(row["payload"]) for row in rows if isinstance(row.get("payload"), dict)
        ]

    async def load_supersession(
        self,
        lineage_id: str,
        *,
        product_id: str,
    ) -> SupersessionLineageV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('grounded_supersession', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(lineage_id), "product": parse_record_id(product_id)},
                )
            )
        if not row or not isinstance(row.get("payload"), dict):
            return None
        return SupersessionLineageV1.model_validate(row["payload"])

    async def load_item_receipt(
        self,
        receipt_id: str,
        *,
        product_id: str,
    ) -> IngestionItemReceiptV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('grounded_ingestion_item_receipt', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(receipt_id), "product": parse_record_id(product_id)},
                )
            )
        return (
            IngestionItemReceiptV1.model_validate(row["payload"])
            if row and isinstance(row.get("payload"), dict)
            else None
        )

    async def create_item_receipt(self, db, receipt: IngestionItemReceiptV1) -> None:
        existing = parse_one(
            await db.query(
                "SELECT payload FROM ONLY type::record('grounded_ingestion_item_receipt', $record_key) "
                "WHERE product = $product LIMIT 1",
                {
                    "record_key": _record_key(receipt.receipt_id),
                    "product": parse_record_id(receipt.product_id),
                },
            )
        )
        if existing:
            stored = IngestionItemReceiptV1.model_validate(existing["payload"])
            if canonical_hash(stored) == canonical_hash(receipt):
                return
            raise GroundedStateReplayConflict(f"item receipt {receipt.receipt_id} contains different material")
        content = {
            "contract_version": receipt.contract_version,
            "product": parse_record_id(receipt.product_id),
            "receipt_id": receipt.receipt_id,
            "manifest_id": receipt.manifest_id,
            "item_key": receipt.item_key,
            "item_ordinal": receipt.item_ordinal,
            "input_hash": receipt.input_hash,
            "disposition": receipt.disposition.value,
            "payload": receipt.model_dump(mode="python"),
        }
        await _query_or_raise(
            db,
            "CREATE ONLY type::record('grounded_ingestion_item_receipt', $record_key) CONTENT $content",
            {"record_key": _record_key(receipt.receipt_id), "content": content},
        )

    async def load_batch_receipt(
        self,
        receipt_id: str,
        *,
        product_id: str,
    ) -> BatchIngestionReceiptV1 | None:
        async with self.pool.connection() as db:
            row = parse_one(
                await db.query(
                    "SELECT payload FROM ONLY type::record('grounded_batch_ingestion_receipt', $record_key) "
                    "WHERE product = $product LIMIT 1",
                    {"record_key": _record_key(receipt_id), "product": parse_record_id(product_id)},
                )
            )
        return (
            BatchIngestionReceiptV1.model_validate(row["payload"])
            if row and isinstance(row.get("payload"), dict)
            else None
        )

    async def create_batch_receipt(self, receipt: BatchIngestionReceiptV1) -> BatchIngestionReceiptV1:
        existing = await self.load_batch_receipt(receipt.receipt_id, product_id=receipt.product_id)
        if existing is not None:
            if canonical_hash(existing) != canonical_hash(receipt):
                raise GroundedStateReplayConflict(f"batch receipt {receipt.receipt_id} contains different material")
            return existing
        content = {
            "contract_version": receipt.contract_version,
            "product": parse_record_id(receipt.product_id),
            "receipt_id": receipt.receipt_id,
            "manifest_id": receipt.manifest_id,
            "manifest_hash": receipt.manifest_hash,
            "adapter_id": receipt.adapter_id,
            "extraction_run_id": receipt.extraction_run_id,
            "payload": receipt.model_dump(mode="python"),
        }
        async with self.pool.connection() as db:
            result = await db.query(
                "CREATE ONLY type::record('grounded_batch_ingestion_receipt', $record_key) CONTENT $content",
                {"record_key": _record_key(receipt.receipt_id), "content": content},
            )
        if isinstance(result, str):
            raced = await self.load_batch_receipt(receipt.receipt_id, product_id=receipt.product_id)
            if raced is not None and canonical_hash(raced) == canonical_hash(receipt):
                return raced
            raise GroundedStateReplayConflict(f"batch receipt create failed closed: {result[:200]}")
        return receipt

    async def semantic_counts(self, *, product_id: str) -> dict[GroundedRecordKind, int]:
        counts: dict[GroundedRecordKind, int] = {}
        async with self.pool.connection() as db:
            for kind, table in TABLE_BY_KIND.items():
                row = parse_one(
                    await db.query(
                        f"SELECT count() AS count FROM {table} WHERE product = $product GROUP ALL",
                        {"product": parse_record_id(product_id)},
                    )
                )
                counts[kind] = int(row.get("count", 0)) if row else 0
        return counts

    async def ace_created_times(self, *, product_id: str) -> dict[str, datetime]:
        """Return ACE row-creation time without conflating it with ingestion time."""
        created: dict[str, datetime] = {}
        async with self.pool.connection() as db:
            for table in TABLE_BY_KIND.values():
                rows = parse_rows(
                    await db.query(
                        f"SELECT stable_id, created_at FROM {table} WHERE product = $product ORDER BY stable_id ASC",
                        {"product": parse_record_id(product_id)},
                    )
                )
                for row in rows:
                    stable_id = row.get("stable_id")
                    created_at = row.get("created_at")
                    if stable_id and created_at is not None:
                        created[str(stable_id)] = TypeAdapter(datetime).validate_python(created_at)
        return created

    async def assert_product_refs(self, refs: Iterable[str], *, product_id: str) -> None:
        for ref in sorted(set(refs)):
            if not await self.record_exists(ref, product_id=product_id):
                raise GroundedStateProductScopeError(f"referenced grounded-state record is unavailable: {ref}")
