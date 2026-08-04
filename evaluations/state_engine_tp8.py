"""Frozen, provider-free TP8 scale dataset and acceptance-manifest helpers.

The generator emits adapter proposals, never Core-owned product or record IDs.
Core still validates each bounded manifest and derives authoritative identities.
No private or customer material is used.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.ingestion_contracts import (
    BoundedBatchManifestV1,
    CanonicalEntityV1,
    GroundedEventV1,
    GroundedRecordCountsV1,
    SourceClaimV1,
)

TP8_BENCHMARK_VERSION = "ace.grounded-state.tp8-benchmark/v1"
TP8_RESULT_VERSION = "ace.grounded-state.tp8-result/v1"
TP8_DATASET_GENERATOR_VERSION = "ace.grounded-state.tp8-synthetic-public-generator/v1"
UTC = timezone.utc


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TP8DatasetSpecV1(FrozenModel):
    generator_version: Literal["ace.grounded-state.tp8-synthetic-public-generator/v1"] = TP8_DATASET_GENERATOR_VERSION
    seed: int
    product_id: str
    foreign_product_id: str
    base_time: datetime
    source_count: int = Field(ge=1)
    entity_count: int = Field(ge=1)
    alias_count: int = Field(ge=0)
    claim_count: int = Field(ge=200_000)
    event_count: int = Field(ge=1)
    event_participant_count: int = Field(ge=1)
    relation_count: int = Field(ge=1)
    correction_count: int = Field(ge=1)
    contradiction_count: int = Field(ge=1)
    unknown_time_count: int = Field(ge=1)
    negative_control_count: int = Field(ge=1)
    daily_claim_counts: tuple[int, ...]
    records_per_item: int = Field(ge=1, le=200)
    items_per_manifest: int = Field(ge=1, le=200)
    raw_dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_manifest_count: int = Field(ge=1)
    expected_semantic_counts: GroundedRecordCountsV1

    @model_validator(mode="after")
    def reconcile(self):
        if sum(self.daily_claim_counts) != self.claim_count:
            raise ValueError("daily claim counts must reconcile the complete claim corpus")
        if self.correction_count >= self.claim_count:
            raise ValueError("corrections must extend a bounded subset of base claims")
        if self.expected_semantic_counts.claims != self.claim_count:
            raise ValueError("expected semantic claim count must equal claim_count")
        return self


class TP8BenchmarkManifestV1(FrozenModel):
    contract_version: Literal["ace.grounded-state.tp8-benchmark/v1"] = TP8_BENCHMARK_VERSION
    frozen_at: datetime
    benchmark_id: str
    dataset: TP8DatasetSpecV1
    reference_workload: dict[str, Any]
    reference_environment: dict[str, Any]
    process_topology: dict[str, Any]
    storage_adapters: tuple[dict[str, Any], ...]
    versions: dict[str, Any]
    deterministic_ordering: tuple[str, ...]
    failure_injections: tuple[dict[str, Any], ...]
    extension_compatibility: tuple[dict[str, Any], ...]
    provider_budget: dict[str, Any]
    budgets: dict[str, Any]
    thresholds: dict[str, Any]
    required_planes: tuple[str, ...]


def load_tp8_manifest(path: str | Path) -> TP8BenchmarkManifestV1:
    return TP8BenchmarkManifestV1.model_validate_json(Path(path).read_text())


def _common(*, spec: TP8DatasetSpecV1, source_index: int, local_id: str, version: str = "v1") -> dict[str, Any]:
    return {
        "source_external_id": f"tp8-public-source-{source_index:05d}",
        "source_version": version,
        "local_id": local_id,
        "publisher_id": f"tp8-public-publisher-{source_index % 17:02d}",
        "local_reference": f"tp8-synthetic:{source_index:05d}/{local_id}",
        "published_at": None,
        "ingested_at": spec.base_time.isoformat(),
        "extracted_at": None,
        "extraction": None,
        "source_span": None,
        "degraded_reasons": (),
    }


def _entity_proposal(spec: TP8DatasetSpecV1, index: int) -> dict[str, Any]:
    return {
        "kind": "entity",
        **_common(spec=spec, source_index=index % spec.source_count, local_id=f"entity-{index:05d}"),
        "external_id": f"tp8-public-entity-{index:05d}",
        "canonical_name": f"Synthetic Public Entity {index:05d}",
        "entity_type": "synthetic_organization",
        "attributes": {"public_safe": True, "partition": index % 32},
        "temporal": {"precision": "unknown"},
    }


@lru_cache(maxsize=20_000)
def _entity_id(spec: TP8DatasetSpecV1, index: int) -> str:
    raw = dict(_entity_proposal(spec, index))
    raw.pop("kind")
    raw["product_id"] = spec.product_id
    raw["content_hash"] = canonical_hash(
        {
            "canonical_name": raw["canonical_name"],
            "entity_type": raw["entity_type"],
            "attributes": raw["attributes"],
        }
    )
    return str(CanonicalEntityV1.model_validate(raw).record_id)


def _source_proposal(spec: TP8DatasetSpecV1, index: int) -> dict[str, Any]:
    return {
        "kind": "source",
        **_common(spec=spec, source_index=index, local_id=f"source-{index:05d}"),
        "external_id": f"tp8-public-source-{index:05d}",
        "content_hash": canonical_hash({"source": index, "seed": spec.seed}),
        "source_kind": "tp8-synthetic-public",
        "title": f"Synthetic public source {index:05d}",
        "content": None,
        "temporal": {"precision": "unknown"},
    }


def _claim_day(spec: TP8DatasetSpecV1, index: int) -> int:
    cursor = 0
    for day, count in enumerate(spec.daily_claim_counts):
        cursor += count
        if index < cursor:
            return day
    return len(spec.daily_claim_counts) - 1


def _claim_temporal(spec: TP8DatasetSpecV1, index: int) -> dict[str, Any]:
    if index < spec.unknown_time_count:
        return {"precision": "unknown"}
    day = _claim_day(spec, index)
    occurred = spec.base_time + timedelta(days=day, seconds=index % 86_400)
    if index % 20 == 0:
        return {
            "precision": "range",
            "valid_from": occurred.isoformat(),
            "valid_to": (occurred + timedelta(hours=6)).isoformat(),
        }
    if index % 20 == 1:
        return {
            "precision": "inferred",
            "occurred_at": occurred.isoformat(),
            "inferred_from": [f"tp8-public-time-rule:{index % 7}"],
        }
    return {"precision": "exact", "occurred_at": occurred.isoformat()}


def _event_proposal(spec: TP8DatasetSpecV1, index: int) -> dict[str, Any]:
    source_index = index % spec.source_count
    occurred = spec.base_time + timedelta(days=index % len(spec.daily_claim_counts), seconds=index)
    return {
        "kind": "event",
        **_common(spec=spec, source_index=source_index, local_id=f"event-{index:05d}"),
        "external_id": f"tp8-public-event-{index:05d}",
        "event_type": "synthetic_public_event",
        "description": f"Synthetic public event {index:05d} occurred.",
        "temporal": {"precision": "exact", "occurred_at": occurred.isoformat()},
    }


@lru_cache(maxsize=20_000)
def _event_id(spec: TP8DatasetSpecV1, index: int) -> str:
    raw = dict(_event_proposal(spec, index))
    raw.pop("kind")
    raw["product_id"] = spec.product_id
    raw["content_hash"] = hashlib.sha256(raw["description"].encode()).hexdigest()
    return str(GroundedEventV1.model_validate(raw).record_id)


def _base_claim_proposal(spec: TP8DatasetSpecV1, index: int) -> dict[str, Any]:
    entity_index = index % spec.entity_count
    contradiction = index < spec.contradiction_count
    negative_control = spec.contradiction_count <= index < spec.contradiction_count + spec.negative_control_count
    if contradiction:
        predicate = "synthetic_operating_state"
        value: Any = "active" if index % 2 == 0 else "inactive"
        text = f"Synthetic source reports entity {entity_index:05d} operating state {value}."
    elif negative_control:
        predicate = "synthetic_negative_control"
        value = f"unrelated-{index:06d}"
        text = f"Negative control {index:06d} is intentionally unrelated to the benchmark query."
    else:
        predicate = "synthetic_capacity"
        value = index % 101
        text = f"Synthetic source reports entity {entity_index:05d} capacity value {value}."
    return {
        "kind": "claim",
        **_common(
            spec=spec,
            source_index=index % spec.source_count,
            local_id=f"claim-{index:06d}",
        ),
        "external_id": f"tp8-public-claim-{index:06d}",
        "claim_text": text,
        "entity_ids": (_entity_id(spec, entity_index),),
        "predicate": predicate,
        "value": value,
        "confidence": 0.8,
        "temporal": _claim_temporal(spec, index),
    }


def _correction_proposal(spec: TP8DatasetSpecV1, correction_index: int) -> dict[str, Any]:
    target = correction_index
    entity_index = target % spec.entity_count
    text = f"Correction: synthetic entity {entity_index:05d} capacity value is {(target + 1) % 101}."
    return {
        "kind": "claim",
        **_common(
            spec=spec,
            source_index=target % spec.source_count,
            local_id=f"claim-{target:06d}",
            version="v2",
        ),
        "external_id": f"tp8-public-claim-{target:06d}",
        "claim_text": text,
        "entity_ids": (_entity_id(spec, entity_index),),
        "predicate": "synthetic_capacity",
        "value": (target + 1) % 101,
        "confidence": 1.0,
        "temporal": _claim_temporal(spec, target),
        "degraded_reasons": ("source_correction",),
    }


@lru_cache(maxsize=100_000)
def _claim_id(spec: TP8DatasetSpecV1, index: int) -> str:
    raw = dict(_base_claim_proposal(spec, index))
    raw.pop("kind")
    raw["product_id"] = spec.product_id
    raw["content_hash"] = hashlib.sha256(raw["claim_text"].encode()).hexdigest()
    return str(SourceClaimV1.model_validate(raw).record_id)


def iter_dataset_records(spec: TP8DatasetSpecV1) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield the complete frozen initial-load proposal stream in stable family order."""
    for index in range(spec.source_count):
        yield "sources", _source_proposal(spec, index)
    for index in range(spec.entity_count):
        yield "entities", _entity_proposal(spec, index)
    for index in range(spec.alias_count):
        entity_index = index % spec.entity_count
        surface = f"SPE-{entity_index:05d}"
        yield (
            "aliases",
            {
                "kind": "alias",
                **_common(spec=spec, source_index=index % spec.source_count, local_id=f"alias-{index:05d}"),
                "external_id": f"tp8-public-alias-{index:05d}",
                "raw_surface_form": surface,
                "entity_id": _entity_id(spec, entity_index),
                "language": "en",
                "temporal": {"precision": "unknown"},
            },
        )
    for index in range(spec.event_count):
        yield "events", _event_proposal(spec, index)
    for index in range(spec.event_participant_count):
        source_index = index % spec.source_count
        occurred = spec.base_time + timedelta(days=index % len(spec.daily_claim_counts), seconds=index)
        yield (
            "event_participants",
            {
                "kind": "event_participant",
                **_common(
                    spec=spec,
                    source_index=source_index,
                    local_id=f"participant-{index:05d}",
                ),
                "external_id": f"tp8-public-participant-{index:05d}",
                "event_id": _event_id(spec, index % spec.event_count),
                "entity_id": _entity_id(spec, index % spec.entity_count),
                "role": "participant",
                "raw_surface_form": f"SPE-{index % spec.entity_count:05d}",
                "temporal": {"precision": "exact", "occurred_at": occurred.isoformat()},
            },
        )
    base_count = spec.claim_count - spec.correction_count
    for index in range(base_count):
        yield "claims", _base_claim_proposal(spec, index)
    for index in range(spec.correction_count):
        yield "corrections", _correction_proposal(spec, index)
    for index in range(spec.relation_count):
        entity_index = index % spec.entity_count
        claim_index = index % base_count
        yield (
            "relations",
            {
                "kind": "relation",
                **_common(spec=spec, source_index=index % spec.source_count, local_id=f"relation-{index:06d}"),
                "external_id": f"tp8-public-relation-{index:06d}",
                "relation": "mentions",
                "subject_id": _claim_id(spec, claim_index),
                "object_id": _entity_id(spec, entity_index),
                "basis": "Synthetic public claim names the deterministically mapped entity.",
                "temporal": _claim_temporal(spec, claim_index),
            },
        )


