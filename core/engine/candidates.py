"""Provider-neutral, deterministic multi-signal candidate generation.

This module is shared infrastructure for grounded-evidence retrieval and
Cognify.  It ranks bounded candidates and produces an inspectable receipt; it
does not judge, persist, or promote semantic relationships.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.contracts import (
    FrozenContract,
    TemporalScopeV1,
    TimePrecision,
    stable_id,
)

CANDIDATE_RECORD_VERSION = "ace.candidate.record/v1"
CANDIDATE_FILTERS_VERSION = "ace.candidate.filters/v1"
CANDIDATE_REQUEST_VERSION = "ace.candidate.request/v1"
CANDIDATE_INDEX_VERSION = "ace.candidate.index-snapshot/v1"
CANDIDATE_RECEIPT_VERSION = "ace.candidate.receipt/v1"
CANDIDATE_POLICY_VERSION = "ace.candidate.multi-signal-policy/v1"

MAX_CANDIDATE_RECORDS = 200
MAX_CANDIDATE_K = 50
MAX_VECTOR_DIMENSIONS = 4_096
HASHED_VECTOR_DIMENSIONS = 256
MAX_GRAPH_REFS = 200
MAX_FILTER_VALUES = 100

_PRODUCT_ID = re.compile(r"^product:[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_TOKEN = re.compile(r"[a-z0-9]+")


class CandidateSignal(StrEnum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    ENTITY = "entity"
    TEMPORAL = "temporal"
    GRAPH = "graph"
    SOURCE_DIVERSITY = "source_diversity"


ALL_CANDIDATE_SIGNALS = tuple(CandidateSignal)


SIGNAL_WEIGHTS: dict[CandidateSignal, float] = {
    CandidateSignal.LEXICAL: 0.15,
    CandidateSignal.VECTOR: 0.20,
    CandidateSignal.ENTITY: 0.30,
    CandidateSignal.TEMPORAL: 0.15,
    CandidateSignal.GRAPH: 0.15,
    CandidateSignal.SOURCE_DIVERSITY: 0.05,
}


def _bounded_strings(
    value: Any,
    *,
    name: str,
    limit: int = MAX_FILTER_VALUES,
    item_limit: int = 500,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{name} must be a collection")
    items = tuple(sorted(set(value)))
    if len(items) > limit:
        raise ValueError(f"{name} exceeds the {limit}-item bound")
    if any(not isinstance(item, str) or not item.strip() or len(item) > item_limit for item in items):
        raise ValueError(f"{name} must contain bounded non-empty strings")
    return items


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value


def _tokens(value: str | None) -> tuple[str, ...]:
    return tuple(_TOKEN.findall((value or "").lower()))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    if left_norm < 1e-12 or right_norm < 1e-12:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def hashed_token_vector(value: str | None) -> tuple[float, ...]:
    """Return a deterministic local vector without a model or provider call."""
    counts: Counter[int] = Counter()
    for token in _tokens(value):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        counts[int.from_bytes(digest[:4], "big") % HASHED_VECTOR_DIMENSIONS] += 1
    if not counts:
        return ()
    vector = [0.0] * HASHED_VECTOR_DIMENSIONS
    for index, count in counts.items():
        vector[index] = 1.0 + math.log(count)
    return tuple(vector)


def _instant(scope: TemporalScopeV1) -> datetime | None:
    if scope.occurred_at is not None:
        return scope.occurred_at
    if scope.valid_from is not None and scope.valid_to is not None:
        return scope.valid_from + (scope.valid_to - scope.valid_from) / 2
    return scope.valid_from or scope.valid_to


def _interval(scope: TemporalScopeV1) -> tuple[datetime | None, datetime | None]:
    if scope.occurred_at is not None:
        return scope.occurred_at, scope.occurred_at
    return scope.valid_from, scope.valid_to


def _temporal_score(left: TemporalScopeV1, right: TemporalScopeV1, *, window_days: int) -> float | None:
    if left.precision is TimePrecision.UNKNOWN or right.precision is TimePrecision.UNKNOWN:
        return None
    left_start, left_end = _interval(left)
    right_start, right_end = _interval(right)
    if left_start is not None and right_end is not None and left_start <= right_end:
        if right_start is None or left_end is None or right_start <= left_end:
            return 1.0
    left_at = _instant(left)
    right_at = _instant(right)
    if left_at is None or right_at is None:
        return None
    distance_days = abs((left_at - right_at).total_seconds()) / 86_400
    return max(0.0, 1.0 - distance_days / max(1, window_days))


class CandidateRecordV1(FrozenContract):
    contract_version: Literal["ace.candidate.record/v1"] = CANDIDATE_RECORD_VERSION
    record_id: str = Field(min_length=1, max_length=240)
    product_id: str
    record_kind: str = Field(min_length=1, max_length=120)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content: str | None = Field(default=None, max_length=16_000)
    entity_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_GRAPH_REFS)
    temporal: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    source_id: str | None = Field(default=None, max_length=500)
    publisher_id: str | None = Field(default=None, max_length=240)
    graph_neighbor_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_GRAPH_REFS)
    facets: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_FILTER_VALUES)
    embedding: tuple[float, ...] = Field(default_factory=tuple, max_length=MAX_VECTOR_DIMENSIONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        if not _PRODUCT_ID.fullmatch(value):
            raise ValueError("product_id must be a bounded product record identifier")
        return value

    @field_validator("entity_ids", "graph_neighbor_ids", "facets", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        limit = MAX_GRAPH_REFS if info.field_name != "facets" else MAX_FILTER_VALUES
        return _bounded_strings(value, name=info.field_name, limit=limit)

    @field_validator("embedding", mode="before")
    @classmethod
    def normalize_embedding(cls, value: Any) -> tuple[float, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)) or len(value) > MAX_VECTOR_DIMENSIONS:
            raise ValueError("embedding must be a bounded numeric vector")
        vector = tuple(float(item) for item in value)
        if any(not math.isfinite(item) for item in vector):
            raise ValueError("embedding values must be finite")
        return vector

    @model_validator(mode="after")
    def validate_content(self) -> Self:
        if self.content is not None:
            digest = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
            if digest != self.content_hash:
                raise ValueError("content_hash must equal the supplied candidate content digest")
        return self


class CandidateFiltersV1(FrozenContract):
    contract_version: Literal["ace.candidate.filters/v1"] = CANDIDATE_FILTERS_VERSION
    allowed_record_kinds: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_FILTER_VALUES)
    allowed_source_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_FILTER_VALUES)
    required_entity_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_FILTER_VALUES)
    excluded_record_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_FILTER_VALUES)
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None
    include_unknown_time: bool = True

    @field_validator(
        "allowed_record_kinds",
        "allowed_source_ids",
        "required_entity_ids",
        "excluded_record_ids",
        mode="before",
    )
    @classmethod
    def normalize_values(cls, value: Any, info) -> tuple[str, ...]:
        return _bounded_strings(value, name=info.field_name)

    @field_validator("occurred_after", "occurred_before")
    @classmethod
    def validate_time(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.occurred_after and self.occurred_before and self.occurred_before < self.occurred_after:
            raise ValueError("occurred_before must not precede occurred_after")
        return self


class CandidateRequestV1(FrozenContract):
    contract_version: Literal["ace.candidate.request/v1"] = CANDIDATE_REQUEST_VERSION
    request_id: str | None = None
    product_id: str
    query_record_id: str | None = Field(default=None, max_length=240)
    content: str | None = Field(default=None, max_length=16_000)
    entity_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_GRAPH_REFS)
    temporal: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    source_id: str | None = Field(default=None, max_length=500)
    publisher_id: str | None = Field(default=None, max_length=240)
    graph_neighbor_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_GRAPH_REFS)
    embedding: tuple[float, ...] = Field(default_factory=tuple, max_length=MAX_VECTOR_DIMENSIONS)
    filters: CandidateFiltersV1 = Field(default_factory=CandidateFiltersV1)
    enabled_signals: tuple[CandidateSignal, ...] = Field(default=ALL_CANDIDATE_SIGNALS)
    k: int = Field(default=20, ge=1, le=MAX_CANDIDATE_K)
    max_candidates: int = Field(default=MAX_CANDIDATE_RECORDS, ge=1, le=MAX_CANDIDATE_RECORDS)
    temporal_window_days: int = Field(default=365, ge=1, le=36_500)
    policy_version: Literal["ace.candidate.multi-signal-policy/v1"] = CANDIDATE_POLICY_VERSION

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        if not _PRODUCT_ID.fullmatch(value):
            raise ValueError("product_id must be a bounded product record identifier")
        return value

    @field_validator("entity_ids", "graph_neighbor_ids", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _bounded_strings(value, name=info.field_name, limit=MAX_GRAPH_REFS)

    @field_validator("embedding", mode="before")
    @classmethod
    def normalize_embedding(cls, value: Any) -> tuple[float, ...]:
        return CandidateRecordV1.normalize_embedding(value)

    @field_validator("enabled_signals", mode="before")
    @classmethod
    def normalize_signals(cls, value: Any) -> tuple[CandidateSignal, ...]:
        if value is None:
            return ALL_CANDIDATE_SIGNALS
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("enabled_signals must be a collection")
        return tuple(sorted({CandidateSignal(item) for item in value}, key=lambda item: item.value))

    def identity_material(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"request_id"})

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if not (self.query_record_id or (self.content or "").strip() or self.entity_ids or self.graph_neighbor_ids):
            raise ValueError("candidate query requires a record, content, entity, or graph identity")
        expected = stable_id("candidate_request", self.identity_material())
        if self.request_id is not None and self.request_id != expected:
            raise ValueError("request_id does not match deterministic candidate request material")
        object.__setattr__(self, "request_id", expected)
        return self

    @classmethod
    def from_record(
        cls,
        record: CandidateRecordV1,
        **overrides: Any,
    ) -> CandidateRequestV1:
        return cls(
            product_id=record.product_id,
            query_record_id=record.record_id,
            content=record.content,
            entity_ids=record.entity_ids,
            temporal=record.temporal,
            source_id=record.source_id,
            publisher_id=record.publisher_id,
            graph_neighbor_ids=record.graph_neighbor_ids,
            embedding=record.embedding,
            **overrides,
        )


class CandidateIndexSnapshotV1(FrozenContract):
    contract_version: Literal["ace.candidate.index-snapshot/v1"] = CANDIDATE_INDEX_VERSION
    snapshot_id: str | None = None
    records: tuple[CandidateRecordV1, ...] = Field(max_length=MAX_CANDIDATE_RECORDS)
    available_signals: tuple[CandidateSignal, ...] = Field(default=ALL_CANDIDATE_SIGNALS)
    index_versions: dict[str, str] = Field(default_factory=dict)

    @field_validator("records", mode="before")
    @classmethod
    def normalize_records(cls, value: Any) -> tuple[Any, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("candidate index records must be a bounded collection")
        records = tuple(value)
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    item.record_id if isinstance(item, CandidateRecordV1) else str(item.get("record_id", ""))
                ),
            )
        )

    @field_validator("available_signals", mode="before")
    @classmethod
    def normalize_signals(cls, value: Any) -> tuple[CandidateSignal, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("available_signals must be a collection")
        return tuple(sorted({CandidateSignal(item) for item in value}, key=lambda item: item.value))

    @field_validator("index_versions")
    @classmethod
    def validate_versions(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > len(ALL_CANDIDATE_SIGNALS) + 4:
            raise ValueError("index_versions exceeds the signal bound")
        if any(not key or len(key) > 120 or not item or len(item) > 240 for key, item in value.items()):
            raise ValueError("index_versions must contain bounded stable names")
        return dict(sorted(value.items()))

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        ids = [record.record_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate index record IDs must be unique")
        material = self.model_dump(mode="json", exclude={"snapshot_id"})
        expected = stable_id("candidate_index", material)
        if self.snapshot_id is not None and self.snapshot_id != expected:
            raise ValueError("snapshot_id does not match deterministic index material")
        object.__setattr__(self, "snapshot_id", expected)
        return self


class CandidateSignalContributionV1(FrozenContract):
    signal: CandidateSignal
    score: float = Field(ge=0, le=1)
    weight: float = Field(ge=0, le=1)
    applied: bool
    reason: str = Field(min_length=1, max_length=240)


class CandidateResultV1(FrozenContract):
    record_id: str = Field(min_length=1, max_length=240)
    rank: int = Field(ge=1, le=MAX_CANDIDATE_K)
    score: float = Field(ge=0, le=1)
    contributions: tuple[CandidateSignalContributionV1, ...]
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=len(ALL_CANDIDATE_SIGNALS))

    @field_validator("degraded_reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value: Any) -> tuple[str, ...]:
        return _bounded_strings(value, name="degraded_reasons", limit=len(ALL_CANDIDATE_SIGNALS))


class CandidateReceiptV1(FrozenContract):
    contract_version: Literal["ace.candidate.receipt/v1"] = CANDIDATE_RECEIPT_VERSION
    receipt_id: str | None = None
    request_id: str
    snapshot_id: str
    product_id: str
    policy_version: str
    filters: CandidateFiltersV1
    requested_k: int = Field(ge=1, le=MAX_CANDIDATE_K)
    max_candidates: int = Field(ge=1, le=MAX_CANDIDATE_RECORDS)
    temporal_window_days: int = Field(ge=1, le=36_500)
    index_versions: dict[str, str]
    requested_signals: tuple[CandidateSignal, ...]
    applied_signals: tuple[CandidateSignal, ...]
    unavailable_signals: tuple[CandidateSignal, ...] = Field(default_factory=tuple)
    fallback_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=len(ALL_CANDIDATE_SIGNALS))
    records_in_snapshot: int = Field(ge=0, le=MAX_CANDIDATE_RECORDS)
    product_filtered: int = Field(ge=0, le=MAX_CANDIDATE_RECORDS)
    explicit_filtered: int = Field(ge=0, le=MAX_CANDIDATE_RECORDS)
    zero_score_filtered: int = Field(ge=0, le=MAX_CANDIDATE_RECORDS)
    candidates_scored: int = Field(ge=0, le=MAX_CANDIDATE_RECORDS)
    score_cap_omitted: int = Field(ge=0, le=MAX_CANDIDATE_RECORDS)
    return_cap_omitted: int = Field(ge=0, le=MAX_CANDIDATE_RECORDS)
    candidates_returned: int = Field(ge=0, le=MAX_CANDIDATE_K)
    truncated: bool
    candidates: tuple[CandidateResultV1, ...] = Field(max_length=MAX_CANDIDATE_K)
    primary_model_calls: Literal[0] = 0
    deterministic: Literal[True] = True

    @field_validator("requested_signals", "applied_signals", "unavailable_signals", mode="before")
    @classmethod
    def normalize_signals(cls, value: Any) -> tuple[CandidateSignal, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("receipt signals must be a collection")
        return tuple(sorted({CandidateSignal(item) for item in value}, key=lambda item: item.value))

    @field_validator("fallback_reasons", mode="before")
    @classmethod
    def normalize_fallbacks(cls, value: Any) -> tuple[str, ...]:
        return _bounded_strings(value, name="fallback_reasons", limit=len(ALL_CANDIDATE_SIGNALS))

    @field_validator("index_versions")
    @classmethod
    def validate_versions(cls, value: dict[str, str]) -> dict[str, str]:
        return CandidateIndexSnapshotV1.validate_versions(value)

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.candidates_returned != len(self.candidates):
            raise ValueError("candidate receipt count must match returned candidates")
        if [item.rank for item in self.candidates] != list(range(1, len(self.candidates) + 1)):
            raise ValueError("candidate ranks must be contiguous and one-based")
        if set(self.applied_signals) & set(self.unavailable_signals):
            raise ValueError("a signal cannot be both applied and unavailable")
        if set(self.applied_signals) | set(self.unavailable_signals) != set(self.requested_signals):
            raise ValueError("applied and unavailable signals must partition requested signals")
        accounted_records = (
            self.product_filtered + self.explicit_filtered + self.zero_score_filtered + self.candidates_scored
        )
        if self.records_in_snapshot != accounted_records:
            raise ValueError("candidate receipt filtering counts must reconcile to the snapshot")
        accounted_scored = self.score_cap_omitted + self.return_cap_omitted + self.candidates_returned
        if self.candidates_scored != accounted_scored:
            raise ValueError("candidate receipt cap counts must reconcile to scored candidates")
        if self.candidates_returned > self.requested_k:
            raise ValueError("candidate receipt cannot exceed requested_k")
        if self.candidates_returned + self.return_cap_omitted > self.max_candidates:
            raise ValueError("candidate receipt cannot exceed max_candidates before the return cap")
        if self.truncated is not bool(self.score_cap_omitted or self.return_cap_omitted):
            raise ValueError("candidate receipt truncation flag must match cap omissions")
        material = self.model_dump(mode="json", exclude={"receipt_id"})
        expected = stable_id("candidate_receipt", material)
        if self.receipt_id is not None and self.receipt_id != expected:
            raise ValueError("receipt_id does not match deterministic candidate receipt material")
        object.__setattr__(self, "receipt_id", expected)
        return self


class CandidateFinder(Protocol):
    async def find_candidates(self, request: CandidateRequestV1) -> CandidateReceiptV1: ...


class DeterministicCandidateFinder:
    """Bounded multi-signal ranker with no database, network, or model dependency."""

    def __init__(self, snapshot: CandidateIndexSnapshotV1) -> None:
        self.snapshot = snapshot

    @staticmethod
    def _passes_filters(record: CandidateRecordV1, filters: CandidateFiltersV1) -> bool:
        if filters.allowed_record_kinds and record.record_kind not in filters.allowed_record_kinds:
            return False
        if filters.allowed_source_ids and record.source_id not in filters.allowed_source_ids:
            return False
        if filters.required_entity_ids and not set(filters.required_entity_ids) & set(record.entity_ids):
            return False
        if record.record_id in filters.excluded_record_ids:
            return False
        instant = _instant(record.temporal)
        if instant is None:
            return filters.include_unknown_time
        if filters.occurred_after and instant < filters.occurred_after:
            return False
        if filters.occurred_before and instant > filters.occurred_before:
            return False
        return True

    @staticmethod
    def _contributions(
        request: CandidateRequestV1,
        record: CandidateRecordV1,
        applied: tuple[CandidateSignal, ...],
    ) -> tuple[tuple[CandidateSignalContributionV1, ...], float]:
        query_tokens = set(_tokens(request.content))
        candidate_tokens = set(_tokens(record.content))
        query_entities = set(request.entity_ids)
        candidate_entities = set(record.entity_ids)
        query_graph = set(request.graph_neighbor_ids)
        candidate_graph = set(record.graph_neighbor_ids)
        contributions: list[CandidateSignalContributionV1] = []
        raw: dict[CandidateSignal, float] = {}

        for signal in applied:
            score = 0.0
            signal_applied = True
            reason = "signal_scored"
            if signal is CandidateSignal.LEXICAL:
                score = _jaccard(query_tokens, candidate_tokens)
                if not query_tokens or not candidate_tokens:
                    signal_applied = False
                    reason = "content_unavailable"
            elif signal is CandidateSignal.VECTOR:
                query_vector = request.embedding or hashed_token_vector(request.content)
                candidate_vector = record.embedding or hashed_token_vector(record.content)
                score = _cosine(tuple(query_vector), tuple(candidate_vector))
                if not query_vector or not candidate_vector:
                    signal_applied = False
                    reason = "vector_unavailable_for_record"
            elif signal is CandidateSignal.ENTITY:
                score = _jaccard(query_entities, candidate_entities)
                if not query_entities or not candidate_entities:
                    signal_applied = False
                    reason = "entity_identity_unavailable"
            elif signal is CandidateSignal.TEMPORAL:
                temporal = _temporal_score(
                    request.temporal,
                    record.temporal,
                    window_days=request.temporal_window_days,
                )
                if temporal is None:
                    signal_applied = False
                    reason = "unknown_time_not_scored"
                else:
                    score = temporal
            elif signal is CandidateSignal.GRAPH:
                score = _jaccard(query_graph, candidate_graph)
                if not query_graph or not candidate_graph:
                    signal_applied = False
                    reason = "graph_neighborhood_unavailable"
            elif signal is CandidateSignal.SOURCE_DIVERSITY:
                if request.source_id is None or record.source_id is None:
                    signal_applied = False
                    reason = "source_identity_unavailable"
                else:
                    score = float(request.source_id != record.source_id)
                    reason = "independent_source" if score else "same_source"
            raw[signal] = score if signal_applied else 0.0
            contributions.append(
                CandidateSignalContributionV1(
                    signal=signal,
                    score=round(score, 8),
                    weight=SIGNAL_WEIGHTS[signal],
                    applied=signal_applied,
                    reason=reason,
                )
            )

        base_signals = set(applied) - {CandidateSignal.SOURCE_DIVERSITY}
        has_relationship_signal = any(raw.get(signal, 0.0) > 0 for signal in base_signals)
        total = sum(raw.get(signal, 0.0) * SIGNAL_WEIGHTS[signal] for signal in base_signals)
        if has_relationship_signal:
            total += raw.get(CandidateSignal.SOURCE_DIVERSITY, 0.0) * SIGNAL_WEIGHTS[CandidateSignal.SOURCE_DIVERSITY]
        if (
            query_entities
            and candidate_entities
            and query_entities.isdisjoint(candidate_entities)
            and (not query_graph or not candidate_graph or query_graph.isdisjoint(candidate_graph))
        ):
            # Canonical entity conflict plus no declared graph bridge is a
            # deterministic negative gate. Lexical similarity and coincident
            # timing alone cannot manufacture an association candidate.
            total = 0.0
        return tuple(contributions), round(min(1.0, total), 8)

    async def find_candidates(self, request: CandidateRequestV1) -> CandidateReceiptV1:
        requested = tuple(request.enabled_signals)
        available = set(self.snapshot.available_signals)
        applied = tuple(signal for signal in requested if signal in available)
        unavailable = tuple(signal for signal in requested if signal not in available)
        fallback_reasons = tuple(f"{signal.value}_index_unavailable" for signal in unavailable)

        product_filtered = 0
        explicit_filtered = 0
        zero_score_filtered = 0
        scored: list[tuple[CandidateRecordV1, tuple[CandidateSignalContributionV1, ...], float]] = []
        for record in self.snapshot.records:
            if record.product_id != request.product_id:
                product_filtered += 1
                continue
            if record.record_id == request.query_record_id:
                explicit_filtered += 1
                continue
            if not self._passes_filters(record, request.filters):
                explicit_filtered += 1
                continue
            contributions, score = self._contributions(request, record, applied)
            if score <= 0:
                zero_score_filtered += 1
                continue
            scored.append((record, contributions, score))

        scored.sort(
            key=lambda item: (
                -item[2],
                -next(
                    (part.score for part in item[1] if part.signal is CandidateSignal.ENTITY),
                    0.0,
                ),
                -next(
                    (part.score for part in item[1] if part.signal is CandidateSignal.GRAPH),
                    0.0,
                ),
                -next(
                    (part.score for part in item[1] if part.signal is CandidateSignal.TEMPORAL),
                    0.0,
                ),
                item[0].record_id,
            )
        )
        bounded = scored[: request.max_candidates]
        selected = bounded[: request.k]
        score_cap_omitted = len(scored) - len(bounded)
        return_cap_omitted = len(bounded) - len(selected)
        results = tuple(
            CandidateResultV1(
                record_id=record.record_id,
                rank=index,
                score=score,
                contributions=contributions,
                degraded_reasons=tuple(sorted({part.reason for part in contributions if not part.applied})),
            )
            for index, (record, contributions, score) in enumerate(selected, start=1)
        )
        return CandidateReceiptV1(
            request_id=str(request.request_id),
            snapshot_id=str(self.snapshot.snapshot_id),
            product_id=request.product_id,
            policy_version=request.policy_version,
            filters=request.filters,
            requested_k=request.k,
            max_candidates=request.max_candidates,
            temporal_window_days=request.temporal_window_days,
            index_versions=self.snapshot.index_versions,
            requested_signals=requested,
            applied_signals=applied,
            unavailable_signals=unavailable,
            fallback_reasons=fallback_reasons,
            records_in_snapshot=len(self.snapshot.records),
            product_filtered=product_filtered,
            explicit_filtered=explicit_filtered,
            zero_score_filtered=zero_score_filtered,
            candidates_scored=len(scored),
            score_cap_omitted=score_cap_omitted,
            return_cap_omitted=return_cap_omitted,
            candidates_returned=len(results),
            truncated=bool(score_cap_omitted or return_cap_omitted),
            candidates=results,
        )


def candidate_record_from_mapping(
    value: dict[str, Any],
    *,
    product_id: str,
    record_kind: str,
) -> CandidateRecordV1:
    """Adapt an existing Core record without allowing it to escape product scope."""
    content = value.get("content")
    content = str(content) if content is not None else None
    digest = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
    temporal = value.get("temporal") or {"precision": "unknown"}
    record_id = str(value.get("id") or value.get("record_id") or "")
    if not record_id:
        record_id = stable_id(
            "candidate_record",
            {"product_id": product_id, "record_kind": record_kind, "content_hash": digest},
        )
    return CandidateRecordV1(
        record_id=record_id,
        product_id=product_id,
        record_kind=record_kind,
        content_hash=digest,
        content=content,
        entity_ids=value.get("entity_ids") or (),
        temporal=temporal,
        source_id=value.get("source_id"),
        publisher_id=value.get("publisher_id"),
        graph_neighbor_ids=value.get("graph_neighbor_ids") or value.get("entity_ids") or (),
        facets=value.get("facets") or (),
        embedding=value.get("embedding") or (),
    )


def default_candidate_index_versions() -> dict[str, str]:
    return {
        CandidateSignal.LEXICAL.value: "ace.candidate.lexical-token-overlap/v1",
        CandidateSignal.VECTOR.value: "ace.candidate.hashed-token-vector/v1",
        CandidateSignal.ENTITY.value: "ace.candidate.entity-overlap/v1",
        CandidateSignal.TEMPORAL.value: "ace.candidate.temporal-window/v1",
        CandidateSignal.GRAPH.value: "ace.candidate.graph-neighborhood/v1",
        CandidateSignal.SOURCE_DIVERSITY.value: "ace.candidate.source-diversity/v1",
    }
