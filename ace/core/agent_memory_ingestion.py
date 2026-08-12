"""Provider-neutral contracts for the AM1 episodic experience ledger.

Adapters propose inert source events. Core alone derives canonical identities,
binds authenticated scope, records import lifecycle, and issues content-free
receipts. This module deliberately contains no persistence implementation,
semantic-memory assertions, ranking, composition, provider, host, or MCP code.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, Self, runtime_checkable

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    KnowledgeTimeV1Alpha1,
    LedgerCoordinateV1Alpha1,
    ParticipantRole,
    SourceProvenanceV1Alpha1,
    SourceSpanV1Alpha1,
    WorldTimeV1Alpha1,
)
from ace.core.contracts import FrozenContract, stable_id

SOURCE_ADAPTER_IDENTITY_VERSION = "ace.core.agent-memory-source-adapter-identity/v1alpha1"
IDEMPOTENCY_IDENTITY_VERSION = "ace.core.agent-memory-idempotency-identity/v1alpha1"
CANONICAL_SESSION_IDENTITY_VERSION = "ace.core.agent-memory-canonical-session-identity/v1alpha1"
CANONICAL_PARTICIPANT_IDENTITY_VERSION = "ace.core.agent-memory-canonical-participant-identity/v1alpha1"
EXTERNAL_EVENT_IDENTITY_VERSION = "ace.core.agent-memory-external-event-identity/v1alpha1"
CANONICAL_EVENT_IDENTITY_VERSION = "ace.core.agent-memory-canonical-event-identity/v1alpha1"
CANONICAL_TURN_IDENTITY_VERSION = "ace.core.agent-memory-canonical-turn-identity/v1alpha1"
SESSION_IMPORT_INTENT_VERSION = "ace.core.agent-memory-session-import-intent/v1alpha1"
EPISODIC_SOURCE_EVENT_VERSION = "ace.core.agent-memory-episodic-source-event/v1alpha1"
BATCH_INGESTION_PROPOSAL_VERSION = "ace.core.agent-memory-batch-ingestion-proposal/v1alpha1"
STREAM_INGESTION_PROPOSAL_VERSION = "ace.core.agent-memory-stream-ingestion-proposal/v1alpha1"
IMPORT_JOB_VERSION = "ace.core.agent-memory-import-job/v1alpha1"
SESSION_NORMALIZATION_RECEIPT_VERSION = "ace.core.agent-memory-session-normalization-receipt/v1alpha1"
SESSION_INGESTION_STATUS_VERSION = "ace.core.agent-memory-session-ingestion-status/v1alpha1"
SESSION_INGESTION_RECEIPT_VERSION = "ace.core.agent-memory-session-ingestion-receipt/v1alpha1"
EVENT_LIST_QUERY_VERSION = "ace.core.agent-memory-event-list-query/v1alpha1"
EVENT_LIST_RECEIPT_VERSION = "ace.core.agent-memory-event-list-receipt/v1alpha1"
SPAN_READ_QUERY_VERSION = "ace.core.agent-memory-span-read-query/v1alpha1"
TRANSCRIPT_VIEW_RECEIPT_VERSION = "ace.core.agent-memory-transcript-view-receipt/v1alpha1"

IDENTITY_DERIVATION_VERSION = "agent-memory-am1-identity-v1"
TURN_BOUNDARY_POLICY_VERSION = "agent-memory-am1-adjacent-role-turns-v1"
MAX_EVENTS = 1_000
MAX_REFS = 1_000

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_TYPE_REFERENCE = re.compile(r"^[a-z][a-z0-9]*(?:[._:/-][a-z0-9]+){0,15}$")
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
    if not _TYPE_REFERENCE.fullmatch(value):
        raise ValueError(f"{name} must be a bounded lowercase type reference")
    return value


def _digest(value: str, *, name: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    return value


def _refs(value: Any, *, name: str, maximum: int = MAX_REFS) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple, set, frozenset)) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a collection of stable references")
    normalized = tuple(sorted(set(value)))
    if len(normalized) > maximum:
        raise ValueError(f"{name} exceeds the {maximum}-item bound")
    for item in normalized:
        _reference(item, name=name)
    return normalized


def _derive(instance: _StrictFrozenContract, *, prefix: str, field: str, exclude: set[str] | None = None) -> None:
    material = instance.model_dump(mode="json", exclude={field, *(exclude or set())})
    expected = stable_id(prefix, material)
    supplied = getattr(instance, field)
    if supplied is not None and supplied != expected:
        raise ValueError(f"{field} does not match exact canonical material")
    object.__setattr__(instance, field, expected)


class EpisodicEventKind(StrEnum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"
    ATTACHMENT = "attachment"
    STATE = "state"
    OTHER = "other"


class IngestionMode(StrEnum):
    BATCH = "batch"
    STREAM = "stream"


class ImportState(StrEnum):
    QUEUED = "queued"
    NORMALIZING = "normalizing"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
    STALE = "stale"
    RETRY_PENDING = "retry_pending"
    REPAIR_REQUIRED = "repair_required"


class IngestionDisposition(StrEnum):
    COMMITTED = "committed"
    EXACT_REPLAY = "exact_replay"
    REJECTED = "rejected"
    INDETERMINATE = "indeterminate"


_STATUS_TRANSITIONS: dict[ImportState, frozenset[ImportState]] = {
    ImportState.QUEUED: frozenset({ImportState.NORMALIZING, ImportState.FAILED, ImportState.STALE}),
    ImportState.NORMALIZING: frozenset(
        {
            ImportState.READY,
            ImportState.PARTIAL,
            ImportState.FAILED,
            ImportState.STALE,
            ImportState.RETRY_PENDING,
            ImportState.REPAIR_REQUIRED,
        }
    ),
    ImportState.READY: frozenset({ImportState.STALE, ImportState.REPAIR_REQUIRED}),
    ImportState.PARTIAL: frozenset({ImportState.FAILED, ImportState.RETRY_PENDING, ImportState.REPAIR_REQUIRED}),
    ImportState.FAILED: frozenset({ImportState.RETRY_PENDING, ImportState.REPAIR_REQUIRED}),
    ImportState.STALE: frozenset({ImportState.FAILED, ImportState.RETRY_PENDING, ImportState.REPAIR_REQUIRED}),
    ImportState.RETRY_PENDING: frozenset({ImportState.NORMALIZING, ImportState.FAILED, ImportState.STALE}),
    ImportState.REPAIR_REQUIRED: frozenset({ImportState.READY, ImportState.FAILED, ImportState.RETRY_PENDING}),
}


class SourceAdapterIdentityV1Alpha1(_StrictFrozenContract):
    """Exact provider-neutral adapter artifact; its name is not session identity."""

    contract: Literal["ace.core.agent-memory-source-adapter-identity/v1alpha1"] = SOURCE_ADAPTER_IDENTITY_VERSION
    adapter_ref: str
    adapter_version: str
    artifact_digest: str
    adapter_id: str | None = None

    @field_validator("adapter_ref", "adapter_version")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("artifact_digest")
    @classmethod
    def validate_artifact_digest(cls, value: str) -> str:
        return _digest(value, name="artifact_digest")

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        _derive(self, prefix="agent_memory_source_adapter", field="adapter_id")
        return self


class IdempotencyIdentityV1Alpha1(_StrictFrozenContract):
    """Core-owned exact-replay identity, bound to authenticated scope and material."""

    contract: Literal["ace.core.agent-memory-idempotency-identity/v1alpha1"] = IDEMPOTENCY_IDENTITY_VERSION
    product_id: str
    actor_id: str
    external_key: str
    immutable_input_digest: str
    adapter_id: str
    idempotency_id: str | None = None

    @field_validator("product_id", "actor_id", "external_key", "adapter_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("immutable_input_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _digest(value, name="immutable_input_digest")

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        # The immutable digest is the material bound under this replay key, not
        # part of the key itself. A second request with the same identity and a
        # different digest is therefore detectable as a divergent replay.
        _derive(
            self,
            prefix="agent_memory_idempotency",
            field="idempotency_id",
            exclude={"immutable_input_digest"},
        )
        return self


class CanonicalSessionIdentityV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-canonical-session-identity/v1alpha1"] = CANONICAL_SESSION_IDENTITY_VERSION
    scope_id: str
    source_id: str
    source_version_id: str
    native_session_coordinate: str
    task_ref: str | None = None
    decision_ref: str | None = None
    derivation_version: Literal["agent-memory-am1-identity-v1"] = IDENTITY_DERIVATION_VERSION
    session_id: str | None = None

    @field_validator(
        "scope_id",
        "source_id",
        "source_version_id",
        "native_session_coordinate",
        "task_ref",
        "decision_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        _derive(self, prefix="agent_memory_session", field="session_id")
        return self


class CanonicalParticipantIdentityV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-canonical-participant-identity/v1alpha1"] = (
        CANONICAL_PARTICIPANT_IDENTITY_VERSION
    )
    session_id: str
    native_participant_coordinate: str
    role: ParticipantRole
    grants_authority: Literal[False] = False
    participant_id: str | None = None

    @field_validator("session_id", "native_participant_coordinate")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        _derive(self, prefix="agent_memory_participant", field="participant_id")
        return self


class ExternalEventIdentityV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-external-event-identity/v1alpha1"] = EXTERNAL_EVENT_IDENTITY_VERSION
    source_version_id: str
    native_session_coordinate: str
    native_event_coordinate: str
    external_event_id: str | None = None

    @field_validator("source_version_id", "native_session_coordinate", "native_event_coordinate")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        _derive(self, prefix="agent_memory_external_event", field="external_event_id")
        return self


class CanonicalEventIdentityV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-canonical-event-identity/v1alpha1"] = CANONICAL_EVENT_IDENTITY_VERSION
    session_id: str
    source_version_id: str
    native_event_coordinate: str
    content_digest: str
    event_kind: EpisodicEventKind
    event_id: str | None = None

    @field_validator("session_id", "source_version_id", "native_event_coordinate")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("content_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _digest(value, name="content_digest")

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        _derive(self, prefix="agent_memory_event", field="event_id")
        return self


class CanonicalTurnIdentityV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-canonical-turn-identity/v1alpha1"] = CANONICAL_TURN_IDENTITY_VERSION
    session_id: str
    participant_id: str
    ordered_event_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_EVENTS)
    boundary_policy_version: Literal["agent-memory-am1-adjacent-role-turns-v1"] = TURN_BOUNDARY_POLICY_VERSION
    turn_id: str | None = None

    @field_validator("session_id", "participant_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("ordered_event_refs")
    @classmethod
    def validate_ordered_events(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("ordered_event_refs must not contain duplicates")
        for item in value:
            _reference(item, name="ordered_event_refs")
        return value

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        _derive(self, prefix="agent_memory_turn", field="turn_id")
        return self


class SessionImportIntentV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-session-import-intent/v1alpha1"] = SESSION_IMPORT_INTENT_VERSION
    scope: AgentMemoryScopeV1Alpha1
    adapter: SourceAdapterIdentityV1Alpha1
    input_source_ref: str
    input_source_version_id: str
    immutable_input_digest: str
    input_acquisition_receipt_ref: str
    source_knowledge_time: KnowledgeTimeV1Alpha1
    native_session_coordinate: str
    task_ref: str | None = None
    decision_ref: str | None = None
    idempotency: IdempotencyIdentityV1Alpha1
    mode: IngestionMode
    requested_at: datetime
    max_events: int = Field(default=MAX_EVENTS, ge=1, le=MAX_EVENTS)
    max_content_bytes: int = Field(default=10_000_000, ge=1, le=100_000_000)
    intent_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_scope_laundering_before_nested_identity_validation(cls, value: Any) -> Any:
        """Reject a forged copied identity without disclosing nested details.

        Pydantic revalidates frozen nested contracts. Checking the authenticated
        product/actor binding first ensures a copied object with a stale derived
        ID fails at this authority boundary, rather than as an identity oracle.
        """

        if isinstance(value, dict):
            scope = value.get("scope")
            idempotency = value.get("idempotency")
            if isinstance(scope, AgentMemoryScopeV1Alpha1) and isinstance(idempotency, IdempotencyIdentityV1Alpha1):
                if idempotency.product_id != scope.product_id or idempotency.actor_id != scope.actor_id:
                    raise ValueError("idempotency identity must match authenticated product and actor")
        return value

    @field_validator(
        "input_source_ref",
        "input_source_version_id",
        "input_acquisition_receipt_ref",
        "native_session_coordinate",
        "task_ref",
        "decision_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @field_validator("immutable_input_digest")
    @classmethod
    def validate_input_digest(cls, value: str) -> str:
        return _digest(value, name="immutable_input_digest")

    @field_validator("requested_at")
    @classmethod
    def validate_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        if self.scope.source_id is not None and self.scope.source_id != self.input_source_ref:
            raise ValueError("import source must match authenticated source scope")
        if self.idempotency.product_id != self.scope.product_id or self.idempotency.actor_id != self.scope.actor_id:
            raise ValueError("idempotency identity must match authenticated product and actor")
        if self.idempotency.adapter_id != self.adapter.adapter_id:
            raise ValueError("idempotency identity must bind the exact adapter")
        if self.idempotency.immutable_input_digest != self.immutable_input_digest:
            raise ValueError("idempotency identity must bind the exact immutable input")
        _derive(self, prefix="agent_memory_import_intent", field="intent_id")
        return self


class EpisodicSourceEventV1Alpha1(_StrictFrozenContract):
    """Canonical content-free event metadata; bodies stay behind private ports."""

    contract: Literal["ace.core.agent-memory-episodic-source-event/v1alpha1"] = EPISODIC_SOURCE_EVENT_VERSION
    scope: AgentMemoryScopeV1Alpha1
    session: CanonicalSessionIdentityV1Alpha1
    participant: CanonicalParticipantIdentityV1Alpha1
    external_event: ExternalEventIdentityV1Alpha1
    identity: CanonicalEventIdentityV1Alpha1
    provenance: SourceProvenanceV1Alpha1
    knowledge_time: KnowledgeTimeV1Alpha1
    world_time: WorldTimeV1Alpha1
    processing_ordinal: int = Field(ge=1, le=MAX_EVENTS)
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        if self.session.scope_id != self.scope.scope_id:
            raise ValueError("session identity must bind the authenticated scope")
        if (
            self.participant.session_id != self.session.session_id
            or self.identity.session_id != self.session.session_id
        ):
            raise ValueError("participant and event identities must bind the canonical session")
        if self.scope.source_id is not None and self.provenance.source_id != self.scope.source_id:
            raise ValueError("event provenance must match authenticated source scope")
        source_version = self.provenance.source_version_id
        if not all(
            value == source_version
            for value in (
                self.session.source_version_id,
                self.external_event.source_version_id,
                self.identity.source_version_id,
            )
        ):
            raise ValueError("event identities and provenance must bind the exact source version")
        if self.external_event.native_event_coordinate != self.identity.native_event_coordinate:
            raise ValueError("external and canonical identities must bind the same native event")
        return self


class BatchIngestionProposalV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-batch-ingestion-proposal/v1alpha1"] = BATCH_INGESTION_PROPOSAL_VERSION
    intent_id: str
    adapter_id: str
    events: tuple[EpisodicSourceEventV1Alpha1, ...] = Field(min_length=1, max_length=MAX_EVENTS)
    proposal_id: str | None = None

    @field_validator("intent_id", "adapter_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        ordinals = tuple(event.processing_ordinal for event in self.events)
        if ordinals != tuple(range(1, len(self.events) + 1)):
            raise ValueError("batch events require gap-free deterministic processing order")
        event_ids = tuple(event.identity.event_id for event in self.events)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("batch events must have unique canonical identities")
        _derive(self, prefix="agent_memory_batch_proposal", field="proposal_id")
        return self


class StreamIngestionProposalV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-stream-ingestion-proposal/v1alpha1"] = STREAM_INGESTION_PROPOSAL_VERSION
    intent_id: str
    adapter_id: str
    event: EpisodicSourceEventV1Alpha1
    stream_ordinal: int = Field(ge=1, le=MAX_EVENTS)
    prior_proposal_ref: str | None = None
    terminal: bool = False
    proposal_id: str | None = None

    @field_validator("intent_id", "adapter_id", "prior_proposal_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_sequence(self) -> Self:
        if self.event.processing_ordinal != self.stream_ordinal:
            raise ValueError("stream ordinal must equal canonical processing ordinal")
        if (self.stream_ordinal == 1) != (self.prior_proposal_ref is None):
            raise ValueError("only the first stream proposal may omit the exact predecessor")
        _derive(self, prefix="agent_memory_stream_proposal", field="proposal_id")
        return self


class ImportJobV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-import-job/v1alpha1"] = IMPORT_JOB_VERSION
    intent_id: str
    idempotency_id: str
    attempt: int = Field(ge=1)
    retry_of_job_ref: str | None = None
    job_id: str | None = None

    @field_validator("intent_id", "idempotency_id", "retry_of_job_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_attempt(self) -> Self:
        if (self.attempt == 1) != (self.retry_of_job_ref is None):
            raise ValueError("only the initial import job may omit retry_of_job_ref")
        _derive(self, prefix="agent_memory_import_job", field="job_id")
        return self


class SessionNormalizationReceiptV1Alpha1(_StrictFrozenContract):
    """Content-free normalization evidence; no transcript body is public."""

    contract: Literal["ace.core.agent-memory-session-normalization-receipt/v1alpha1"] = (
        SESSION_NORMALIZATION_RECEIPT_VERSION
    )
    intent_id: str
    adapter_id: str
    immutable_input_digest: str
    session_id: str
    participant_refs: tuple[str, ...]
    turn_refs: tuple[str, ...]
    ordered_event_refs: tuple[str, ...]
    source_span_refs: tuple[str, ...]
    omitted_external_event_refs: tuple[str, ...] = ()
    degraded_reason_refs: tuple[str, ...] = ()
    receipt_id: str | None = None

    @field_validator("intent_id", "adapter_id", "session_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("immutable_input_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _digest(value, name="immutable_input_digest")

    @field_validator(
        "participant_refs", "turn_refs", "source_span_refs", "omitted_external_event_refs", "degraded_reason_refs"
    )
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _refs(value, name=info.field_name)

    @field_validator("ordered_event_refs")
    @classmethod
    def validate_ordered_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > MAX_EVENTS or len(value) != len(set(value)):
            raise ValueError("ordered_event_refs must be non-empty, bounded, and unique")
        for item in value:
            _reference(item, name="ordered_event_refs")
        return value

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        _derive(self, prefix="agent_memory_normalization_receipt", field="receipt_id")
        return self


class SessionIngestionStatusV1Alpha1(_StrictFrozenContract):
    """Append-only import state; every non-initial state binds the prior ledger coordinate."""

    contract: Literal["ace.core.agent-memory-session-ingestion-status/v1alpha1"] = SESSION_INGESTION_STATUS_VERSION
    job_id: str
    state: ImportState
    attempt: int = Field(ge=1)
    previous_state: ImportState | None = None
    prior_coordinate: LedgerCoordinateV1Alpha1 | None = None
    normalization_receipt_ref: str | None = None
    failure_reason_ref: str | None = None
    retry_after: datetime | None = None
    repair_proposal_ref: str | None = None
    recorded_at: datetime
    status_id: str | None = None

    @field_validator("job_id", "normalization_receipt_ref", "failure_reason_ref", "repair_proposal_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @field_validator("retry_after", "recorded_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_transition(self) -> Self:
        initial = self.previous_state is None
        if initial and (self.state is not ImportState.QUEUED or self.prior_coordinate is not None):
            raise ValueError("initial import status must be queued without a prior coordinate")
        if not initial and self.prior_coordinate is None:
            raise ValueError("every non-initial status requires the exact prior ledger coordinate")
        if not initial and self.state not in _STATUS_TRANSITIONS[self.previous_state]:
            raise ValueError("import status transition is not allowed")
        if self.state is ImportState.RETRY_PENDING and self.retry_after is None:
            raise ValueError("retry_pending requires retry_after")
        if self.state is not ImportState.RETRY_PENDING and self.retry_after is not None:
            raise ValueError("retry_after is reserved for retry_pending")
        if self.state is ImportState.REPAIR_REQUIRED and self.repair_proposal_ref is None:
            raise ValueError("repair_required requires repair_proposal_ref")
        if self.state is not ImportState.REPAIR_REQUIRED and self.repair_proposal_ref is not None:
            raise ValueError("repair_proposal_ref is reserved for repair_required")
        if self.state is ImportState.READY and self.normalization_receipt_ref is None:
            raise ValueError("ready requires exact normalization evidence")
        if self.state is not ImportState.READY and self.normalization_receipt_ref is not None:
            raise ValueError("normalization_receipt_ref is reserved for ready")
        if (
            self.state in {ImportState.FAILED, ImportState.PARTIAL, ImportState.STALE}
            and self.failure_reason_ref is None
        ):
            raise ValueError("failed, partial, and stale states require a bounded reason reference")
        if (
            self.state not in {ImportState.FAILED, ImportState.PARTIAL, ImportState.STALE}
            and self.failure_reason_ref is not None
        ):
            raise ValueError("failure_reason_ref is reserved for failed, partial, and stale states")
        _derive(self, prefix="agent_memory_ingestion_status", field="status_id")
        return self


class SessionIngestionReceiptV1Alpha1(_StrictFrozenContract):
    """Content-free durable commit or replay receipt."""

    contract: Literal["ace.core.agent-memory-session-ingestion-receipt/v1alpha1"] = SESSION_INGESTION_RECEIPT_VERSION
    job_id: str
    intent_id: str
    idempotency_id: str
    disposition: IngestionDisposition
    session_id: str | None = None
    normalization_receipt_ref: str | None = None
    ledger_coordinate: LedgerCoordinateV1Alpha1 | None = None
    prior_receipt_ref: str | None = None
    committed_record_refs: tuple[str, ...] = ()
    failure_reason_ref: str | None = None
    receipt_id: str | None = None

    @field_validator(
        "job_id",
        "intent_id",
        "idempotency_id",
        "session_id",
        "normalization_receipt_ref",
        "prior_receipt_ref",
        "failure_reason_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _reference(value, name=info.field_name) if value is not None else None

    @field_validator("committed_record_refs")
    @classmethod
    def normalize_committed_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _refs(value, name="committed_record_refs", maximum=10_000)

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        if self.disposition is IngestionDisposition.COMMITTED:
            if any(
                value is None for value in (self.session_id, self.normalization_receipt_ref, self.ledger_coordinate)
            ):
                raise ValueError("committed receipt requires session, normalization, and ledger evidence")
            if (
                not self.committed_record_refs
                or self.prior_receipt_ref is not None
                or self.failure_reason_ref is not None
            ):
                raise ValueError("committed receipt requires records and forbids replay/failure evidence")
        elif self.disposition is IngestionDisposition.EXACT_REPLAY:
            if (
                self.prior_receipt_ref is None
                or self.session_id is not None
                or self.normalization_receipt_ref is not None
                or self.ledger_coordinate is not None
                or self.committed_record_refs
                or self.failure_reason_ref is not None
            ):
                raise ValueError("exact replay requires only the prior durable receipt reference")
        elif self.disposition is IngestionDisposition.REJECTED:
            if (
                self.failure_reason_ref is None
                or self.session_id is not None
                or self.normalization_receipt_ref is not None
                or self.ledger_coordinate is not None
                or self.prior_receipt_ref is not None
                or self.committed_record_refs
            ):
                raise ValueError("rejection requires a reason and cannot claim committed material")
        elif (
            self.prior_receipt_ref is None
            or self.session_id is not None
            or self.normalization_receipt_ref is not None
            or self.ledger_coordinate is not None
            or self.committed_record_refs
            or self.failure_reason_ref is not None
        ):
            raise ValueError("indeterminate outcome requires receipt lookup evidence and cannot claim a commit")
        _derive(self, prefix="agent_memory_ingestion_receipt", field="receipt_id")
        return self


class EventListQueryV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-event-list-query/v1alpha1"] = EVENT_LIST_QUERY_VERSION
    scope: AgentMemoryScopeV1Alpha1
    session_id: str
    authorization_receipt_ref: str
    after_ordinal: int | None = Field(default=None, ge=0)
    limit: int = Field(default=100, ge=1, le=500)
    query_id: str | None = None

    @field_validator("session_id", "authorization_receipt_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        _derive(self, prefix="agent_memory_event_list_query", field="query_id")
        return self


class EventListReceiptV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-event-list-receipt/v1alpha1"] = EVENT_LIST_RECEIPT_VERSION
    query_id: str
    authorization_receipt_ref: str
    lifecycle_snapshot_ref: str
    ordered_event_refs: tuple[str, ...]
    omitted_count: int = Field(default=0, ge=0)
    next_after_ordinal: int | None = Field(default=None, ge=1)
    receipt_id: str | None = None

    @field_validator("query_id", "authorization_receipt_ref", "lifecycle_snapshot_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("ordered_event_refs")
    @classmethod
    def validate_ordered_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > 500 or len(value) != len(set(value)):
            raise ValueError("ordered_event_refs must be bounded and unique")
        for item in value:
            _reference(item, name="ordered_event_refs")
        return value

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        _derive(self, prefix="agent_memory_event_list_receipt", field="receipt_id")
        return self


class SpanReadQueryV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.core.agent-memory-span-read-query/v1alpha1"] = SPAN_READ_QUERY_VERSION
    scope: AgentMemoryScopeV1Alpha1
    event_ref: str
    span: SourceSpanV1Alpha1
    authorization_receipt_ref: str
    max_bytes: int = Field(default=64_000, ge=1, le=1_000_000)
    query_id: str | None = None

    @field_validator("event_ref", "authorization_receipt_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        _derive(self, prefix="agent_memory_span_read_query", field="query_id")
        return self


class TranscriptViewReceiptV1Alpha1(_StrictFrozenContract):
    """Content-free proof of an authorized, bounded private body read."""

    contract: Literal["ace.core.agent-memory-transcript-view-receipt/v1alpha1"] = TRANSCRIPT_VIEW_RECEIPT_VERSION
    scope_id: str
    query_id: str
    authorization_receipt_ref: str
    lifecycle_snapshot_ref: str
    returned_event_refs: tuple[str, ...]
    returned_span_refs: tuple[str, ...]
    redacted_event_refs: tuple[str, ...] = ()
    omitted_event_refs: tuple[str, ...] = ()
    expires_at: datetime
    receipt_id: str | None = None

    @field_validator("scope_id", "query_id", "authorization_receipt_ref", "lifecycle_snapshot_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("returned_event_refs", "returned_span_refs", "redacted_event_refs", "omitted_event_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _refs(value, name=info.field_name, maximum=500)

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime) -> datetime:
        return _aware(value, name="expires_at")

    @model_validator(mode="after")
    def derive_id(self) -> Self:
        overlaps = set(self.returned_event_refs) & (set(self.redacted_event_refs) | set(self.omitted_event_refs))
        if overlaps:
            raise ValueError("returned events cannot also be redacted or omitted")
        _derive(self, prefix="agent_memory_transcript_view_receipt", field="receipt_id")
        return self


@runtime_checkable
class EpisodicExperienceLedgerReader(Protocol):
    """Opaque bounded reads; implementations authorize before resource lookup."""

    async def list_events(self, query: EventListQueryV1Alpha1) -> EventListReceiptV1Alpha1: ...

    async def read_span(
        self,
        query: SpanReadQueryV1Alpha1,
    ) -> tuple[bytes, TranscriptViewReceiptV1Alpha1]: ...


__all__ = [
    "BATCH_INGESTION_PROPOSAL_VERSION",
    "BatchIngestionProposalV1Alpha1",
    "CANONICAL_EVENT_IDENTITY_VERSION",
    "CANONICAL_PARTICIPANT_IDENTITY_VERSION",
    "CANONICAL_SESSION_IDENTITY_VERSION",
    "CANONICAL_TURN_IDENTITY_VERSION",
    "CanonicalEventIdentityV1Alpha1",
    "CanonicalParticipantIdentityV1Alpha1",
    "CanonicalSessionIdentityV1Alpha1",
    "CanonicalTurnIdentityV1Alpha1",
    "EPISODIC_SOURCE_EVENT_VERSION",
    "EVENT_LIST_QUERY_VERSION",
    "EVENT_LIST_RECEIPT_VERSION",
    "EXTERNAL_EVENT_IDENTITY_VERSION",
    "EpisodicEventKind",
    "EpisodicExperienceLedgerReader",
    "EpisodicSourceEventV1Alpha1",
    "EventListQueryV1Alpha1",
    "EventListReceiptV1Alpha1",
    "ExternalEventIdentityV1Alpha1",
    "IDEMPOTENCY_IDENTITY_VERSION",
    "IDENTITY_DERIVATION_VERSION",
    "IMPORT_JOB_VERSION",
    "IngestionDisposition",
    "IngestionMode",
    "IdempotencyIdentityV1Alpha1",
    "ImportJobV1Alpha1",
    "ImportState",
    "SESSION_IMPORT_INTENT_VERSION",
    "SESSION_INGESTION_RECEIPT_VERSION",
    "SESSION_INGESTION_STATUS_VERSION",
    "SESSION_NORMALIZATION_RECEIPT_VERSION",
    "SOURCE_ADAPTER_IDENTITY_VERSION",
    "SPAN_READ_QUERY_VERSION",
    "STREAM_INGESTION_PROPOSAL_VERSION",
    "SessionImportIntentV1Alpha1",
    "SessionIngestionReceiptV1Alpha1",
    "SessionIngestionStatusV1Alpha1",
    "SessionNormalizationReceiptV1Alpha1",
    "SourceAdapterIdentityV1Alpha1",
    "SpanReadQueryV1Alpha1",
    "StreamIngestionProposalV1Alpha1",
    "TRANSCRIPT_VIEW_RECEIPT_VERSION",
    "TURN_BOUNDARY_POLICY_VERSION",
    "TranscriptViewReceiptV1Alpha1",
]
