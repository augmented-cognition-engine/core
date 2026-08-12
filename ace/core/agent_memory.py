"""Provider-neutral Agent Memory mechanics owned by the ACE Core boundary.

This module defines identity, scope, source location, temporal, lifecycle,
session, opaque ledger-read, and erasure-proof grammar. It deliberately
contains no memory-family, reconciliation, ranking, candidate, graph,
context-composition, persistence-provider, host, or extension logic.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self, TypeAlias

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, stable_id

AGENT_MEMORY_SCOPE_VERSION = "ace.core.agent-memory-scope/v1alpha1"
LEDGER_COORDINATE_VERSION = "ace.core.agent-memory-ledger-coordinate/v1alpha1"
KNOWLEDGE_TIME_VERSION = "ace.core.agent-memory-knowledge-time/v1alpha1"
WORLD_TIME_VERSION = "ace.core.agent-memory-world-time/v1alpha1"
TEMPORAL_QUERY_VERSION = "ace.core.agent-memory-temporal-query/v1alpha1"
SOURCE_PROVENANCE_VERSION = "ace.core.agent-memory-source-provenance/v1alpha1"
HISTORICAL_LINEAGE_REFERENCE_VERSION = "ace.core.agent-memory-historical-lineage-reference/v1alpha1"
PARTICIPANT_VERSION = "ace.core.agent-memory-participant/v1alpha1"
SESSION_RECORD_VERSION = "ace.core.agent-memory-session-record/v1alpha1"
TURN_RECORD_VERSION = "ace.core.agent-memory-turn-record/v1alpha1"
LIFECYCLE_EVENT_VERSION = "ace.core.agent-memory-lifecycle-event/v1alpha1"
LEDGER_READ_VERSION = "ace.core.agent-memory-ledger-read/v1alpha1"
ERASURE_DEPENDENCY_PROOF_VERSION = "ace.core.agent-memory-erasure-dependency-proof/v1alpha1"

MAX_REFS = 256

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_TYPE_REFERENCE = re.compile(r"^[a-z][a-z0-9]*(?:[._:/-][a-z0-9]+){0,15}$")
_PRODUCT_ID = re.compile(r"^product:[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _reference(value: str, *, name: str) -> str:
    if not _REFERENCE.fullmatch(value):
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def _type_reference(value: str, *, name: str) -> str:
    if len(value) > 240 or not _TYPE_REFERENCE.fullmatch(value):
        raise ValueError(f"{name} must be a bounded lowercase type reference")
    return value


def _normalized_refs(value: Any, *, name: str, maximum: int = MAX_REFS) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{name} must be a collection")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must contain stable references")
    refs = tuple(sorted(set(value)))
    if len(refs) > maximum:
        raise ValueError(f"{name} exceeds the {maximum}-item bound")
    for ref in refs:
        _reference(ref, name=name)
    return refs


def _derive_identity(instance: _StrictFrozenContract, *, prefix: str, field: str) -> None:
    material = instance.model_dump(mode="json", exclude={field})
    expected = stable_id(prefix, material)
    supplied = getattr(instance, field)
    if supplied is not None and supplied != expected:
        raise ValueError(f"{field} does not match exact canonical material")
    object.__setattr__(instance, field, expected)


class MemoryVisibility(StrEnum):
    PRIVATE = "private"
    PRODUCT = "product"
    TEAM = "team"
    RESTRICTED = "restricted"


class RetentionClass(StrEnum):
    EPHEMERAL = "ephemeral"
    STANDARD = "standard"
    RESTRICTED = "restricted"
    LEGAL_HOLD = "legal_hold"


class ParticipantRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    SERVICE = "service"
    EXTERNAL = "external"


class AgentMemoryScopeV1Alpha1(_StrictFrozenContract):
    """Core-authenticated scope; captured material cannot manufacture it."""

    contract: Literal["ace.core.agent-memory-scope/v1alpha1"] = AGENT_MEMORY_SCOPE_VERSION
    product_id: str
    actor_id: str
    session_id: str | None = None
    source_id: str | None = None
    visibility: MemoryVisibility
    retention_class: RetentionClass
    authority_receipt_ref: str
    scope_id: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, value: str) -> str:
        if not _PRODUCT_ID.fullmatch(value):
            raise ValueError("product_id must be a bounded product identifier")
        return value

    @field_validator("actor_id", "session_id", "source_id", "authority_receipt_ref")
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def derive_scope_id(self) -> Self:
        _derive_identity(self, prefix="agent_memory_scope", field="scope_id")
        return self


class LedgerCoordinateV1Alpha1(_StrictFrozenContract):
    """One immutable position in a named Agent Memory ledger."""

    contract: Literal["ace.core.agent-memory-ledger-coordinate/v1alpha1"] = LEDGER_COORDINATE_VERSION
    ledger_ref: str
    sequence: int = Field(ge=1)
    event_ref: str
    committed_at: datetime

    @field_validator("ledger_ref", "event_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("committed_at")
    @classmethod
    def validate_committed_at(cls, value: datetime) -> datetime:
        return _aware(value, name="committed_at")


class KnowledgeTimeKind(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class KnowledgeTimeV1Alpha1(_StrictFrozenContract):
    """When ACE first knew the material, independent of commit and world time."""

    contract: Literal["ace.core.agent-memory-knowledge-time/v1alpha1"] = KNOWLEDGE_TIME_VERSION
    kind: KnowledgeTimeKind
    first_known_at: datetime | None = None
    basis_refs: tuple[str, ...] = ()
    unknown_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("first_known_at")
    @classmethod
    def validate_first_known_at(cls, value: datetime | None) -> datetime | None:
        return _aware(value, name="first_known_at") if value is not None else None

    @field_validator("basis_refs", mode="before")
    @classmethod
    def normalize_basis_refs(cls, value: Any) -> tuple[str, ...]:
        return _normalized_refs(value, name="basis_refs")

    @model_validator(mode="after")
    def validate_meaning(self) -> Self:
        if self.kind is KnowledgeTimeKind.KNOWN:
            if self.first_known_at is None or self.unknown_reason is not None:
                raise ValueError("known knowledge time requires first_known_at and forbids unknown_reason")
        elif self.first_known_at is not None or self.basis_refs or self.unknown_reason is None:
            raise ValueError("unknown knowledge time requires a reason and cannot carry a fabricated time or basis")
        return self


class WorldTimeKind(StrEnum):
    INSTANT = "instant"
    INTERVAL = "interval"
    RECURRING = "recurring"
    UNKNOWN = "unknown"


class WorldTimeV1Alpha1(_StrictFrozenContract):
    """When material applies in the represented world."""

    contract: Literal["ace.core.agent-memory-world-time/v1alpha1"] = WORLD_TIME_VERSION
    kind: WorldTimeKind
    occurred_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    recurrence_ref: str | None = None
    inferred_from: tuple[str, ...] = ()
    unknown_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("occurred_at", "valid_from", "valid_to")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @field_validator("recurrence_ref")
    @classmethod
    def validate_recurrence_ref(cls, value: str | None) -> str | None:
        return _reference(value, name="recurrence_ref") if value is not None else None

    @field_validator("inferred_from", mode="before")
    @classmethod
    def normalize_inferred_from(cls, value: Any) -> tuple[str, ...]:
        return _normalized_refs(value, name="inferred_from")

    @model_validator(mode="after")
    def validate_meaning(self) -> Self:
        if self.valid_from is not None and self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        if self.kind is WorldTimeKind.INSTANT:
            if self.occurred_at is None or any(
                value is not None
                for value in (self.valid_from, self.valid_to, self.recurrence_ref, self.unknown_reason)
            ):
                raise ValueError("instant world time requires only occurred_at")
        elif self.kind is WorldTimeKind.INTERVAL:
            if (
                self.valid_from is None
                and self.valid_to is None
                or self.occurred_at is not None
                or self.recurrence_ref is not None
                or self.unknown_reason is not None
            ):
                raise ValueError("interval world time requires an open or closed interval only")
        elif self.kind is WorldTimeKind.RECURRING:
            if self.recurrence_ref is None or self.occurred_at is not None or self.unknown_reason is not None:
                raise ValueError("recurring world time requires recurrence_ref and forbids instant/unknown fields")
        elif (
            any(value is not None for value in (self.occurred_at, self.valid_from, self.valid_to, self.recurrence_ref))
            or self.inferred_from
            or self.unknown_reason is None
        ):
            raise ValueError("unknown world time requires a reason and cannot carry fabricated temporal material")
        return self


class TemporalQueryV1Alpha1(_StrictFrozenContract):
    """Independent optional selectors; no selector substitutes for another."""

    contract: Literal["ace.core.agent-memory-temporal-query/v1alpha1"] = TEMPORAL_QUERY_VERSION
    ledger_at: LedgerCoordinateV1Alpha1 | None = None
    knowledge_at: datetime | None = None
    world_at: datetime | None = None
    include_unknown_knowledge: bool = False
    include_unknown_world: bool = False

    @field_validator("knowledge_at", "world_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None


class _SourceSpanBase(_StrictFrozenContract):
    source_version_id: str
    span_id: str | None = None

    @field_validator("source_version_id")
    @classmethod
    def validate_source_version_id(cls, value: str) -> str:
        return _reference(value, name="source_version_id")

    @model_validator(mode="after")
    def derive_span_id(self) -> Self:
        _derive_identity(self, prefix="agent_memory_span", field="span_id")
        return self


class ByteRangeSpanV1Alpha1(_SourceSpanBase):
    kind: Literal["byte_range"] = "byte_range"
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.end_byte <= self.start_byte:
            raise ValueError("end_byte must be greater than start_byte")
        return self


class TextCharacterRangeSpanV1Alpha1(_SourceSpanBase):
    kind: Literal["text_character_range"] = "text_character_range"
    normalization_version: str
    start_character: int = Field(ge=0)
    end_character: int = Field(ge=1)

    @field_validator("normalization_version")
    @classmethod
    def validate_normalization_version(cls, value: str) -> str:
        return _reference(value, name="normalization_version")

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.end_character <= self.start_character:
            raise ValueError("end_character must be greater than start_character")
        return self


class PageRegionSpanV1Alpha1(_SourceSpanBase):
    kind: Literal["page_region"] = "page_region"
    page: int = Field(ge=1)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_region(self) -> Self:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("page region must remain within normalized page bounds")
        return self


class FrameRegionSpanV1Alpha1(_SourceSpanBase):
    kind: Literal["frame_region"] = "frame_region"
    frame: int = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_region(self) -> Self:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("frame region must remain within normalized frame bounds")
        return self


class TimecodeSpanV1Alpha1(_SourceSpanBase):
    kind: Literal["timecode"] = "timecode"
    start_milliseconds: int = Field(ge=0)
    end_milliseconds: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.end_milliseconds <= self.start_milliseconds:
            raise ValueError("end_milliseconds must be greater than start_milliseconds")
        return self


class StructuredPointerSpanV1Alpha1(_SourceSpanBase):
    kind: Literal["structured_pointer"] = "structured_pointer"
    pointer: str = Field(min_length=1, max_length=1_000)
    pointer_scheme: Literal["json_pointer"] = "json_pointer"

    @field_validator("pointer")
    @classmethod
    def validate_pointer(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("JSON Pointer source spans must start with slash")
        return value


class WholeSourceSpanV1Alpha1(_SourceSpanBase):
    kind: Literal["whole_source"] = "whole_source"


class UnavailableSpanReason(StrEnum):
    ADAPTER_UNSUPPORTED = "adapter_unsupported"
    MISSING_FROM_SOURCE = "missing_from_source"
    REDACTED = "redacted"
    SOURCE_UNAVAILABLE = "source_unavailable"
    UNKNOWN = "unknown"


class UnavailableSourceSpanV1Alpha1(_SourceSpanBase):
    kind: Literal["unavailable"] = "unavailable"
    reason: UnavailableSpanReason
    detail: str = Field(min_length=1, max_length=500)


SourceSpanV1Alpha1: TypeAlias = Annotated[
    ByteRangeSpanV1Alpha1
    | TextCharacterRangeSpanV1Alpha1
    | PageRegionSpanV1Alpha1
    | FrameRegionSpanV1Alpha1
    | TimecodeSpanV1Alpha1
    | StructuredPointerSpanV1Alpha1
    | WholeSourceSpanV1Alpha1
    | UnavailableSourceSpanV1Alpha1,
    Field(discriminator="kind"),
]


class HistoricalLineageReferenceV1Alpha1(_StrictFrozenContract):
    """Exact external lineage that is permanently non-authoritative."""

    contract: Literal["ace.core.agent-memory-historical-lineage-reference/v1alpha1"] = (
        HISTORICAL_LINEAGE_REFERENCE_VERSION
    )
    authority_stage: Literal["historical_reference"] = "historical_reference"
    live_authority: Literal[False] = False
    referenced_contract: str
    referenced_record_ref: str
    referenced_material_digest: str
    lineage_id: str | None = None

    @field_validator("referenced_contract")
    @classmethod
    def validate_referenced_contract(cls, value: str) -> str:
        return _type_reference(value, name="referenced_contract")

    @field_validator("referenced_record_ref")
    @classmethod
    def validate_referenced_record_ref(cls, value: str) -> str:
        return _reference(value, name="referenced_record_ref")

    @field_validator("referenced_material_digest")
    @classmethod
    def validate_referenced_material_digest(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("referenced_material_digest must use lowercase sha256:<64-hex> syntax")
        return value

    @model_validator(mode="after")
    def derive_lineage_id(self) -> Self:
        _derive_identity(self, prefix="agent_memory_historical_lineage", field="lineage_id")
        return self


class SourceProvenanceV1Alpha1(_StrictFrozenContract):
    """Exact source identity and locator, or an explicit reason it is unavailable."""

    contract: Literal["ace.core.agent-memory-source-provenance/v1alpha1"] = SOURCE_PROVENANCE_VERSION
    source_id: str
    source_version_id: str
    content_digest: str
    span: SourceSpanV1Alpha1
    acquisition_receipt_ref: str
    capture_method_ref: str
    derived_from: tuple[str, ...] = ()
    historical_lineage: tuple[HistoricalLineageReferenceV1Alpha1, ...] = ()

    @field_validator("source_id", "source_version_id", "acquisition_receipt_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("capture_method_ref")
    @classmethod
    def validate_capture_method_ref(cls, value: str) -> str:
        return _type_reference(value, name="capture_method_ref")

    @field_validator("content_digest")
    @classmethod
    def validate_content_digest(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("content_digest must use lowercase sha256:<64-hex> syntax")
        return value

    @field_validator("derived_from", mode="before")
    @classmethod
    def normalize_derived_from(cls, value: Any) -> tuple[str, ...]:
        return _normalized_refs(value, name="derived_from")

    @field_validator("historical_lineage")
    @classmethod
    def normalize_historical_lineage(
        cls,
        value: tuple[HistoricalLineageReferenceV1Alpha1, ...],
    ) -> tuple[HistoricalLineageReferenceV1Alpha1, ...]:
        if len(value) > MAX_REFS:
            raise ValueError("historical_lineage exceeds the supported bound")
        identities = [item.lineage_id for item in value]
        if len(identities) != len(set(identities)):
            raise ValueError("historical_lineage must contain unique exact references")
        return tuple(sorted(value, key=lambda item: str(item.lineage_id)))

    @model_validator(mode="after")
    def validate_source_version(self) -> Self:
        if self.span.source_version_id != self.source_version_id:
            raise ValueError("source span must bind the exact provenance source version")
        return self


class ParticipantV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-participant/v1alpha1"] = PARTICIPANT_VERSION
    participant_id: str
    role: ParticipantRole
    authority_ref: str | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("participant_id", "authority_ref")
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None


class SessionRecordV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-session-record/v1alpha1"] = SESSION_RECORD_VERSION
    scope: AgentMemoryScopeV1Alpha1
    session_id: str
    participants: tuple[ParticipantV1Alpha1, ...]
    source_refs: tuple[str, ...] = ()
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        return _reference(value, name="session_id")

    @field_validator("source_refs", mode="before")
    @classmethod
    def normalize_source_refs(cls, value: Any) -> tuple[str, ...]:
        return _normalized_refs(value, name="source_refs")

    @field_validator("started_at", "ended_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_session(self) -> Self:
        if self.scope.session_id is not None and self.scope.session_id != self.session_id:
            raise ValueError("session record must match the authenticated session scope")
        participant_ids = [item.participant_id for item in self.participants]
        if not participant_ids or len(participant_ids) != len(set(participant_ids)):
            raise ValueError("session participants must be non-empty and uniquely identified")
        ordered = tuple(sorted(self.participants, key=lambda item: item.participant_id))
        object.__setattr__(self, "participants", ordered)
        if self.started_at is not None and self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must not precede started_at")
        return self


class TurnRecordV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-turn-record/v1alpha1"] = TURN_RECORD_VERSION
    scope: AgentMemoryScopeV1Alpha1
    turn_id: str
    session_id: str
    participant_id: str
    ordinal: int = Field(ge=0)
    provenance: SourceProvenanceV1Alpha1
    knowledge_time: KnowledgeTimeV1Alpha1
    world_time: WorldTimeV1Alpha1

    @field_validator("turn_id", "session_id", "participant_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.scope.session_id is not None and self.scope.session_id != self.session_id:
            raise ValueError("turn record must match the authenticated session scope")
        if self.scope.source_id is not None and self.scope.source_id != self.provenance.source_id:
            raise ValueError("turn provenance must match the authenticated source scope")
        return self


class LifecycleState(StrEnum):
    ACTIVE = "active"
    RESTRICTED = "restricted"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    REDACTED = "redacted"
    FORGOTTEN = "forgotten"
    ERASE_PENDING = "erase_pending"
    ERASED = "erased"
    QUARANTINED = "quarantined"


class LifecycleOperation(StrEnum):
    ACTIVATE = "activate"
    RESTRICT = "restrict"
    SUPERSEDE = "supersede"
    EXPIRE = "expire"
    ARCHIVE = "archive"
    REDACT = "redact"
    SOFT_FORGET = "soft_forget"
    REQUEST_ERASURE = "request_erasure"
    CONFIRM_ERASURE = "confirm_erasure"
    QUARANTINE = "quarantine"
    RESTORE = "restore"


_OPERATION_TARGET_STATE = {
    LifecycleOperation.ACTIVATE: LifecycleState.ACTIVE,
    LifecycleOperation.RESTRICT: LifecycleState.RESTRICTED,
    LifecycleOperation.SUPERSEDE: LifecycleState.SUPERSEDED,
    LifecycleOperation.EXPIRE: LifecycleState.EXPIRED,
    LifecycleOperation.ARCHIVE: LifecycleState.ARCHIVED,
    LifecycleOperation.REDACT: LifecycleState.REDACTED,
    LifecycleOperation.SOFT_FORGET: LifecycleState.FORGOTTEN,
    LifecycleOperation.REQUEST_ERASURE: LifecycleState.ERASE_PENDING,
    LifecycleOperation.CONFIRM_ERASURE: LifecycleState.ERASED,
    LifecycleOperation.QUARANTINE: LifecycleState.QUARANTINED,
    LifecycleOperation.RESTORE: LifecycleState.ACTIVE,
}


class LifecycleEventV1Alpha1(_StrictFrozenContract):
    """Append-only lifecycle transition; it never rewrites prior material."""

    contract: Literal["ace.core.agent-memory-lifecycle-event/v1alpha1"] = LIFECYCLE_EVENT_VERSION
    scope: AgentMemoryScopeV1Alpha1
    target_ref: str
    operation: LifecycleOperation
    prior_state: LifecycleState | None = None
    next_state: LifecycleState
    actor_ref: str
    authority_receipt_ref: str
    reason: str = Field(min_length=1, max_length=2_000)
    occurred_at: datetime
    prior_coordinate: LedgerCoordinateV1Alpha1 | None = None
    successor_ref: str | None = None
    erasure_dependency_proof_ref: str | None = None
    event_id: str | None = None

    @field_validator(
        "target_ref",
        "actor_ref",
        "authority_receipt_ref",
        "successor_ref",
        "erasure_dependency_proof_ref",
    )
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return _aware(value, name="occurred_at")

    @model_validator(mode="after")
    def validate_transition(self) -> Self:
        if _OPERATION_TARGET_STATE[self.operation] is not self.next_state:
            raise ValueError("lifecycle operation does not match next_state")
        if self.operation is LifecycleOperation.ACTIVATE and self.prior_state is not None:
            raise ValueError("initial activation cannot name a prior lifecycle state")
        if self.operation is not LifecycleOperation.ACTIVATE and self.prior_state is None:
            raise ValueError("later lifecycle operations require a prior state")
        if self.operation is LifecycleOperation.ACTIVATE and self.prior_coordinate is not None:
            raise ValueError("initial activation cannot name a prior ledger coordinate")
        if self.operation is not LifecycleOperation.ACTIVATE and self.prior_coordinate is None:
            raise ValueError("later lifecycle operations require the exact prior ledger coordinate")
        if self.operation is LifecycleOperation.CONFIRM_ERASURE:
            if self.prior_state is not LifecycleState.ERASE_PENDING or self.erasure_dependency_proof_ref is None:
                raise ValueError("erasure confirmation requires erase_pending and an erasure dependency proof")
        elif self.erasure_dependency_proof_ref is not None:
            raise ValueError("erasure_dependency_proof_ref is reserved for erasure confirmation")
        if self.operation is LifecycleOperation.SUPERSEDE:
            if self.successor_ref is None:
                raise ValueError("supersession requires successor_ref")
        elif self.successor_ref is not None:
            raise ValueError("successor_ref is reserved for supersession")
        if self.operation is LifecycleOperation.RESTORE and self.prior_state not in {
            LifecycleState.RESTRICTED,
            LifecycleState.QUARANTINED,
        }:
            raise ValueError("restore is only valid from restricted or quarantined state")
        _derive_identity(self, prefix="agent_memory_lifecycle", field="event_id")
        return self


class AgentMemoryLedgerReadV1Alpha1(_StrictFrozenContract):
    """Opaque authorized ledger read with independent temporal selectors."""

    contract: Literal["ace.core.agent-memory-ledger-read/v1alpha1"] = LEDGER_READ_VERSION
    scope: AgentMemoryScopeV1Alpha1
    temporal: TemporalQueryV1Alpha1 = Field(default_factory=TemporalQueryV1Alpha1)
    record_kind_refs: tuple[str, ...] = ()
    limit: int = Field(default=200, ge=1, le=1_000)
    read_id: str | None = None

    @field_validator("record_kind_refs", mode="before")
    @classmethod
    def normalize_record_kinds(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("record_kind_refs must be a collection")
        refs = tuple(sorted(set(value)))
        if len(refs) > MAX_REFS:
            raise ValueError("record_kind_refs exceeds the supported bound")
        for ref in refs:
            _type_reference(ref, name="record_kind_refs")
        return refs

    @model_validator(mode="after")
    def derive_read_id(self) -> Self:
        _derive_identity(self, prefix="agent_memory_ledger_read", field="read_id")
        return self


class ErasureDependencyProofV1Alpha1(_StrictFrozenContract):
    """Content-free proof that every enumerated dependency was removed."""

    contract: Literal["ace.core.agent-memory-erasure-dependency-proof/v1alpha1"] = ERASURE_DEPENDENCY_PROOF_VERSION
    scope: AgentMemoryScopeV1Alpha1
    target_ref: str
    erasure_request_event_ref: str
    dependency_index_snapshot_ref: str
    enumerated_dependency_refs: tuple[str, ...]
    removed_dependency_refs: tuple[str, ...]
    verifier_ref: str
    authority_receipt_ref: str
    verified_at: datetime
    proof_id: str | None = None

    @field_validator(
        "target_ref",
        "erasure_request_event_ref",
        "dependency_index_snapshot_ref",
        "verifier_ref",
        "authority_receipt_ref",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("enumerated_dependency_refs", "removed_dependency_refs", mode="before")
    @classmethod
    def normalize_dependency_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _normalized_refs(value, name=info.field_name, maximum=10_000)

    @field_validator("verified_at")
    @classmethod
    def validate_verified_at(cls, value: datetime) -> datetime:
        return _aware(value, name="verified_at")

    @model_validator(mode="after")
    def validate_complete_removal(self) -> Self:
        if self.enumerated_dependency_refs != self.removed_dependency_refs:
            raise ValueError("erasure proof requires every enumerated dependency to be removed")
        _derive_identity(self, prefix="agent_memory_erasure_proof", field="proof_id")
        return self


__all__ = [
    "AGENT_MEMORY_SCOPE_VERSION",
    "ERASURE_DEPENDENCY_PROOF_VERSION",
    "HISTORICAL_LINEAGE_REFERENCE_VERSION",
    "KNOWLEDGE_TIME_VERSION",
    "LEDGER_COORDINATE_VERSION",
    "LIFECYCLE_EVENT_VERSION",
    "PARTICIPANT_VERSION",
    "LEDGER_READ_VERSION",
    "SESSION_RECORD_VERSION",
    "SOURCE_PROVENANCE_VERSION",
    "TEMPORAL_QUERY_VERSION",
    "TURN_RECORD_VERSION",
    "WORLD_TIME_VERSION",
    "AgentMemoryLedgerReadV1Alpha1",
    "AgentMemoryScopeV1Alpha1",
    "ByteRangeSpanV1Alpha1",
    "ErasureDependencyProofV1Alpha1",
    "FrameRegionSpanV1Alpha1",
    "HistoricalLineageReferenceV1Alpha1",
    "KnowledgeTimeKind",
    "KnowledgeTimeV1Alpha1",
    "LedgerCoordinateV1Alpha1",
    "LifecycleEventV1Alpha1",
    "LifecycleOperation",
    "LifecycleState",
    "MemoryVisibility",
    "PageRegionSpanV1Alpha1",
    "ParticipantRole",
    "ParticipantV1Alpha1",
    "RetentionClass",
    "SessionRecordV1Alpha1",
    "SourceProvenanceV1Alpha1",
    "SourceSpanV1Alpha1",
    "StructuredPointerSpanV1Alpha1",
    "TemporalQueryV1Alpha1",
    "TextCharacterRangeSpanV1Alpha1",
    "TimecodeSpanV1Alpha1",
    "TurnRecordV1Alpha1",
    "UnavailableSourceSpanV1Alpha1",
    "UnavailableSpanReason",
    "WholeSourceSpanV1Alpha1",
    "WorldTimeKind",
    "WorldTimeV1Alpha1",
]
