"""Provider-neutral application services for the AM1 episodic experience ledger.

Source adapters in this module only parse bounded immutable input into inert
proposals.  Authenticated scope, canonical identity, authority, lifecycle, and
durable commits remain owned by Core.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    ByteRangeSpanV1Alpha1,
    LedgerCoordinateV1Alpha1,
    LifecycleState,
    ParticipantRole,
    SourceProvenanceV1Alpha1,
    StructuredPointerSpanV1Alpha1,
    UnavailableSourceSpanV1Alpha1,
    UnavailableSpanReason,
    WorldTimeKind,
    WorldTimeV1Alpha1,
)
from ace.core.agent_memory_ingestion import (
    BatchIngestionProposalV1Alpha1,
    CanonicalEventIdentityV1Alpha1,
    CanonicalParticipantIdentityV1Alpha1,
    CanonicalSessionIdentityV1Alpha1,
    CanonicalTurnIdentityV1Alpha1,
    EpisodicEventKind,
    EpisodicSourceEventV1Alpha1,
    EventListQueryV1Alpha1,
    EventListReceiptV1Alpha1,
    ExternalEventIdentityV1Alpha1,
    ImportJobV1Alpha1,
    ImportState,
    IngestionDisposition,
    SessionImportIntentV1Alpha1,
    SessionIngestionReceiptV1Alpha1,
    SessionIngestionStatusV1Alpha1,
    SessionNormalizationReceiptV1Alpha1,
    SpanReadQueryV1Alpha1,
    StreamIngestionProposalV1Alpha1,
    TranscriptViewReceiptV1Alpha1,
)
from ace.core.contracts import canonical_hash, stable_id
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1


class AgentMemoryApplicationError(RuntimeError):
    """A bounded AM1 application operation failed closed."""


class AgentMemoryAuthorizationDenied(AgentMemoryApplicationError):
    """A non-disclosing authorization failure."""

    def __init__(self) -> None:
        super().__init__("agent memory operation is unavailable")


class AgentMemoryReplayConflict(AgentMemoryApplicationError):
    """One stable import identity already binds different immutable material."""


AGENT_MEMORY_RECORD_SPACE_PREFIX = "agent_memory"
IMPORT_INTENT_RECORD_KIND = "import_intent"
IMPORT_JOB_RECORD_KIND = "import_job"
EVENT_METADATA_RECORD_KIND = "event_metadata"
EVENT_BODY_RECORD_KIND = "event_body_private"
NORMALIZATION_RECEIPT_RECORD_KIND = "normalization_receipt"
INGESTION_RECEIPT_RECORD_KIND = "ingestion_receipt"
INGESTION_STATUS_RECORD_KIND = "ingestion_status"
PRIVATE_EVENT_BODY_CONTRACT = "ace.application.agent-memory-private-event-body/v1alpha1"
SESSION_NORMALIZATION_CAPTURE_METHOD = "agent_memory.session_normalization/v1"


def _now() -> datetime:
    return datetime.now(UTC)


def _record_space(scope: AgentMemoryScopeV1Alpha1) -> str:
    """Fence records by product plus principal/session/source scope material."""

    return stable_id(
        AGENT_MEMORY_RECORD_SPACE_PREFIX,
        {
            "product_id": scope.product_id,
            "actor_id": scope.actor_id,
            "session_id": scope.session_id,
            "source_id": scope.source_id,
            "visibility": scope.visibility,
            "retention_class": scope.retention_class,
        },
    )


def _transaction_key(intent: SessionImportIntentV1Alpha1) -> str:
    """Stable external idempotency coordinate, deliberately excluding material."""

    return stable_id(
        "agent_memory_import_transaction",
        {
            "product_id": intent.scope.product_id,
            "actor_id": intent.scope.actor_id,
            "external_key": intent.idempotency.external_key,
        },
    )


def _job_ledger_ref(scope: AgentMemoryScopeV1Alpha1, job_id: str) -> str:
    return stable_id(
        "agent_memory_import_job_ledger",
        {"record_space": _record_space(scope), "job_id": job_id},
    )


def _status_record_key(job_id: str, sequence: int) -> str:
    """One immutable CAS slot for each exact job-ledger sequence."""

    return stable_id("agent_memory_status_slot", {"job_id": job_id, "sequence": sequence})


@dataclass(frozen=True, slots=True)
class AuthorizedAgentMemoryUse:
    """One present-tense authorization result, never a reusable credential."""

    product_id: str
    actor_id: str
    operation: str
    subject_ref: str
    authority_receipt_ref: str
    evaluated_at: datetime
    lifecycle_snapshot_ref: str = "lifecycle_snapshot:unspecified"
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE
    expires_at: datetime | None = None
    state_head_precondition: GovernedStateHeadPreconditionV1Alpha1 | None = None

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("authorization evaluation time must include a timezone")
        object.__setattr__(self, "evaluated_at", self.evaluated_at.astimezone(UTC))
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
                raise ValueError("authorization expiry must include a timezone")
            expiry = self.expires_at.astimezone(UTC)
            if expiry <= self.evaluated_at:
                raise ValueError("authorization must remain current after evaluation")
            object.__setattr__(self, "expires_at", expiry)
        if not self.lifecycle_snapshot_ref or len(self.lifecycle_snapshot_ref) > 240:
            raise ValueError("lifecycle snapshot must be a bounded stable reference")

    @property
    def reusable_authority(self) -> bool:
        return False


@runtime_checkable
class AgentMemoryAuthorizationResolver(Protocol):
    """Resolve current authority before any AM1 lookup, append, or body read."""

    async def authorize(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        operation: str,
        subject_ref: str,
        evaluated_at: datetime,
    ) -> AuthorizedAgentMemoryUse: ...


@dataclass(frozen=True, slots=True)
class InertSourceSpanProposal:
    """Adapter-native location proposal with no scope or authority meaning."""

    kind: str
    start_byte: int | None = None
    end_byte: int | None = None
    pointer: str | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "byte_range":
            if (
                self.start_byte is None
                or self.end_byte is None
                or self.start_byte < 0
                or self.end_byte <= self.start_byte
                or self.pointer is not None
                or self.unavailable_reason is not None
            ):
                raise ValueError("byte-range proposal requires one valid half-open range")
            return
        if self.kind == "structured_pointer":
            if (
                self.pointer is None
                or not self.pointer.startswith("/")
                or self.start_byte is not None
                or self.end_byte is not None
                or self.unavailable_reason is not None
            ):
                raise ValueError("structured-pointer proposal requires one JSON Pointer")
            return
        if self.kind == "unavailable":
            if (
                self.unavailable_reason is None
                or self.start_byte is not None
                or self.end_byte is not None
                or self.pointer is not None
            ):
                raise ValueError("unavailable proposal requires one explicit reason")
            return
        raise ValueError("unsupported source-span proposal kind")


@dataclass(frozen=True, slots=True)
class InertSourceEventProposal:
    """One source event proposed by an adapter; its body remains inert data."""

    native_event_coordinate: str
    native_participant_coordinate: str
    role: ParticipantRole
    event_kind: str
    body: str
    native_order: int
    world_time: datetime | None
    source_span: InertSourceSpanProposal

    def __post_init__(self) -> None:
        for name, value in (
            ("native_event_coordinate", self.native_event_coordinate),
            ("native_participant_coordinate", self.native_participant_coordinate),
            ("event_kind", self.event_kind),
        ):
            if not value or value != value.strip() or len(value) > 240:
                raise ValueError(f"{name} must be a bounded stable value")
        if self.native_order < 1:
            raise ValueError("native_order must be positive")
        if len(self.body.encode("utf-8")) > 1_000_000:
            raise ValueError("event body exceeds the adapter bound")
        if self.world_time is not None:
            if self.world_time.tzinfo is None or self.world_time.utcoffset() is None:
                raise ValueError("world time must include a timezone")
            object.__setattr__(self, "world_time", self.world_time.astimezone(UTC))

    @property
    def grants_authority(self) -> bool:
        """Captured event content can never authorize behavior."""

        return False


@dataclass(frozen=True, slots=True)
class InertSessionProposal:
    """One normalized adapter proposal before Core derives canonical identity."""

    native_session_coordinate: str
    events: tuple[InertSourceEventProposal, ...]
    mode: str = "batch"

    def __post_init__(self) -> None:
        if (
            not self.native_session_coordinate
            or self.native_session_coordinate != self.native_session_coordinate.strip()
            or len(self.native_session_coordinate) > 240
        ):
            raise ValueError("native session coordinate must be a bounded stable value")
        if self.mode not in {"batch", "stream"}:
            raise ValueError("proposal mode must be batch or stream")
        if not self.events or len(self.events) > 500:
            raise ValueError("session proposal must contain between 1 and 500 events")
        orders = tuple(event.native_order for event in self.events)
        if len(orders) != len(set(orders)):
            raise ValueError("source event order coordinates must be unique")
        coordinates = [event.native_event_coordinate for event in self.events]
        if len(coordinates) != len(set(coordinates)):
            by_coordinate: dict[str, InertSourceEventProposal] = {}
            for event in self.events:
                prior = by_coordinate.setdefault(event.native_event_coordinate, event)
                if prior != event:
                    raise AgentMemoryReplayConflict("one native event coordinate binds divergent source material")
            raise ValueError("exact duplicate source events must be deduplicated before admission")
        ordered = tuple(sorted(self.events, key=lambda event: (event.native_order, event.native_event_coordinate)))
        object.__setattr__(self, "events", ordered)


@runtime_checkable
class SessionSourceAdapter(Protocol):
    """Credential-free parser for one exact immutable source format."""

    @property
    def adapter_ref(self) -> str: ...

    @property
    def adapter_version(self) -> str: ...

    @property
    def artifact_digest(self) -> str: ...

    def normalize(self, raw: Mapping[str, Any]) -> InertSessionProposal: ...


def _mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AgentMemoryApplicationError(f"{name} must be an object")
    return value


def _sequence(value: Any, *, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AgentMemoryApplicationError(f"{name} must be an ordered collection")
    return value


def _text(value: Any, *, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > 1_000_000 or (not allow_empty and not value):
        raise AgentMemoryApplicationError(f"{name} must be bounded text")
    return value


def _positive_order(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AgentMemoryApplicationError("native event order must be a positive integer")
    return value


def _role(value: Any) -> ParticipantRole:
    try:
        return ParticipantRole(_text(value, name="participant role"))
    except ValueError as exc:
        raise AgentMemoryApplicationError("source supplied an unsupported participant role") from exc


def _optional_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AgentMemoryApplicationError("source event time must be RFC 3339 text or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgentMemoryApplicationError("source event time is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AgentMemoryApplicationError("source event time must include a timezone")
    return parsed.astimezone(UTC)


def _event_stream_span(value: Any) -> InertSourceSpanProposal:
    span = _mapping(value, name="source_span")
    kind = _text(span.get("kind"), name="source span kind")
    if kind == "byte_range":
        start = span.get("start_byte")
        end = span.get("end_byte")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            raise AgentMemoryApplicationError("byte source span coordinates must be integers")
        return InertSourceSpanProposal(kind=kind, start_byte=start, end_byte=end)
    if kind == "structured_pointer":
        return InertSourceSpanProposal(kind=kind, pointer=_text(span.get("pointer"), name="pointer"))
    if kind == "unavailable":
        return InertSourceSpanProposal(
            kind=kind,
            unavailable_reason=_text(span.get("reason"), name="unavailable span reason"),
        )
    raise AgentMemoryApplicationError("source supplied an unsupported span kind")


class StructuredEventStreamAdapter:
    """Normalize an event-stream shaped fixture without accepting its scope."""

    adapter_ref = "session_adapter:event-stream-v1"
    adapter_version = "1.0.0"
    artifact_digest = "sha256:" + "1" * 64

    def normalize(self, raw: Mapping[str, Any]) -> InertSessionProposal:
        source = _mapping(raw, name="event-stream input")
        events: list[InertSourceEventProposal] = []
        for item in _sequence(source.get("events"), name="events"):
            event = _mapping(item, name="event")
            events.append(
                InertSourceEventProposal(
                    native_event_coordinate=_text(
                        event.get("native_event_coordinate"),
                        name="native_event_coordinate",
                    ),
                    native_participant_coordinate=_text(
                        event.get("native_participant_coordinate"),
                        name="native_participant_coordinate",
                    ),
                    role=_role(event.get("role")),
                    event_kind=_text(event.get("kind"), name="event kind"),
                    body=_text(event.get("body"), name="event body", allow_empty=True),
                    native_order=_positive_order(event.get("native_order")),
                    world_time=_optional_time(event.get("world_time")),
                    source_span=_event_stream_span(event.get("source_span")),
                )
            )
        return InertSessionProposal(
            native_session_coordinate=_text(
                source.get("native_session_coordinate"),
                name="native_session_coordinate",
            ),
            events=tuple(events),
        )


class TranscriptExportAdapter:
    """Normalize a differently nested transcript export into the same proposal."""

    adapter_ref = "session_adapter:transcript-export-v1"
    adapter_version = "1.0.0"
    artifact_digest = "sha256:" + "2" * 64

    def normalize(self, raw: Mapping[str, Any]) -> InertSessionProposal:
        source = _mapping(raw, name="transcript-export input")
        events: list[InertSourceEventProposal] = []
        for item in _sequence(source.get("messages"), name="messages"):
            message = _mapping(item, name="message")
            speaker = _mapping(message.get("speaker"), name="speaker")
            payload = _mapping(message.get("payload"), name="payload")
            locator = message.get("locator")
            if locator is None:
                span = InertSourceSpanProposal(
                    kind="unavailable",
                    unavailable_reason="adapter_unsupported",
                )
            else:
                exact = _mapping(locator, name="locator")
                start = exact.get("utf8_start")
                end = exact.get("utf8_end")
                if (
                    not isinstance(start, int)
                    or isinstance(start, bool)
                    or not isinstance(end, int)
                    or isinstance(end, bool)
                ):
                    raise AgentMemoryApplicationError("UTF-8 locator coordinates must be integers")
                span = InertSourceSpanProposal(
                    kind="byte_range",
                    start_byte=start,
                    end_byte=end,
                )
            events.append(
                InertSourceEventProposal(
                    native_event_coordinate=_text(message.get("message_key"), name="message_key"),
                    native_participant_coordinate=_text(speaker.get("key"), name="speaker key"),
                    role=_role(speaker.get("type")),
                    event_kind=_text(payload.get("type"), name="payload type"),
                    body=_text(payload.get("text"), name="payload text", allow_empty=True),
                    native_order=_positive_order(message.get("position")),
                    world_time=_optional_time(message.get("occurred_at")),
                    source_span=span,
                )
            )
        return InertSessionProposal(
            native_session_coordinate=_text(source.get("conversation_key"), name="conversation_key"),
            events=tuple(events),
        )


class ExplicitSessionAdapterRegistry:
    """Resolve one exact adapter identity; unknown identities never fall back."""

    def __init__(self, adapters: Sequence[SessionSourceAdapter] = ()) -> None:
        self._adapters: dict[tuple[str, str], SessionSourceAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: SessionSourceAdapter) -> None:
        if not isinstance(adapter, SessionSourceAdapter):
            raise TypeError("adapter must implement the bounded session source protocol")
        identity = (adapter.adapter_ref, adapter.adapter_version)
        if identity in self._adapters:
            raise ValueError("session source adapter identity is already registered")
        self._adapters[identity] = adapter

    def resolve(self, *, adapter_ref: str, adapter_version: str) -> SessionSourceAdapter:
        adapter = self._adapters.get((adapter_ref, adapter_version))
        if adapter is None:
            raise AgentMemoryApplicationError("exact session source adapter is unavailable")
        return adapter

    def resolve_identity(self, intent: SessionImportIntentV1Alpha1) -> SessionSourceAdapter:
        adapter = self.resolve(
            adapter_ref=intent.adapter.adapter_ref,
            adapter_version=intent.adapter.adapter_version,
        )
        if adapter.artifact_digest != intent.adapter.artifact_digest:
            raise AgentMemoryApplicationError("exact session source adapter artifact is unavailable")
        return adapter

    @classmethod
    def fixture_adapters(cls) -> ExplicitSessionAdapterRegistry:
        return cls((StructuredEventStreamAdapter(), TranscriptExportAdapter()))


@dataclass(frozen=True, slots=True)
class SessionIngestionAdmission:
    """Private application result plus its content-free public receipt."""

    proposal: BatchIngestionProposalV1Alpha1
    normalization_receipt: SessionNormalizationReceiptV1Alpha1
    ingestion_receipt: SessionIngestionReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


@dataclass(frozen=True, slots=True)
class ImportStatusAdmission:
    """One separately committed retry, repair, partial, stale, or failed status."""

    status: SessionIngestionStatusV1Alpha1
    ledger_coordinate: LedgerCoordinateV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


@dataclass(frozen=True, slots=True)
class AuthorizedEventListing:
    receipt: EventListReceiptV1Alpha1
    events: tuple[EpisodicSourceEventV1Alpha1, ...]


@dataclass(frozen=True, slots=True)
class AuthorizedSpanRead:
    """Private content channel; the public receipt never carries ``content``."""

    content: str
    receipt: TranscriptViewReceiptV1Alpha1


def _event_kind(value: str) -> EpisodicEventKind:
    aliases = {"tool_use": EpisodicEventKind.TOOL_CALL, "error": EpisodicEventKind.OTHER}
    try:
        return aliases.get(value, EpisodicEventKind(value))
    except ValueError as exc:
        raise AgentMemoryApplicationError("source supplied an unsupported event kind") from exc


def _span(intent: SessionImportIntentV1Alpha1, proposed: InertSourceSpanProposal):
    source_version = intent.input_source_version_id
    if proposed.kind == "byte_range":
        return ByteRangeSpanV1Alpha1(
            source_version_id=source_version,
            start_byte=proposed.start_byte,
            end_byte=proposed.end_byte,
        )
    if proposed.kind == "structured_pointer":
        return StructuredPointerSpanV1Alpha1(
            source_version_id=source_version,
            pointer=str(proposed.pointer),
        )
    try:
        reason = UnavailableSpanReason(str(proposed.unavailable_reason))
    except ValueError:
        reason = UnavailableSpanReason.UNKNOWN
    return UnavailableSourceSpanV1Alpha1(
        source_version_id=source_version,
        reason=reason,
        detail=str(proposed.unavailable_reason),
    )


def normalize_session_proposal(
    *,
    intent: SessionImportIntentV1Alpha1,
    proposal: InertSessionProposal,
) -> tuple[
    BatchIngestionProposalV1Alpha1,
    SessionNormalizationReceiptV1Alpha1,
    tuple[CanonicalTurnIdentityV1Alpha1, ...],
]:
    """Derive canonical Core material from one inert adapter proposal."""

    if proposal.native_session_coordinate != intent.native_session_coordinate:
        raise AgentMemoryApplicationError("adapter session coordinate does not match the exact import intent")
    if len(proposal.events) > intent.max_events:
        raise AgentMemoryApplicationError("normalized event count exceeds the import bound")
    total_bytes = sum(len(event.body.encode("utf-8")) for event in proposal.events)
    if total_bytes > intent.max_content_bytes:
        raise AgentMemoryApplicationError("normalized content exceeds the import byte bound")
    session = CanonicalSessionIdentityV1Alpha1(
        scope_id=str(intent.scope.scope_id),
        source_id=intent.input_source_ref,
        source_version_id=intent.input_source_version_id,
        native_session_coordinate=proposal.native_session_coordinate,
        task_ref=intent.task_ref,
        decision_ref=intent.decision_ref,
    )
    events: list[EpisodicSourceEventV1Alpha1] = []
    turns: list[CanonicalTurnIdentityV1Alpha1] = []
    for ordinal, proposed in enumerate(proposal.events, start=1):
        digest = "sha256:" + canonical_hash(proposed.body)
        kind = _event_kind(proposed.event_kind)
        participant = CanonicalParticipantIdentityV1Alpha1(
            session_id=str(session.session_id),
            native_participant_coordinate=proposed.native_participant_coordinate,
            role=proposed.role,
        )
        external = ExternalEventIdentityV1Alpha1(
            source_version_id=intent.input_source_version_id,
            native_session_coordinate=proposal.native_session_coordinate,
            native_event_coordinate=proposed.native_event_coordinate,
        )
        identity = CanonicalEventIdentityV1Alpha1(
            session_id=str(session.session_id),
            source_version_id=intent.input_source_version_id,
            native_event_coordinate=proposed.native_event_coordinate,
            content_digest=digest,
            event_kind=kind,
        )
        exact_span = _span(intent, proposed.source_span)
        event = EpisodicSourceEventV1Alpha1(
            scope=intent.scope,
            session=session,
            participant=participant,
            external_event=external,
            identity=identity,
            provenance=SourceProvenanceV1Alpha1(
                source_id=intent.input_source_ref,
                source_version_id=intent.input_source_version_id,
                content_digest=intent.immutable_input_digest,
                span=exact_span,
                acquisition_receipt_ref=intent.input_acquisition_receipt_ref,
                capture_method_ref=SESSION_NORMALIZATION_CAPTURE_METHOD,
            ),
            knowledge_time=intent.source_knowledge_time,
            world_time=(
                WorldTimeV1Alpha1(kind=WorldTimeKind.INSTANT, occurred_at=proposed.world_time)
                if proposed.world_time is not None
                else WorldTimeV1Alpha1(kind=WorldTimeKind.UNKNOWN, unknown_reason="missing_from_source")
            ),
            processing_ordinal=ordinal,
        )
        events.append(event)
        turns.append(
            CanonicalTurnIdentityV1Alpha1(
                session_id=str(session.session_id),
                participant_id=str(participant.participant_id),
                ordered_event_refs=(str(identity.event_id),),
            )
        )
    batch = BatchIngestionProposalV1Alpha1(
        intent_id=str(intent.intent_id),
        adapter_id=str(intent.adapter.adapter_id),
        events=tuple(events),
    )
    normalization = SessionNormalizationReceiptV1Alpha1(
        intent_id=str(intent.intent_id),
        adapter_id=str(intent.adapter.adapter_id),
        immutable_input_digest=intent.immutable_input_digest,
        session_id=str(session.session_id),
        participant_refs=tuple(str(event.participant.participant_id) for event in events),
        turn_refs=tuple(str(turn.turn_id) for turn in turns),
        ordered_event_refs=tuple(str(event.identity.event_id) for event in events),
        source_span_refs=tuple(str(event.provenance.span.span_id) for event in events),
    )
    return batch, normalization, tuple(turns)


def normalized_input_digest(proposal: InertSessionProposal) -> str:
    """Digest provider-free normalized source material shared by both adapters."""

    return "sha256:" + canonical_hash(
        {
            "native_session_coordinate": proposal.native_session_coordinate,
            "events": [
                {
                    "native_event_coordinate": event.native_event_coordinate,
                    "native_participant_coordinate": event.native_participant_coordinate,
                    "role": event.role.value,
                    "event_kind": event.event_kind,
                    "body": event.body,
                    "native_order": event.native_order,
                    "world_time": event.world_time.isoformat() if event.world_time is not None else None,
                    "source_span": {
                        "kind": event.source_span.kind,
                        "start_byte": event.source_span.start_byte,
                        "end_byte": event.source_span.end_byte,
                        "pointer": event.source_span.pointer,
                        "unavailable_reason": event.source_span.unavailable_reason,
                    },
                }
                for event in proposal.events
            ],
        }
    )


def normalize_stream_proposals(
    *,
    intent: SessionImportIntentV1Alpha1,
    proposal: InertSessionProposal,
) -> tuple[StreamIngestionProposalV1Alpha1, ...]:
    """Project the canonical batch material as a predecessor-bound stream."""

    batch, _, _ = normalize_session_proposal(intent=intent, proposal=proposal)
    stream: list[StreamIngestionProposalV1Alpha1] = []
    prior: str | None = None
    for index, event in enumerate(batch.events, start=1):
        item = StreamIngestionProposalV1Alpha1(
            intent_id=str(intent.intent_id),
            adapter_id=str(intent.adapter.adapter_id),
            event=event,
            stream_ordinal=index,
            prior_proposal_ref=prior,
            terminal=index == len(batch.events),
        )
        stream.append(item)
        prior = str(item.proposal_id)
    return tuple(stream)


class _AuthorizedService:
    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authorization: AgentMemoryAuthorizationResolver,
        clock: Callable[[], datetime],
    ) -> None:
        self.store = store
        self.authorization = authorization
        self.clock = clock

    async def _authorize(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        operation: str,
        subject_ref: str,
    ) -> AuthorizedAgentMemoryUse:
        evaluated = self.clock()
        if evaluated.tzinfo is None or evaluated.utcoffset() is None:
            raise AgentMemoryApplicationError("service clock must return a timezone-aware value")
        try:
            use = await self.authorization.authorize(
                context=context,
                scope=scope,
                operation=operation,
                subject_ref=subject_ref,
                evaluated_at=evaluated.astimezone(UTC),
            )
        except Exception as exc:
            raise AgentMemoryAuthorizationDenied() from exc
        if (
            use.product_id != scope.product_id
            or use.actor_id != scope.actor_id
            or use.operation != operation
            or use.subject_ref != subject_ref
            or context.product_id != scope.product_id
            or context.actor_ref != scope.actor_id
            or not (context.authenticated_at <= evaluated.astimezone(UTC) < context.expires_at)
            or use.authority_receipt_ref != scope.authority_receipt_ref
            or use.evaluated_at != evaluated.astimezone(UTC)
            or (use.expires_at is not None and use.expires_at <= evaluated.astimezone(UTC))
            or use.lifecycle_snapshot_ref == "lifecycle_snapshot:unspecified"
            or use.lifecycle_state is not LifecycleState.ACTIVE
        ):
            raise AgentMemoryAuthorizationDenied()
        return use


def _immutable_record(
    payload: Any,
    *,
    scope: AgentMemoryScopeV1Alpha1,
    kind: str,
    key: str,
    when: datetime,
    order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=scope.product_id,
        record_space=_record_space(scope),
        record_kind=kind,
        record_key=key,
        payload_contract=payload.contract,
        payload=payload.model_dump(mode="python"),
        as_of=when,
        available_at=when,
        processing_order=order,
    )


def _reopen_contract(model: Any, payload: Mapping[str, Any]) -> Any:
    """Revalidate both in-memory Python and durable JSON primitive payloads."""

    try:
        # Surreal reopens canonical payloads as JSON primitives, while the
        # in-memory conformance store retains Python datetime/enum values.
        # Non-strict parsing is confined to this persistence boundary; the
        # constructed frozen model still runs every identity and binding check.
        return model.model_validate(payload, strict=False)
    except (TypeError, ValueError) as exc:
        raise AgentMemoryApplicationError("durable Agent Memory contract failed exact validation") from exc


class SessionIngestionService(_AuthorizedService):
    """Authorize, normalize, atomically append, replay, and recover AM1 imports."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authorization: AgentMemoryAuthorizationResolver,
        adapters: ExplicitSessionAdapterRegistry,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        super().__init__(store=store, authorization=authorization, clock=clock)
        self.adapters = adapters

    async def ingest(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        intent: SessionImportIntentV1Alpha1,
        raw_input: Mapping[str, Any],
    ) -> SessionIngestionAdmission:
        validated = SessionImportIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        await self._authorize(
            context=context,
            scope=validated.scope,
            operation="ingest_agent_memory",
            subject_ref=str(validated.intent_id),
        )
        adapter = self.adapters.resolve_identity(validated)
        inert = adapter.normalize(raw_input)
        if normalized_input_digest(inert) != validated.immutable_input_digest:
            raise AgentMemoryReplayConflict(
                "divergent import intent: immutable input digest does not match normalized source material"
            )
        replay = await self._load_replay(context=context, intent=validated)
        if replay is not None:
            return replay
        batch, normalization, _ = normalize_session_proposal(intent=validated, proposal=inert)
        job = ImportJobV1Alpha1(
            intent_id=str(validated.intent_id),
            idempotency_id=str(validated.idempotency.idempotency_id),
            attempt=1,
        )
        committed_at = self.clock()
        if committed_at.tzinfo is None or committed_at.utcoffset() is None:
            raise AgentMemoryApplicationError("service clock must return a timezone-aware value")
        committed_at = committed_at.astimezone(UTC)
        queued_status = SessionIngestionStatusV1Alpha1(
            job_id=str(job.job_id),
            state=ImportState.QUEUED,
            attempt=1,
            recorded_at=committed_at,
        )
        ledger_ref = _job_ledger_ref(validated.scope, str(job.job_id))
        queued_coordinate = LedgerCoordinateV1Alpha1(
            ledger_ref=ledger_ref,
            sequence=1,
            event_ref=str(queued_status.status_id),
            committed_at=committed_at,
        )
        normalizing_status = SessionIngestionStatusV1Alpha1(
            job_id=str(job.job_id),
            state=ImportState.NORMALIZING,
            attempt=1,
            previous_state=ImportState.QUEUED,
            prior_coordinate=queued_coordinate,
            recorded_at=committed_at,
        )
        normalizing_coordinate = LedgerCoordinateV1Alpha1(
            ledger_ref=ledger_ref,
            sequence=2,
            event_ref=str(normalizing_status.status_id),
            committed_at=committed_at,
        )
        ready_status = SessionIngestionStatusV1Alpha1(
            job_id=str(job.job_id),
            state=ImportState.READY,
            attempt=1,
            previous_state=ImportState.NORMALIZING,
            prior_coordinate=normalizing_coordinate,
            normalization_receipt_ref=str(normalization.receipt_id),
            recorded_at=committed_at,
        )
        records: list[ImmutableRecordV1] = []
        records.append(
            _immutable_record(
                validated,
                scope=validated.scope,
                kind=IMPORT_INTENT_RECORD_KIND,
                key=str(validated.intent_id),
                when=committed_at,
                order=len(records),
            )
        )
        records.append(
            _immutable_record(
                job,
                scope=validated.scope,
                kind=IMPORT_JOB_RECORD_KIND,
                key=str(job.job_id),
                when=committed_at,
                order=len(records),
            )
        )
        for event, source in zip(batch.events, inert.events, strict=True):
            records.append(
                _immutable_record(
                    event,
                    scope=validated.scope,
                    kind=EVENT_METADATA_RECORD_KIND,
                    key=str(event.identity.event_id),
                    when=committed_at,
                    order=len(records),
                )
            )
            body_payload = {
                "contract": PRIVATE_EVENT_BODY_CONTRACT,
                "event_ref": str(event.identity.event_id),
                "content_digest": str(event.identity.content_digest),
                "body": source.body,
            }
            body_record = ImmutableRecordV1(
                product_id=validated.scope.product_id,
                record_space=_record_space(validated.scope),
                record_kind=EVENT_BODY_RECORD_KIND,
                record_key=str(event.identity.event_id),
                payload_contract=PRIVATE_EVENT_BODY_CONTRACT,
                payload=body_payload,
                as_of=committed_at,
                available_at=committed_at,
                processing_order=len(records),
            )
            records.append(body_record)
        records.append(
            _immutable_record(
                normalization,
                scope=validated.scope,
                kind=NORMALIZATION_RECEIPT_RECORD_KIND,
                key=str(normalization.receipt_id),
                when=committed_at,
                order=len(records),
            )
        )
        for sequence, status in enumerate((queued_status, normalizing_status, ready_status), start=1):
            records.append(
                _immutable_record(
                    status,
                    scope=validated.scope,
                    kind=INGESTION_STATUS_RECORD_KIND,
                    key=_status_record_key(str(job.job_id), sequence),
                    when=committed_at,
                    order=len(records),
                )
            )
        coordinate = LedgerCoordinateV1Alpha1(
            ledger_ref=ledger_ref,
            sequence=3,
            event_ref=str(ready_status.status_id),
            committed_at=committed_at,
        )
        public_refs = tuple(
            str(record.storage_id)
            for record in records
            if record.record_kind not in {EVENT_BODY_RECORD_KIND, IMPORT_INTENT_RECORD_KIND, IMPORT_JOB_RECORD_KIND}
        )
        ingestion = SessionIngestionReceiptV1Alpha1(
            job_id=str(job.job_id),
            intent_id=str(validated.intent_id),
            idempotency_id=str(validated.idempotency.idempotency_id),
            disposition=IngestionDisposition.COMMITTED,
            session_id=normalization.session_id,
            normalization_receipt_ref=str(normalization.receipt_id),
            ledger_coordinate=coordinate,
            committed_record_refs=public_refs,
        )
        records.append(
            _immutable_record(
                ingestion,
                scope=validated.scope,
                kind=INGESTION_RECEIPT_RECORD_KIND,
                key=str(ingestion.receipt_id),
                when=committed_at,
                order=len(records),
            )
        )
        final_use = await self._authorize(
            context=context,
            scope=validated.scope,
            operation="ingest_agent_memory",
            subject_ref=str(validated.intent_id),
        )
        request = AppendOnlyTransactionRequestV1(
            product_id=validated.scope.product_id,
            record_space=_record_space(validated.scope),
            transaction_key=_transaction_key(validated),
            records=tuple(records),
            submitted_at=committed_at,
            governed_state_preconditions=(
                (final_use.state_head_precondition,) if final_use.state_head_precondition is not None else ()
            ),
        )
        try:
            transaction = await self.store.append(request)
        except ImmutableRecordReplayConflict as exc:
            # Another exact caller may have committed after our receipt check.
            # Classify only from the durable winner; never infer divergence from
            # a process-local timestamp or a losing append attempt.
            await self._authorize(
                context=context,
                scope=validated.scope,
                operation="ingest_agent_memory",
                subject_ref=str(validated.intent_id),
            )
            recovered = await self._load_replay(context=context, intent=validated)
            if recovered is not None:
                return recovered
            raise AgentMemoryReplayConflict("idempotency identity binds divergent import material") from exc
        except ImmutableRecordPersistenceError:
            # Resolve an unknown winner from its exact durable receipt before any retry.
            await self._authorize(
                context=context,
                scope=validated.scope,
                operation="ingest_agent_memory",
                subject_ref=str(validated.intent_id),
            )
            recovered = await self._load_replay(context=context, intent=validated)
            if recovered is not None:
                return recovered
            raise
        return SessionIngestionAdmission(batch, normalization, ingestion, transaction, False)

    async def record_status(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        scope: AgentMemoryScopeV1Alpha1,
        status: SessionIngestionStatusV1Alpha1,
    ) -> ImportStatusAdmission:
        """Append an authorized non-initial status against its exact predecessor."""

        validated = SessionIngestionStatusV1Alpha1.model_validate(status.model_dump(mode="python"))
        if validated.prior_coordinate is None:
            raise AgentMemoryApplicationError("separate status append requires an exact prior coordinate")
        await self._authorize(
            context=context,
            scope=scope,
            operation="repair_agent_memory_import",
            subject_ref=validated.job_id,
        )
        expected_ledger = _job_ledger_ref(scope, validated.job_id)
        prior = validated.prior_coordinate
        if prior.ledger_ref != expected_ledger:
            raise AgentMemoryAuthorizationDenied()
        prior_storage_id = immutable_record_storage_id(
            product_id=scope.product_id,
            record_space=_record_space(scope),
            record_kind=INGESTION_STATUS_RECORD_KIND,
            record_key=_status_record_key(validated.job_id, prior.sequence),
        )
        prior_record = await self.store.load_record(
            prior_storage_id,
            product_id=scope.product_id,
            record_space=_record_space(scope),
            record_kind=INGESTION_STATUS_RECORD_KIND,
        )
        if prior_record is None:
            raise AgentMemoryAuthorizationDenied()
        try:
            prior_status = _reopen_contract(SessionIngestionStatusV1Alpha1, prior_record.payload)
        except (TypeError, ValueError) as exc:
            raise AgentMemoryApplicationError("durable import status failed exact validation") from exc
        if (
            prior_status.job_id != validated.job_id
            or prior_status.status_id != prior.event_ref
            or prior_status.state != validated.previous_state
            or prior_record.available_at != prior.committed_at
        ):
            raise AgentMemoryAuthorizationDenied()
        when = self.clock()
        if when.tzinfo is None or when.utcoffset() is None:
            raise AgentMemoryApplicationError("service clock must return a timezone-aware value")
        when = when.astimezone(UTC)
        record = _immutable_record(
            validated,
            scope=scope,
            kind=INGESTION_STATUS_RECORD_KIND,
            key=_status_record_key(validated.job_id, prior.sequence + 1),
            when=when,
            order=0,
        )
        use = await self._authorize(
            context=context,
            scope=scope,
            operation="repair_agent_memory_import",
            subject_ref=validated.job_id,
        )
        request = AppendOnlyTransactionRequestV1(
            product_id=scope.product_id,
            record_space=_record_space(scope),
            transaction_key=stable_id(
                "agent_memory_status_successor",
                {
                    "job_id": validated.job_id,
                    "sequence": prior.sequence + 1,
                },
            ),
            records=(record,),
            submitted_at=when,
            governed_state_preconditions=(
                (use.state_head_precondition,) if use.state_head_precondition is not None else ()
            ),
        )
        successor_coordinate = LedgerCoordinateV1Alpha1(
            ledger_ref=expected_ledger,
            sequence=prior.sequence + 1,
            event_ref=str(validated.status_id),
            committed_at=when,
        )
        try:
            receipt = await self.store.append(request)
        except ImmutableRecordReplayConflict as exc:
            await self._authorize(
                context=context,
                scope=scope,
                operation="repair_agent_memory_import",
                subject_ref=validated.job_id,
            )
            existing = await self.store.load_transaction_receipt(
                product_id=scope.product_id,
                record_space=_record_space(scope),
                transaction_key=request.transaction_key,
            )
            if existing is not None and len(existing.records) == 1:
                reference = existing.records[0]
                stored = await self.store.load_record(
                    reference.storage_id,
                    product_id=scope.product_id,
                    record_space=_record_space(scope),
                    record_kind=INGESTION_STATUS_RECORD_KIND,
                )
                if stored is not None:
                    existing_status = _reopen_contract(SessionIngestionStatusV1Alpha1, stored.payload)
                    if existing_status == validated:
                        coordinate = successor_coordinate.model_copy(update={"committed_at": existing.committed_at})
                        return ImportStatusAdmission(existing_status, coordinate, existing, True)
            raise AgentMemoryReplayConflict(
                "exact prior import coordinate already binds a different successor"
            ) from exc
        return ImportStatusAdmission(validated, successor_coordinate, receipt, False)

    async def replay(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        intent: SessionImportIntentV1Alpha1,
    ) -> SessionIngestionAdmission | None:
        validated = SessionImportIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        await self._authorize(
            context=context,
            scope=validated.scope,
            operation="ingest_agent_memory",
            subject_ref=str(validated.intent_id),
        )
        return await self._load_replay(context=context, intent=validated)

    async def _load_replay(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        intent: SessionImportIntentV1Alpha1,
    ) -> SessionIngestionAdmission | None:
        await self._authorize(
            context=context,
            scope=intent.scope,
            operation="ingest_agent_memory",
            subject_ref=str(intent.intent_id),
        )
        transaction = await self.store.load_transaction_receipt(
            product_id=intent.scope.product_id,
            record_space=_record_space(intent.scope),
            transaction_key=_transaction_key(intent),
        )
        if transaction is None:
            return None
        loaded: dict[str, ImmutableRecordV1] = {}
        for reference in transaction.records:
            await self._authorize(
                context=context,
                scope=intent.scope,
                operation="ingest_agent_memory",
                subject_ref=str(intent.intent_id),
            )
            record = await self.store.load_record(
                reference.storage_id,
                product_id=intent.scope.product_id,
                record_space=_record_space(intent.scope),
                record_kind=reference.record_kind,
            )
            if record is None or record.reference() != reference:
                raise AgentMemoryApplicationError("durable import transaction is incomplete")
            loaded[record.record_kind + ":" + record.record_key] = record
        intent_record = loaded.get(IMPORT_INTENT_RECORD_KIND + ":" + str(intent.intent_id))
        if intent_record is None:
            raise AgentMemoryReplayConflict("idempotency identity has no exact import intent")
        stored_intent = _reopen_contract(SessionImportIntentV1Alpha1, intent_record.payload)
        if stored_intent != intent:
            raise AgentMemoryReplayConflict("idempotency identity binds a divergent import intent")
        normalization_records = [r for r in loaded.values() if r.record_kind == NORMALIZATION_RECEIPT_RECORD_KIND]
        ingestion_records = [r for r in loaded.values() if r.record_kind == INGESTION_RECEIPT_RECORD_KIND]
        event_records = sorted(
            (r for r in loaded.values() if r.record_kind == EVENT_METADATA_RECORD_KIND),
            key=lambda r: r.processing_order,
        )
        if len(normalization_records) != 1 or len(ingestion_records) != 1 or not event_records:
            raise AgentMemoryApplicationError("durable import transaction lost canonical records")
        events = tuple(_reopen_contract(EpisodicSourceEventV1Alpha1, r.payload) for r in event_records)
        batch = BatchIngestionProposalV1Alpha1(
            intent_id=str(intent.intent_id), adapter_id=str(intent.adapter.adapter_id), events=events
        )
        normalization = _reopen_contract(SessionNormalizationReceiptV1Alpha1, normalization_records[0].payload)
        ingestion = _reopen_contract(SessionIngestionReceiptV1Alpha1, ingestion_records[0].payload)
        return SessionIngestionAdmission(batch, normalization, ingestion, transaction, True)


