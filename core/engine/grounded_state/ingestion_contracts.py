"""Immutable TP2 contracts for the grounded temporal evidence substrate.

These contracts are deliberately persistence-facing.  Domain extensions may
propose source-specific extraction output, but Core injects product scope and
derives every authoritative identity before a record reaches this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.contracts import (
    MAX_REFS,
    ExtractionProvenanceV1,
    FrozenContract,
    TemporalScopeV1,
    canonical_hash,
    stable_id,
)

SOURCE_RECORD_VERSION = "ace.grounded-state.source-record/v1"
CANONICAL_ENTITY_VERSION = "ace.grounded-state.canonical-entity/v1"
RAW_ALIAS_VERSION = "ace.grounded-state.raw-alias/v1"
SOURCE_CLAIM_VERSION = "ace.grounded-state.source-claim/v1"
GROUNDED_EVENT_VERSION = "ace.grounded-state.event/v1"
EVENT_PARTICIPANT_VERSION = "ace.grounded-state.event-participant/v1"
EVIDENCE_RELATION_VERSION = "ace.grounded-state.evidence-relation/v1"
EXTRACTION_FAILURE_VERSION = "ace.grounded-state.extraction-failure/v1"
SUPERSESSION_LINEAGE_VERSION = "ace.grounded-state.supersession-lineage/v1"
INGESTION_MANIFEST_VERSION = "ace.grounded-state.ingestion-manifest/v1"
ITEM_RECEIPT_VERSION = "ace.grounded-state.ingestion-item-receipt/v1"
BATCH_RECEIPT_VERSION = "ace.grounded-state.batch-ingestion-receipt/v1"
INGESTION_PROCESSOR_VERSION = "ace.grounded-state.ingestion-processor/v1"
INGESTION_SCHEMA_VERSION = "grounded-state-schema/v1"

MAX_BATCH_ITEMS = 200
MAX_RECORDS_PER_ITEM = 200
MAX_DEGRADED_REASONS = 20
MAX_REASON_CHARS = 1_000
_PRODUCT_ID = re.compile(r"^product:[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_GROUNDED_REF_PREFIXES = (
    "grounded_source:",
    "grounded_entity:",
    "grounded_alias:",
    "grounded_claim:",
    "grounded_event:",
    "grounded_event_participant:",
    "grounded_evidence_relation:",
    "grounded_extraction_failure:",
)


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value


def _product(value: str) -> str:
    if not _PRODUCT_ID.fullmatch(value):
        raise ValueError("product_id must be a bounded product record identifier")
    return value


def _token(value: str, name: str, limit: int = 240) -> str:
    if not value or value != value.strip() or len(value) > limit or any(char.isspace() for char in value):
        raise ValueError(f"{name} must be a bounded stable token")
    return value


def _bounded_strings(value: Any, *, name: str, limit: int = MAX_REFS, item_limit: int = 500) -> tuple[str, ...]:
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


def _bounded_json(value: Any, *, name: str, max_chars: int = 16_000) -> Any:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be JSON serializable") from exc
    if len(encoded) > max_chars:
        raise ValueError(f"{name} exceeds the {max_chars}-character bound")
    return value


def _natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple((0, int(part)) if part.isdigit() else (1, part.lower()) for part in re.split(r"(\d+)", value))


def _manifest_item_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    records = item.get("records") if isinstance(item.get("records"), (list, tuple)) else ()
    coordinates = sorted(
        (
            str(record.get("source_external_id") or record.get("source_id") or ""),
            str(record.get("local_id") or ""),
            _natural_key(str(record.get("source_version") or "")),
            str(record.get("kind") or record.get("record_kind") or ""),
        )
        for record in records
        if isinstance(record, dict)
    )
    return (coordinates[0] if coordinates else ("", "", (), ""), canonical_hash(item))


class GroundedRecordKind(StrEnum):
    SOURCE = "source"
    ENTITY = "entity"
    ALIAS = "alias"
    CLAIM = "claim"
    EVENT = "event"
    EVENT_PARTICIPANT = "event_participant"
    RELATION = "relation"
    EXTRACTION_FAILURE = "extraction_failure"


class EvidenceRelationKind(StrEnum):
    MENTIONS = "mentions"
    PARTICIPATES_IN = "participates_in"
    PRECEDES = "precedes"
    REACTS_TO = "reacts_to"
    CO_OCCURS = "co_occurs"


class IngestionDisposition(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    SUPERSEDING = "superseding"
    REJECTED = "rejected"
    FAILED = "failed"


class GroundedSemanticRecordV1(FrozenContract):
    """Common immutable provenance and lifecycle fields for semantic records."""

    record_kind: ClassVar[GroundedRecordKind]
    identity_prefix: ClassVar[str]

    contract_version: str
    record_id: str | None = None
    product_id: str
    external_id: str = Field(min_length=1, max_length=500)
    source_external_id: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=240)
    local_id: str = Field(min_length=1, max_length=240)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    publisher_id: str = Field(min_length=1, max_length=240)
    source_uri: str | None = Field(default=None, max_length=2_000)
    local_reference: str | None = Field(default=None, max_length=500)
    temporal: TemporalScopeV1 = Field(default_factory=TemporalScopeV1)
    published_at: datetime | None = None
    ingested_at: datetime
    extracted_at: datetime | None = None
    extraction: ExtractionProvenanceV1 | None = None
    source_span: str | None = Field(default=None, max_length=1_000)
    idempotency_key: str | None = None
    supersedes: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_DEGRADED_REASONS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("published_at", "ingested_at", "extracted_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator("supersedes", mode="before")
    @classmethod
    def normalize_supersedes(cls, value: Any) -> tuple[str, ...]:
        refs = _bounded_strings(value, name="supersedes", item_limit=240)
        if any(not ref.startswith(_GROUNDED_REF_PREFIXES) for ref in refs):
            raise ValueError("supersedes must contain Core grounded-state identities")
        return refs

    @field_validator("degraded_reasons", mode="before")
    @classmethod
    def normalize_degraded_reasons(cls, value: Any) -> tuple[str, ...]:
        return _bounded_strings(
            value,
            name="degraded_reasons",
            limit=MAX_DEGRADED_REASONS,
            item_limit=MAX_REASON_CHARS,
        )

    def identity_material(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "product_id": self.product_id,
            "external_id": self.external_id,
            "source_external_id": self.source_external_id,
            "source_version": self.source_version,
            "record_kind": self.record_kind.value,
            "content_hash": self.content_hash,
            "local_id": self.local_id,
            "publisher_id": self.publisher_id,
            "source_uri": self.source_uri,
            "local_reference": self.local_reference,
            "temporal": self.temporal.model_dump(mode="json"),
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "extraction": self.extraction.model_dump(mode="json") if self.extraction else None,
            "source_span": self.source_span,
            "degraded_reasons": self.degraded_reasons,
        }

    def expected_record_id(self) -> str:
        return stable_id(self.identity_prefix, self.identity_material())

    def expected_idempotency_key(self) -> str:
        return stable_id("grounded_idempotency", self.identity_material())

    @model_validator(mode="after")
    def validate_common_semantics(self) -> Self:
        if bool(self.source_uri) == bool(self.local_reference):
            raise ValueError("exactly one of source_uri or local_reference is required")
        if self.extracted_at is None and self.extraction is not None:
            raise ValueError("extraction provenance requires extracted_at")
        if self.extracted_at is not None and self.extraction is None:
            raise ValueError("extracted_at requires extraction provenance")
        if self.extraction is not None and self.source_span is None and self.extraction.source_span is None:
            raise ValueError("extracted semantic records require a bounded source span")
        expected_record_id = self.expected_record_id()
        expected_key = self.expected_idempotency_key()
        if self.record_id is not None and self.record_id != expected_record_id:
            raise ValueError("record_id does not match Core deterministic identity material")
        if self.idempotency_key is not None and self.idempotency_key != expected_key:
            raise ValueError("idempotency_key does not match Core deterministic identity material")
        object.__setattr__(self, "record_id", expected_record_id)
        object.__setattr__(self, "idempotency_key", expected_key)
        if expected_record_id in self.supersedes:
            raise ValueError("a grounded-state record cannot supersede itself")
        return self


class SourceRecordV1(GroundedSemanticRecordV1):
    contract_version: Literal["ace.grounded-state.source-record/v1"] = SOURCE_RECORD_VERSION
    record_kind: ClassVar[GroundedRecordKind] = GroundedRecordKind.SOURCE
    identity_prefix: ClassVar[str] = "grounded_source"
    source_kind: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=1_000)
    content: str | None = Field(default=None, max_length=8_000)

    def identity_material(self) -> dict[str, Any]:
        return {**super().identity_material(), "source_kind": self.source_kind, "title": self.title}

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if self.content is not None and hashlib.sha256(self.content.encode()).hexdigest() != self.content_hash:
            raise ValueError("source content_hash must equal the supplied content digest")
        return self


class CanonicalEntityV1(GroundedSemanticRecordV1):
    contract_version: Literal["ace.grounded-state.canonical-entity/v1"] = CANONICAL_ENTITY_VERSION
    record_kind: ClassVar[GroundedRecordKind] = GroundedRecordKind.ENTITY
    identity_prefix: ClassVar[str] = "grounded_entity"
    canonical_name: str = Field(min_length=1, max_length=500)
    entity_type: str = Field(min_length=1, max_length=120)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(value, name="entity attributes")

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        material = {
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "attributes": self.attributes,
        }
        if canonical_hash(material) != self.content_hash:
            raise ValueError("entity content_hash must equal its canonical semantic content digest")
        return self


class RawAliasV1(GroundedSemanticRecordV1):
    contract_version: Literal["ace.grounded-state.raw-alias/v1"] = RAW_ALIAS_VERSION
    record_kind: ClassVar[GroundedRecordKind] = GroundedRecordKind.ALIAS
    identity_prefix: ClassVar[str] = "grounded_alias"
    raw_surface_form: str = Field(min_length=1, max_length=500)
    entity_id: str = Field(min_length=1, max_length=240)
    language: str | None = Field(default=None, max_length=32)

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        if not value.startswith("grounded_entity:"):
            raise ValueError("aliases must bind a Core grounded_entity identity")
        return value

    def identity_material(self) -> dict[str, Any]:
        return {**super().identity_material(), "entity_id": self.entity_id, "language": self.language}

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if hashlib.sha256(self.raw_surface_form.encode()).hexdigest() != self.content_hash:
            raise ValueError("alias content_hash must equal the raw surface-form digest")
        return self


class SourceClaimV1(GroundedSemanticRecordV1):
    contract_version: Literal["ace.grounded-state.source-claim/v1"] = SOURCE_CLAIM_VERSION
    record_kind: ClassVar[GroundedRecordKind] = GroundedRecordKind.CLAIM
    identity_prefix: ClassVar[str] = "grounded_claim"
    claim_text: str = Field(min_length=1, max_length=8_000)
    entity_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    predicate: str | None = Field(default=None, max_length=160)
    value: Any = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    def identity_material(self) -> dict[str, Any]:
        return {
            **super().identity_material(),
            "entity_ids": self.entity_ids,
            "predicate": self.predicate,
            "value": self.value,
            "confidence": self.confidence,
        }

    @field_validator("entity_ids", mode="before")
    @classmethod
    def normalize_entity_ids(cls, value: Any) -> tuple[str, ...]:
        refs = _bounded_strings(value, name="entity_ids", item_limit=240)
        if any(not ref.startswith("grounded_entity:") for ref in refs):
            raise ValueError("claims may reference only Core grounded_entity identities")
        return refs

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: Any) -> Any:
        return _bounded_json(value, name="claim value")

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if hashlib.sha256(self.claim_text.encode()).hexdigest() != self.content_hash:
            raise ValueError("claim content_hash must equal the claim text digest")
        return self


class GroundedEventV1(GroundedSemanticRecordV1):
    contract_version: Literal["ace.grounded-state.event/v1"] = GROUNDED_EVENT_VERSION
    record_kind: ClassVar[GroundedRecordKind] = GroundedRecordKind.EVENT
    identity_prefix: ClassVar[str] = "grounded_event"
    event_type: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=8_000)

    def identity_material(self) -> dict[str, Any]:
        return {**super().identity_material(), "event_type": self.event_type}

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if hashlib.sha256(self.description.encode()).hexdigest() != self.content_hash:
            raise ValueError("event content_hash must equal the event description digest")
        return self


class EventParticipantV1(GroundedSemanticRecordV1):
    contract_version: Literal["ace.grounded-state.event-participant/v1"] = EVENT_PARTICIPANT_VERSION
    record_kind: ClassVar[GroundedRecordKind] = GroundedRecordKind.EVENT_PARTICIPANT
    identity_prefix: ClassVar[str] = "grounded_event_participant"
    event_id: str = Field(min_length=1, max_length=240)
    entity_id: str = Field(min_length=1, max_length=240)
    role: str = Field(min_length=1, max_length=160)
    raw_surface_form: str | None = Field(default=None, max_length=500)

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str) -> str:
        if not value.startswith("grounded_event:"):
            raise ValueError("event participants require a Core grounded_event identity")
        return value

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        if not value.startswith("grounded_entity:"):
            raise ValueError("event participants require a Core grounded_entity identity")
        return value

    def identity_material(self) -> dict[str, Any]:
        return {
            **super().identity_material(),
            "event_id": self.event_id,
            "entity_id": self.entity_id,
            "role": self.role,
            "raw_surface_form": self.raw_surface_form,
        }

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        material = {
            "event_id": self.event_id,
            "entity_id": self.entity_id,
            "role": self.role,
            "raw_surface_form": self.raw_surface_form,
        }
        if canonical_hash(material) != self.content_hash:
            raise ValueError("participant content_hash must equal its canonical semantic content digest")
        return self


class EvidenceRelationV1(GroundedSemanticRecordV1):
    contract_version: Literal["ace.grounded-state.evidence-relation/v1"] = EVIDENCE_RELATION_VERSION
    record_kind: ClassVar[GroundedRecordKind] = GroundedRecordKind.RELATION
    identity_prefix: ClassVar[str] = "grounded_evidence_relation"
    relation: EvidenceRelationKind
    subject_id: str = Field(min_length=1, max_length=240)
    object_id: str = Field(min_length=1, max_length=240)
    basis: str = Field(min_length=1, max_length=1_000)

    @field_validator("subject_id", "object_id")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        if not value.startswith(_GROUNDED_REF_PREFIXES):
            raise ValueError("evidence relation endpoints must be Core grounded-state identities")
        return value

    def identity_material(self) -> dict[str, Any]:
        return {
            **super().identity_material(),
            "relation": self.relation.value,
            "subject_id": self.subject_id,
            "object_id": self.object_id,
            "basis": self.basis,
        }

    @model_validator(mode="after")
    def prohibit_causal_self_edges(self) -> Self:
        if self.subject_id == self.object_id:
            raise ValueError("evidence relations require distinct endpoints")
        material = {
            "relation": self.relation.value,
            "subject_id": self.subject_id,
            "object_id": self.object_id,
            "basis": self.basis,
        }
        if canonical_hash(material) != self.content_hash:
            raise ValueError("relation content_hash must equal its canonical semantic content digest")
        return self


class ExtractionFailureV1(GroundedSemanticRecordV1):
    contract_version: Literal["ace.grounded-state.extraction-failure/v1"] = EXTRACTION_FAILURE_VERSION
    record_kind: ClassVar[GroundedRecordKind] = GroundedRecordKind.EXTRACTION_FAILURE
    identity_prefix: ClassVar[str] = "grounded_extraction_failure"
    failure_code: str = Field(min_length=1, max_length=120)
    failure_message: str = Field(min_length=1, max_length=1_000)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    retryable: bool = False

    def identity_material(self) -> dict[str, Any]:
        return {
            **super().identity_material(),
            "failure_code": self.failure_code,
            "input_hash": self.input_hash,
            "retryable": self.retryable,
        }

    @model_validator(mode="after")
    def require_degraded_reason(self) -> Self:
        if not self.degraded_reasons:
            raise ValueError("extraction failures require a bounded degraded reason")
        if self.content_hash != self.input_hash:
            raise ValueError("extraction failure content_hash must preserve the failed input hash")
        return self


RECORD_MODEL_BY_KIND: dict[GroundedRecordKind, type[GroundedSemanticRecordV1]] = {
    GroundedRecordKind.SOURCE: SourceRecordV1,
    GroundedRecordKind.ENTITY: CanonicalEntityV1,
    GroundedRecordKind.ALIAS: RawAliasV1,
    GroundedRecordKind.CLAIM: SourceClaimV1,
    GroundedRecordKind.EVENT: GroundedEventV1,
    GroundedRecordKind.EVENT_PARTICIPANT: EventParticipantV1,
    GroundedRecordKind.RELATION: EvidenceRelationV1,
    GroundedRecordKind.EXTRACTION_FAILURE: ExtractionFailureV1,
}


class GroundedIngestionItemV1(FrozenContract):
    """One adapter output bundle; nested record proposals remain item-local raw JSON."""

    item_key: str = Field(min_length=1, max_length=240)
    records: tuple[dict[str, Any], ...] = Field(min_length=1, max_length=MAX_RECORDS_PER_ITEM)

    @field_validator("item_key")
    @classmethod
    def validate_item_key(cls, value: str) -> str:
        return _token(value, "item_key")

    @field_validator("records", mode="before")
    @classmethod
    def normalize_records(cls, value: Any) -> tuple[dict[str, Any], ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("records must be a bounded list")
        records = tuple(value)
        if not records or len(records) > MAX_RECORDS_PER_ITEM or any(not isinstance(item, dict) for item in records):
            raise ValueError("records must contain one or more bounded objects")
        _bounded_json(records, name="item records", max_chars=1_000_000)
        return tuple(sorted(records, key=canonical_hash))


class BoundedBatchManifestV1(FrozenContract):
    """Product-owned bounded manifest whose items are validated independently."""

    contract_version: Literal["ace.grounded-state.ingestion-manifest/v1"] = INGESTION_MANIFEST_VERSION
    product_id: str
    manifest_external_id: str = Field(min_length=1, max_length=240)
    adapter_id: str = Field(min_length=1, max_length=240)
    adapter_version: str = Field(min_length=1, max_length=120)
    extraction_run_id: str = Field(min_length=1, max_length=240)
    submitted_at: datetime
    chunk_size: int = Field(default=20, ge=1, le=50)
    items: tuple[dict[str, Any], ...] = Field(min_length=1, max_length=MAX_BATCH_ITEMS)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("manifest_external_id", "adapter_id", "adapter_version", "extraction_run_id")
    @classmethod
    def validate_tokens(cls, value: str, info) -> str:
        return _token(value, info.field_name)

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, value: datetime) -> datetime:
        return _aware(value, "submitted_at")

    @field_validator("items", mode="before")
    @classmethod
    def normalize_items(cls, value: Any) -> tuple[dict[str, Any], ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("items must be a bounded list")
        items = tuple(value)
        if not items or len(items) > MAX_BATCH_ITEMS or any(not isinstance(item, dict) for item in items):
            raise ValueError("items must contain one or more bounded objects")
        _bounded_json(items, name="manifest items", max_chars=4_000_000)
        normalized: list[dict[str, Any]] = []
        for item in items:
            try:
                validated = GroundedIngestionItemV1.model_validate(item)
            except ValueError:
                normalized.append(item)
            else:
                normalized.append(validated.model_dump(mode="json"))
        return tuple(sorted(normalized, key=_manifest_item_sort_key))

    def manifest_hash(self) -> str:
        return canonical_hash(
            {
                "contract_version": self.contract_version,
                "product_id": self.product_id,
                "manifest_external_id": self.manifest_external_id,
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "extraction_run_id": self.extraction_run_id,
                "items": self.items,
            }
        )

    def manifest_id(self) -> str:
        return f"grounded_ingestion_manifest:{self.manifest_hash()[:32]}"


class GroundedRecordCountsV1(FrozenContract):
    sources: int = Field(default=0, ge=0)
    entities: int = Field(default=0, ge=0)
    aliases: int = Field(default=0, ge=0)
    claims: int = Field(default=0, ge=0)
    events: int = Field(default=0, ge=0)
    event_participants: int = Field(default=0, ge=0)
    relations: int = Field(default=0, ge=0)
    extraction_failures: int = Field(default=0, ge=0)

    def total(self) -> int:
        return sum(self.model_dump().values())


class IngestionDispositionCountsV1(FrozenContract):
    inputs: int = Field(default=0, ge=0)
    accepted: int = Field(default=0, ge=0)
    duplicate: int = Field(default=0, ge=0)
    superseding: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    persisted: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def reconcile(self) -> Self:
        accounted = self.accepted + self.duplicate + self.superseding + self.rejected + self.failed
        if accounted != self.inputs:
            raise ValueError("ingestion counts must reconcile every input exactly once")
        if self.persisted > self.accepted + self.superseding:
            raise ValueError("persisted count cannot exceed accepted plus superseding inputs")
        return self


class RecordIngestionResultV1(FrozenContract):
    ordinal: int = Field(ge=0)
    kind: GroundedRecordKind | None = None
    disposition: IngestionDisposition
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    record_id: str | None = Field(default=None, max_length=240)
    reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_DEGRADED_REASONS)

    @field_validator("reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value: Any) -> tuple[str, ...]:
        return _bounded_strings(
            value,
            name="record result reasons",
            limit=MAX_DEGRADED_REASONS,
            item_limit=MAX_REASON_CHARS,
        )

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.disposition in {
            IngestionDisposition.ACCEPTED,
            IngestionDisposition.DUPLICATE,
            IngestionDisposition.SUPERSEDING,
        } and (self.kind is None or self.record_id is None):
            raise ValueError("successful record results require kind and stable record identity")
        if self.disposition in {IngestionDisposition.REJECTED, IngestionDisposition.FAILED} and not self.reasons:
            raise ValueError("rejected and failed record results require a reason")
        return self


class SupersessionLineageV1(FrozenContract):
    """One append-only, arrival-order-independent source-version lineage edge."""

    contract_version: Literal["ace.grounded-state.supersession-lineage/v1"] = SUPERSESSION_LINEAGE_VERSION
    lineage_id: str | None = None
    product_id: str
    record_kind: GroundedRecordKind
    successor_id: str = Field(min_length=1, max_length=240)
    predecessor_id: str = Field(min_length=1, max_length=240)
    source_external_id: str = Field(min_length=1, max_length=500)
    local_id: str = Field(min_length=1, max_length=240)
    policy_version: Literal["ace.grounded-state.supersession-policy/v1"] = "ace.grounded-state.supersession-policy/v1"

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @model_validator(mode="after")
    def validate_lineage(self) -> Self:
        expected_prefix = RECORD_MODEL_BY_KIND[self.record_kind].identity_prefix + ":"
        if not self.successor_id.startswith(expected_prefix) or not self.predecessor_id.startswith(expected_prefix):
            raise ValueError("supersession endpoints must share the declared grounded record kind")
        if self.successor_id == self.predecessor_id:
            raise ValueError("a supersession edge requires distinct records")
        expected = stable_id(
            "grounded_supersession",
            {
                "contract_version": self.contract_version,
                "product_id": self.product_id,
                "record_kind": self.record_kind.value,
                "successor_id": self.successor_id,
                "predecessor_id": self.predecessor_id,
                "source_external_id": self.source_external_id,
                "local_id": self.local_id,
                "policy_version": self.policy_version,
            },
        )
        if self.lineage_id is not None and self.lineage_id != expected:
            raise ValueError("lineage_id does not match Core deterministic lineage material")
        object.__setattr__(self, "lineage_id", expected)
        return self


class IngestionItemReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.ingestion-item-receipt/v1"] = ITEM_RECEIPT_VERSION
    receipt_id: str
    manifest_id: str
    product_id: str
    item_key: str
    item_ordinal: int = Field(ge=0)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    disposition: IngestionDisposition
    record_results: tuple[RecordIngestionResultV1, ...] = Field(min_length=1, max_length=MAX_RECORDS_PER_ITEM)
    lineage_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_RECORDS_PER_ITEM**2)
    processor_version: str = INGESTION_PROCESSOR_VERSION
    schema_version: str = INGESTION_SCHEMA_VERSION

    @field_validator("lineage_ids", mode="before")
    @classmethod
    def normalize_lineage_ids(cls, value: Any) -> tuple[str, ...]:
        return _bounded_strings(
            value,
            name="lineage_ids",
            limit=MAX_RECORDS_PER_ITEM**2,
            item_limit=240,
        )

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @model_validator(mode="after")
    def validate_item_disposition(self) -> Self:
        dispositions = {result.disposition for result in self.record_results}
        priority = (
            IngestionDisposition.FAILED,
            IngestionDisposition.REJECTED,
            IngestionDisposition.SUPERSEDING,
            IngestionDisposition.ACCEPTED,
            IngestionDisposition.DUPLICATE,
        )
        expected = next(value for value in priority if value in dispositions)
        if self.disposition is not expected:
            raise ValueError("item disposition must summarize its record results deterministically")
        return self


class BatchIngestionReceiptV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.batch-ingestion-receipt/v1"] = BATCH_RECEIPT_VERSION
    receipt_id: str
    manifest_id: str
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    product_id: str
    adapter_id: str
    adapter_version: str
    extraction_run_id: str
    submitted_at: datetime
    item_counts: IngestionDispositionCountsV1
    record_counts: IngestionDispositionCountsV1
    persisted_by_kind: GroundedRecordCountsV1
    item_receipt_ids: tuple[str, ...] = Field(min_length=1, max_length=MAX_BATCH_ITEMS)
    stable_record_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_BATCH_ITEMS * MAX_RECORDS_PER_ITEM)
    lineage_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=MAX_BATCH_ITEMS * MAX_RECORDS_PER_ITEM**2,
    )
    lineage_edges_persisted: int = Field(default=0, ge=0)
    primary_model_calls: Literal[0] = 0
    processor_version: str = INGESTION_PROCESSOR_VERSION
    schema_version: str = INGESTION_SCHEMA_VERSION
    complete: Literal[True] = True

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _product(value)

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, value: datetime) -> datetime:
        return _aware(value, "submitted_at")

    @field_validator("item_receipt_ids", mode="before")
    @classmethod
    def normalize_item_receipt_ids(cls, value: Any) -> tuple[str, ...]:
        # Receipt ordering is semantically irrelevant and must not vary with arrival order.
        return _bounded_strings(
            value,
            name="item_receipt_ids",
            limit=MAX_BATCH_ITEMS * MAX_RECORDS_PER_ITEM,
            item_limit=240,
        )

    @field_validator("stable_record_ids", mode="before")
    @classmethod
    def normalize_stable_record_ids(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("stable_record_ids must be a collection")
        ids = tuple(sorted(value))
        if len(ids) > MAX_BATCH_ITEMS * MAX_RECORDS_PER_ITEM:
            raise ValueError("stable_record_ids exceeds the manifest record bound")
        if any(not isinstance(item, str) or not item.strip() or len(item) > 240 for item in ids):
            raise ValueError("stable_record_ids must contain bounded stable identities")
        return ids

    @field_validator("lineage_ids", mode="before")
    @classmethod
    def normalize_lineage_ids(cls, value: Any) -> tuple[str, ...]:
        return _bounded_strings(
            value,
            name="lineage_ids",
            limit=MAX_BATCH_ITEMS * MAX_RECORDS_PER_ITEM**2,
            item_limit=240,
        )

    @model_validator(mode="after")
    def validate_reconciliation(self) -> Self:
        if self.item_counts.inputs != len(self.item_receipt_ids):
            raise ValueError("batch receipt must name one item receipt per manifest input")
        if self.record_counts.persisted != self.persisted_by_kind.total():
            raise ValueError("persisted per-kind counts must equal the persisted record total")
        if len(self.stable_record_ids) != (
            self.record_counts.accepted + self.record_counts.duplicate + self.record_counts.superseding
        ):
            raise ValueError("every successful record result must expose one stable identity")
        if self.lineage_edges_persisted != len(self.lineage_ids):
            raise ValueError("lineage edge counts must reconcile their stable identities")
        return self


def build_item_receipt_id(*, manifest_id: str, item_ordinal: int, input_hash: str) -> str:
    return stable_id(
        "grounded_ingestion_item_receipt",
        {"manifest_id": manifest_id, "item_ordinal": item_ordinal, "input_hash": input_hash},
    )


def build_batch_receipt_id(*, manifest_id: str) -> str:
    return stable_id("grounded_batch_ingestion_receipt", {"manifest_id": manifest_id})