def _manifest_chunks(
    spec: TP8DatasetSpecV1,
    family: str,
    records: Sequence[dict[str, Any]],
    *,
    family_ordinal: int,
) -> Iterator[BoundedBatchManifestV1]:
    per_item = min(spec.records_per_item, 200)
    items = [
        {
            "item_key": f"tp8-{family}-{item_index:06d}",
            "records": records[start : start + per_item],
        }
        for item_index, start in enumerate(range(0, len(records), per_item))
    ]
    for manifest_index, start in enumerate(range(0, len(items), spec.items_per_manifest)):
        ordinal = family_ordinal * 10_000 + manifest_index
        yield BoundedBatchManifestV1(
            product_id=spec.product_id,
            manifest_external_id=f"tp8-{family}-{manifest_index:04d}",
            adapter_id="tp8-synthetic-public-reference",
            adapter_version="v1",
            extraction_run_id=f"tp8-frozen-seed-{spec.seed}",
            submitted_at=spec.base_time + timedelta(seconds=ordinal),
            chunk_size=50,
            items=tuple(items[start : start + spec.items_per_manifest]),
        )


def _one_manifest(
    spec: TP8DatasetSpecV1,
    *,
    family: str,
    records: Sequence[dict[str, Any]],
    family_ordinal: int,
    manifest_index: int,
    item_offset: int,
) -> BoundedBatchManifestV1:
    items = tuple(
        {
            "item_key": f"tp8-{family}-{item_offset + item_index:06d}",
            "records": records[start : start + spec.records_per_item],
        }
        for item_index, start in enumerate(range(0, len(records), spec.records_per_item))
    )
    ordinal = family_ordinal * 10_000 + manifest_index
    return BoundedBatchManifestV1(
        product_id=spec.product_id,
        manifest_external_id=f"tp8-{family}-{manifest_index:04d}",
        adapter_id="tp8-synthetic-public-reference",
        adapter_version="v1",
        extraction_run_id=f"tp8-frozen-seed-{spec.seed}",
        submitted_at=spec.base_time + timedelta(seconds=ordinal),
        chunk_size=50,
        items=items,
    )


