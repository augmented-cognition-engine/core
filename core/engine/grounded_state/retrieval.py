"""TP3 candidate retrieval over the Core-owned grounded-state substrate."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

from core.engine.candidates import (
    ALL_CANDIDATE_SIGNALS,
    MAX_CANDIDATE_RECORDS,
    CandidateFiltersV1,
    CandidateIndexSnapshotV1,
    CandidateReceiptV1,
    CandidateRecordV1,
    CandidateRequestV1,
    CandidateSignal,
    DeterministicCandidateFinder,
    default_candidate_index_versions,
)
from core.engine.grounded_state.ingestion_contracts import (
    CanonicalEntityV1,
    EventParticipantV1,
    EvidenceRelationV1,
    ExtractionFailureV1,
    GroundedEventV1,
    GroundedRecordKind,
    GroundedSemanticRecordV1,
    RawAliasV1,
    SourceClaimV1,
    SourceRecordV1,
)
from core.engine.grounded_state.operations import StateEngineOperationsService
from core.engine.grounded_state.persistence import (
    GroundedStateProductScopeError,
    GroundedStateStore,
)


class GroundedCandidateIndexBoundExceeded(RuntimeError):
    """The bounded TP3 pilot cannot silently truncate an oversized product."""


def _candidate_content(record: GroundedSemanticRecordV1) -> str | None:
    if isinstance(record, SourceRecordV1):
        return record.content or record.title
    if isinstance(record, CanonicalEntityV1):
        return record.canonical_name
    if isinstance(record, RawAliasV1):
        return record.raw_surface_form
    if isinstance(record, SourceClaimV1):
        return record.claim_text
    if isinstance(record, GroundedEventV1):
        return record.description
    if isinstance(record, EventParticipantV1):
        return " ".join(part for part in (record.raw_surface_form, record.role) if part)
    if isinstance(record, EvidenceRelationV1):
        return record.basis
    if isinstance(record, ExtractionFailureV1):
        return record.failure_message
    return None


def _entity_ids(record: GroundedSemanticRecordV1) -> tuple[str, ...]:
    if isinstance(record, CanonicalEntityV1):
        return (str(record.record_id),)
    if isinstance(record, RawAliasV1):
        return (record.entity_id,)
    if isinstance(record, SourceClaimV1):
        return record.entity_ids
    if isinstance(record, EventParticipantV1):
        return (record.entity_id,)
    return ()


def _direct_refs(record: GroundedSemanticRecordV1) -> tuple[str, ...]:
    refs: set[str] = set(record.supersedes)
    refs.add(record.source_external_id)
    refs.update(_entity_ids(record))
    if isinstance(record, EventParticipantV1):
        refs.add(record.event_id)
    elif isinstance(record, EvidenceRelationV1):
        refs.update((record.subject_id, record.object_id))
    return tuple(sorted(refs))


def candidate_record_from_grounded(record: GroundedSemanticRecordV1) -> CandidateRecordV1:
    content = _candidate_content(record)
    digest = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
    return CandidateRecordV1(
        record_id=str(record.record_id),
        product_id=record.product_id,
        record_kind=record.record_kind.value,
        content_hash=digest,
        content=content,
        entity_ids=_entity_ids(record),
        temporal=record.temporal,
        source_id=record.source_external_id,
        publisher_id=record.publisher_id,
        graph_neighbor_ids=_direct_refs(record),
        facets=(record.record_kind.value,),
    )


def build_grounded_candidate_snapshot(
    records: Iterable[GroundedSemanticRecordV1],
    *,
    available_signals: Iterable[CandidateSignal] = ALL_CANDIDATE_SIGNALS,
) -> CandidateIndexSnapshotV1:
    semantic_records = tuple(records)
    candidates = tuple(candidate_record_from_grounded(record) for record in semantic_records)
    if len(candidates) > MAX_CANDIDATE_RECORDS:
        raise GroundedCandidateIndexBoundExceeded(
            f"grounded candidate pilot is bounded to {MAX_CANDIDATE_RECORDS} records; found {len(candidates)}"
        )
    adjacency = {record.record_id: set(record.graph_neighbor_ids) for record in candidates}
    for semantic, candidate in zip(semantic_records, candidates, strict=True):
        for reference in candidate.graph_neighbor_ids:
            if reference in adjacency:
                adjacency[reference].add(candidate.record_id)
        if isinstance(semantic, EventParticipantV1):
            event_id = semantic.event_id
            entity_id = semantic.entity_id
            if event_id in adjacency:
                adjacency[event_id].update((candidate.record_id, entity_id))
            if entity_id in adjacency:
                adjacency[entity_id].update((candidate.record_id, event_id))
        elif isinstance(semantic, EvidenceRelationV1):
            subject_id = semantic.subject_id
            object_id = semantic.object_id
            if subject_id in adjacency:
                adjacency[subject_id].update((candidate.record_id, object_id))
            if object_id in adjacency:
                adjacency[object_id].update((candidate.record_id, subject_id))

    enriched: list[CandidateRecordV1] = []
    for candidate in candidates:
        graph_neighbors = tuple(sorted(adjacency[candidate.record_id]))
        if len(graph_neighbors) > MAX_CANDIDATE_RECORDS:
            raise GroundedCandidateIndexBoundExceeded(
                f"grounded candidate graph is bounded to {MAX_CANDIDATE_RECORDS} neighbors per record"
            )
        material = candidate.model_dump()
        material["graph_neighbor_ids"] = graph_neighbors
        enriched.append(CandidateRecordV1.model_validate(material))

    versions = default_candidate_index_versions()
    versions["grounded_state"] = "ace.grounded-state.schema/v163"
    return CandidateIndexSnapshotV1(
        records=tuple(enriched),
        available_signals=tuple(available_signals),
        index_versions=versions,
    )


class GroundedStateCandidateService:
    """Internal provider-free TP3 service; intentionally not a public MCP tool."""

    primary_model_calls = 0

    def __init__(self, pool) -> None:
        self.store = GroundedStateStore(pool)
        self.operations = StateEngineOperationsService(pool)

    @staticmethod
    def _content_terms(value: str | None) -> tuple[str, ...]:
        stop = {"a", "an", "and", "are", "for", "if", "in", "is", "of", "or", "the", "to", "what"}
        tokens = {token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if token not in stop}
        return tuple(sorted(tokens, key=lambda item: (-len(item), item))[:8])

    async def _bounded_records_for_request(
        self,
        request: CandidateRequestV1,
    ) -> list[GroundedSemanticRecordV1]:
        allowed: list[GroundedRecordKind] = []
        for value in request.filters.allowed_record_kinds:
            try:
                allowed.append(GroundedRecordKind(value))
            except ValueError:
                continue
        entity_ids = tuple(sorted(set(request.entity_ids) | set(request.filters.required_entity_ids)))
        source_ids = tuple(
            sorted(set(request.filters.allowed_source_ids) | ({request.source_id} if request.source_id else set()))
        )
        records = await self.store.bounded_candidate_records(
            product_id=request.product_id,
            allowed_kinds=allowed or None,
            content_terms=self._content_terms(request.content),
            entity_ids=entity_ids,
            source_ids=source_ids,
            max_records=request.max_candidates,
        )
        if request.query_record_id and all(str(record.record_id) != request.query_record_id for record in records):
            query_record = await self.store.load_any_record(
                request.query_record_id,
                product_id=request.product_id,
            )
            if query_record is not None:
                records = [query_record, *records[: request.max_candidates - 1]]
        return records

    async def _records(self, *, product_id: str) -> list[GroundedSemanticRecordV1]:
        await self.operations.assert_active(product_id=product_id)
        records: list[GroundedSemanticRecordV1] = []
        for kind in GroundedRecordKind:
            records.extend(await self.store.list_records(kind, product_id=product_id))
            if len(records) > MAX_CANDIDATE_RECORDS:
                raise GroundedCandidateIndexBoundExceeded(
                    f"grounded candidate pilot is bounded to {MAX_CANDIDATE_RECORDS} records"
                )
        return records

    async def records(self, *, product_id: str) -> list[GroundedSemanticRecordV1]:
        """Return the same bounded product-fenced record set used by TP3."""
        return await self._records(product_id=product_id)

    async def snapshot(
        self,
        *,
        product_id: str,
        available_signals: Iterable[CandidateSignal] = ALL_CANDIDATE_SIGNALS,
    ) -> CandidateIndexSnapshotV1:
        return build_grounded_candidate_snapshot(
            await self._records(product_id=product_id),
            available_signals=available_signals,
        )

    async def find_candidates(
        self,
        request: CandidateRequestV1,
        *,
        available_signals: Iterable[CandidateSignal] = ALL_CANDIDATE_SIGNALS,
    ) -> CandidateReceiptV1:
        await self.operations.assert_active(product_id=request.product_id)
        snapshot = build_grounded_candidate_snapshot(
            await self._bounded_records_for_request(request),
            available_signals=available_signals,
        )
        return await DeterministicCandidateFinder(snapshot).find_candidates(request)

    async def find_related(
        self,
        record_id: str,
        *,
        product_id: str,
        k: int = 20,
        enabled_signals: Iterable[CandidateSignal] = ALL_CANDIDATE_SIGNALS,
        available_signals: Iterable[CandidateSignal] = ALL_CANDIDATE_SIGNALS,
        filters: CandidateFiltersV1 | None = None,
        temporal_window_days: int = 365,
    ) -> CandidateReceiptV1:
        await self.operations.assert_active(product_id=product_id)
        semantic = await self.store.load_any_record(record_id, product_id=product_id)
        if semantic is None:
            raise GroundedStateProductScopeError(
                "grounded candidate query record is unavailable in the requested product scope"
            )
        query_record = candidate_record_from_grounded(semantic)
        request = CandidateRequestV1.from_record(
            query_record,
            k=k,
            enabled_signals=tuple(enabled_signals),
            filters=filters or CandidateFiltersV1(),
            temporal_window_days=temporal_window_days,
        )
        return await self.find_candidates(request, available_signals=available_signals)