class SessionReadService(_AuthorizedService):
    """Authorized opaque event listings and exact private span retrieval."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authorization: AgentMemoryAuthorizationResolver,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        super().__init__(store=store, authorization=authorization, clock=clock)

    async def list_events(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        query: EventListQueryV1Alpha1,
    ) -> AuthorizedEventListing:
        use = await self._authorize(
            context=context, scope=query.scope, operation="read_agent_memory", subject_ref=str(query.query_id)
        )
        records = await self.store.read_as_of(
            product_id=query.scope.product_id,
            record_space=_record_space(query.scope),
            record_kind=EVENT_METADATA_RECORD_KIND,
            available_at=use.evaluated_at,
        )
        events = sorted(
            (_reopen_contract(EpisodicSourceEventV1Alpha1, record.payload) for record in records),
            key=lambda event: event.processing_ordinal,
        )
        filtered = [
            event
            for event in events
            if event.session.session_id == query.session_id
            and (query.after_ordinal is None or event.processing_ordinal > query.after_ordinal)
        ]
        selected = tuple(filtered[: query.limit])
        receipt = EventListReceiptV1Alpha1(
            query_id=str(query.query_id),
            authorization_receipt_ref=use.authority_receipt_ref,
            lifecycle_snapshot_ref=use.lifecycle_snapshot_ref,
            ordered_event_refs=tuple(str(event.identity.event_id) for event in selected),
            omitted_count=max(0, len(filtered) - len(selected)),
            next_after_ordinal=(
                selected[-1].processing_ordinal if len(filtered) > len(selected) and selected else None
            ),
        )
        return AuthorizedEventListing(receipt=receipt, events=selected)

    async def read_span(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        query: SpanReadQueryV1Alpha1,
    ) -> AuthorizedSpanRead:
        await self._authorize(
            context=context, scope=query.scope, operation="read_agent_memory_span", subject_ref=str(query.query_id)
        )
        metadata_id = immutable_record_storage_id(
            product_id=query.scope.product_id,
            record_space=_record_space(query.scope),
            record_kind=EVENT_METADATA_RECORD_KIND,
            record_key=query.event_ref,
        )
        metadata = await self.store.load_record(
            metadata_id,
            product_id=query.scope.product_id,
            record_space=_record_space(query.scope),
            record_kind=EVENT_METADATA_RECORD_KIND,
        )
        if metadata is None:
            raise AgentMemoryAuthorizationDenied()
        event = _reopen_contract(EpisodicSourceEventV1Alpha1, metadata.payload)
        if event.provenance.span != query.span:
            raise AgentMemoryAuthorizationDenied()
        use = await self._authorize(
            context=context, scope=query.scope, operation="read_agent_memory_span", subject_ref=str(query.query_id)
        )
        body_id = immutable_record_storage_id(
            product_id=query.scope.product_id,
            record_space=_record_space(query.scope),
            record_kind=EVENT_BODY_RECORD_KIND,
            record_key=query.event_ref,
        )
        body = await self.store.load_record(
            body_id,
            product_id=query.scope.product_id,
            record_space=_record_space(query.scope),
            record_kind=EVENT_BODY_RECORD_KIND,
        )
        if body is None or body.payload.get("event_ref") != query.event_ref:
            raise AgentMemoryAuthorizationDenied()
        content = body.payload.get("body")
        if not isinstance(content, str) or len(content.encode("utf-8")) > query.max_bytes:
            raise AgentMemoryAuthorizationDenied()
        receipt = TranscriptViewReceiptV1Alpha1(
            scope_id=str(query.scope.scope_id),
            query_id=str(query.query_id),
            authorization_receipt_ref=use.authority_receipt_ref,
            lifecycle_snapshot_ref=use.lifecycle_snapshot_ref,
            returned_event_refs=(query.event_ref,),
            returned_span_refs=(str(query.span.span_id),),
            expires_at=min(
                use.expires_at or (use.evaluated_at + timedelta(minutes=5)),
                use.evaluated_at + timedelta(minutes=5),
            ),
        )
        return AuthorizedSpanRead(content=content, receipt=receipt)


__all__ = [
    "AgentMemoryApplicationError",
    "AgentMemoryAuthorizationDenied",
    "AgentMemoryAuthorizationResolver",
    "AgentMemoryReplayConflict",
    "AuthorizedEventListing",
    "AuthorizedAgentMemoryUse",
    "AuthorizedSpanRead",
    "ExplicitSessionAdapterRegistry",
    "InertSessionProposal",
    "InertSourceEventProposal",
    "InertSourceSpanProposal",
    "ImportStatusAdmission",
    "SessionSourceAdapter",
    "SessionIngestionAdmission",
    "SessionIngestionService",
    "SessionReadService",
    "StructuredEventStreamAdapter",
    "TranscriptExportAdapter",
    "normalize_session_proposal",
    "normalize_stream_proposals",
    "normalized_input_digest",
]