def iter_dataset_manifests(spec: TP8DatasetSpecV1) -> Iterator[BoundedBatchManifestV1]:
    """Stream validated manifests without materializing the 200k-claim corpus."""
    current_family: str | None = None
    records: list[dict[str, Any]] = []
    family_ordinal = 0
    manifest_index = 0
    item_offset = 0
    records_per_manifest = spec.records_per_item * spec.items_per_manifest

    def flush() -> BoundedBatchManifestV1:
        return _one_manifest(
            spec,
            family=str(current_family),
            records=records,
            family_ordinal=family_ordinal,
            manifest_index=manifest_index,
            item_offset=item_offset,
        )

    for family, record in iter_dataset_records(spec):
        if current_family is not None and family != current_family:
            if records:
                yield flush()
            family_ordinal += 1
            manifest_index = 0
            item_offset = 0
            records = []
        current_family = family
        records.append(record)
        if len(records) == records_per_manifest:
            yield flush()
            item_offset += len(records) // spec.records_per_item
            manifest_index += 1
            records = []
    if current_family is not None:
        if records:
            yield flush()


def compute_dataset_hashes(spec: TP8DatasetSpecV1) -> tuple[str, str, int]:
    raw = hashlib.sha256()
    for family, record in iter_dataset_records(spec):
        raw.update(
            json.dumps(
                {"family": family, "record": record},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        )
        raw.update(b"\n")
    manifest_ids = [manifest.manifest_id() for manifest in iter_dataset_manifests(spec)]
    return raw.hexdigest(), canonical_hash(manifest_ids), len(manifest_ids)


def dataset_record_counts(spec: TP8DatasetSpecV1) -> GroundedRecordCountsV1:
    return GroundedRecordCountsV1(
        sources=spec.source_count,
        entities=spec.entity_count,
        aliases=spec.alias_count,
        claims=spec.claim_count,
        events=spec.event_count,
        event_participants=spec.event_participant_count,
        relations=spec.relation_count,
    )


def manifests_for_claim_window(
    spec: TP8DatasetSpecV1,
    *,
    start: int,
    count: int,
    product_id: str | None = None,
    family: str = "sustained",
) -> Iterable[BoundedBatchManifestV1]:
    """Generate a deterministic post-load claim window for sustained-ingestion proof."""
    if start < spec.claim_count or count < 1:
        raise ValueError("sustained windows must follow the frozen initial claim range")
    effective = spec.model_copy(update={"product_id": product_id or spec.product_id})
    records = [_base_claim_proposal(effective, index) for index in range(start, start + count)]
    return tuple(_manifest_chunks(effective, family, records, family_ordinal=9_000))
