from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    ByteRangeSpanV1Alpha1,
    KnowledgeTimeKind,
    KnowledgeTimeV1Alpha1,
    LedgerCoordinateV1Alpha1,
    MemoryVisibility,
    ParticipantRole,
    RetentionClass,
    SourceProvenanceV1Alpha1,
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
    ExternalEventIdentityV1Alpha1,
    IdempotencyIdentityV1Alpha1,
    ImportJobV1Alpha1,
    ImportState,
    IngestionDisposition,
    IngestionMode,
    SessionImportIntentV1Alpha1,
    SessionIngestionReceiptV1Alpha1,
    SessionIngestionStatusV1Alpha1,
    SourceAdapterIdentityV1Alpha1,
    StreamIngestionProposalV1Alpha1,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
DIGEST_A = f"sha256:{'a' * 64}"
DIGEST_B = f"sha256:{'b' * 64}"


def _scope() -> AgentMemoryScopeV1Alpha1:
    return AgentMemoryScopeV1Alpha1(
        product_id="product:am1-contracts",
        actor_id="principal:am1-user",
        session_id="native-session:fixture-001",
        source_id="source:fixture-session-export",
        visibility=MemoryVisibility.PRIVATE,
        retention_class=RetentionClass.STANDARD,
        authority_receipt_ref="authority_receipt:fixture-import",
    )


def _adapter() -> SourceAdapterIdentityV1Alpha1:
    return SourceAdapterIdentityV1Alpha1(
        adapter_ref="session_adapter:event-stream-v1",
        adapter_version="1.0.0",
        artifact_digest=DIGEST_B,
    )


def _idempotency(adapter: SourceAdapterIdentityV1Alpha1) -> IdempotencyIdentityV1Alpha1:
    return IdempotencyIdentityV1Alpha1(
        product_id="product:am1-contracts",
        actor_id="principal:am1-user",
        external_key="external_import:fixture-001",
        immutable_input_digest=DIGEST_A,
        adapter_id=adapter.adapter_id,
    )


def _coordinate(sequence: int = 1) -> LedgerCoordinateV1Alpha1:
    return LedgerCoordinateV1Alpha1(
        ledger_ref="ledger:am1",
        sequence=sequence,
        event_ref=f"import_status:event-{sequence}",
        committed_at=NOW + timedelta(seconds=sequence),
    )


def _source_event(
    *, ordinal: int = 1, source_version: str = "source_version:fixture-v1"
) -> EpisodicSourceEventV1Alpha1:
    scope = _scope()
    session = CanonicalSessionIdentityV1Alpha1(
        scope_id=scope.scope_id,
        source_id=scope.source_id,
        source_version_id=source_version,
        native_session_coordinate="fixture-001",
    )
    participant = CanonicalParticipantIdentityV1Alpha1(
        session_id=session.session_id,
        native_participant_coordinate="user-001",
        role=ParticipantRole.USER,
    )
    external = ExternalEventIdentityV1Alpha1(
        source_version_id=source_version,
        native_session_coordinate="fixture-001",
        native_event_coordinate=f"event-{ordinal:03d}",
    )
    identity = CanonicalEventIdentityV1Alpha1(
        session_id=session.session_id,
        source_version_id=source_version,
        native_event_coordinate=external.native_event_coordinate,
        content_digest=DIGEST_A,
        event_kind=EpisodicEventKind.TEXT,
    )
    span = ByteRangeSpanV1Alpha1(source_version_id=source_version, start_byte=0, end_byte=1)
    return EpisodicSourceEventV1Alpha1(
        scope=scope,
        session=session,
        participant=participant,
        external_event=external,
        identity=identity,
        provenance=SourceProvenanceV1Alpha1(
            source_id=scope.source_id,
            source_version_id=source_version,
            content_digest=DIGEST_A,
            span=span,
            acquisition_receipt_ref="receipt:source",
            capture_method_ref="adapter.fixture",
        ),
        knowledge_time=KnowledgeTimeV1Alpha1(
            kind=KnowledgeTimeKind.KNOWN,
            first_known_at=NOW,
            basis_refs=("receipt:source",),
        ),
        world_time=WorldTimeV1Alpha1(kind=WorldTimeKind.UNKNOWN, unknown_reason="not reported"),
        processing_ordinal=ordinal,
    )


def test_all_identity_families_are_stable_and_content_addressed() -> None:
    scope = _scope()
    adapter = _adapter()
    session = CanonicalSessionIdentityV1Alpha1(
        scope_id=scope.scope_id,
        source_id="source:fixture-session-export",
        source_version_id="source_version:fixture-session-export-v1",
        native_session_coordinate="fixture-001",
    )
    participant = CanonicalParticipantIdentityV1Alpha1(
        session_id=session.session_id,
        native_participant_coordinate="user-001",
        role=ParticipantRole.USER,
    )
    event = CanonicalEventIdentityV1Alpha1(
        session_id=session.session_id,
        source_version_id=session.source_version_id,
        native_event_coordinate="event-001",
        content_digest=DIGEST_A,
        event_kind=EpisodicEventKind.TEXT,
    )
    turn = CanonicalTurnIdentityV1Alpha1(
        session_id=session.session_id,
        participant_id=participant.participant_id,
        ordered_event_refs=(event.event_id,),
    )

    for contract in (adapter, _idempotency(adapter), session, participant, event, turn):
        rebuilt = type(contract).model_validate(contract.model_dump(mode="python"))
        assert rebuilt == contract
    assert participant.grants_authority is False


def test_frozen_fixture_exact_identity_coordinates(am1_fixture: dict[str, Any]) -> None:
    source = am1_fixture["authenticated_scope"]
    expected = am1_fixture["expected_canonical_identities"]
    scope = AgentMemoryScopeV1Alpha1(
        product_id=source["product_id"],
        actor_id=source["actor_id"],
        session_id=source["session_id"],
        source_id=source["source_id"],
        visibility=MemoryVisibility(source["visibility"]),
        retention_class=RetentionClass(source["retention_class"]),
        authority_receipt_ref=source["authority_receipt_ref"],
    )
    session = CanonicalSessionIdentityV1Alpha1(
        scope_id=scope.scope_id,
        source_id=source["source_id"],
        source_version_id=am1_fixture["immutable_source"]["source_version_id"],
        native_session_coordinate="fixture-001",
    )

    assert scope.scope_id == expected["scope_id"]
    assert session.session_id == expected["session_id"]
    for raw_event in am1_fixture["adapter_inputs"][0]["events"]:
        coordinate = raw_event["native_event_coordinate"]
        participant = CanonicalParticipantIdentityV1Alpha1(
            session_id=session.session_id,
            native_participant_coordinate=raw_event["native_participant_coordinate"],
            role=ParticipantRole(raw_event["role"]),
        )
        event = CanonicalEventIdentityV1Alpha1(
            session_id=session.session_id,
            source_version_id=session.source_version_id,
            native_event_coordinate=coordinate,
            content_digest=expected["content_digests"][coordinate],
            event_kind=EpisodicEventKind(raw_event["kind"]),
        )
        external_event = ExternalEventIdentityV1Alpha1(
            source_version_id=session.source_version_id,
            native_session_coordinate="fixture-001",
            native_event_coordinate=coordinate,
        )
        turn = CanonicalTurnIdentityV1Alpha1(
            session_id=session.session_id,
            participant_id=participant.participant_id,
            ordered_event_refs=(event.event_id,),
        )
        assert participant.participant_id == expected["participant_ids"][raw_event["native_participant_coordinate"]]
        assert event.event_id == expected["event_ids"][coordinate]
        assert external_event.external_event_id == expected["external_event_ids"][coordinate]
        assert turn.turn_id == expected["turn_ids"][coordinate]


def test_import_intent_rejects_scope_adapter_and_material_laundering() -> None:
    scope = _scope()
    adapter = _adapter()
    idempotency = _idempotency(adapter)
    base = dict(
        scope=scope,
        adapter=adapter,
        input_source_ref="source:fixture-session-export",
        input_source_version_id="source_version:fixture-session-export-v1",
        input_acquisition_receipt_ref="receipt:fixture-session-export",
        source_knowledge_time=KnowledgeTimeV1Alpha1(
            kind=KnowledgeTimeKind.KNOWN,
            first_known_at=NOW,
            basis_refs=("receipt:fixture-session-export",),
        ),
        immutable_input_digest=DIGEST_A,
        native_session_coordinate="fixture-001",
        idempotency=idempotency,
        mode=IngestionMode.BATCH,
        requested_at=NOW,
    )

    assert SessionImportIntentV1Alpha1(**base).scope.scope_id == scope.scope_id
    with pytest.raises(ValidationError, match="source must match authenticated source scope"):
        SessionImportIntentV1Alpha1(**{**base, "input_source_ref": "source:foreign"})
    with pytest.raises(ValidationError, match="exact immutable input"):
        SessionImportIntentV1Alpha1(**{**base, "immutable_input_digest": DIGEST_B})
    foreign_actor = IdempotencyIdentityV1Alpha1(
        product_id=idempotency.product_id,
        actor_id="principal:foreign",
        external_key=idempotency.external_key,
        immutable_input_digest=idempotency.immutable_input_digest,
        adapter_id=idempotency.adapter_id,
    )
    with pytest.raises(ValidationError, match="authenticated product and actor"):
        SessionImportIntentV1Alpha1(**{**base, "idempotency": foreign_actor})


def test_import_job_retry_identity_requires_exact_predecessor() -> None:
    initial = ImportJobV1Alpha1(
        intent_id="agent_memory_import_intent:fixture",
        idempotency_id="agent_memory_idempotency:fixture",
        attempt=1,
    )
    retry = ImportJobV1Alpha1(
        intent_id=initial.intent_id,
        idempotency_id=initial.idempotency_id,
        attempt=2,
        retry_of_job_ref=initial.job_id,
    )

    assert retry.job_id != initial.job_id
    with pytest.raises(ValidationError, match="only the initial import job"):
        ImportJobV1Alpha1(
            intent_id=initial.intent_id,
            idempotency_id=initial.idempotency_id,
            attempt=2,
        )


@pytest.mark.parametrize(
    ("state", "extra"),
    [
        (ImportState.READY, {"normalization_receipt_ref": "normalization_receipt:one"}),
        (ImportState.PARTIAL, {"failure_reason_ref": "failure_reason:partial"}),
        (ImportState.FAILED, {"failure_reason_ref": "failure_reason:failed"}),
        (ImportState.STALE, {"failure_reason_ref": "failure_reason:stale"}),
        (ImportState.RETRY_PENDING, {"retry_after": NOW + timedelta(minutes=1)}),
        (ImportState.REPAIR_REQUIRED, {"repair_proposal_ref": "repair_proposal:one"}),
    ],
)
def test_non_initial_import_states_bind_the_exact_prior_coordinate(
    state: ImportState,
    extra: dict[str, object],
) -> None:
    status = SessionIngestionStatusV1Alpha1(
        job_id="agent_memory_import_job:fixture",
        state=state,
        attempt=1,
        previous_state=ImportState.NORMALIZING,
        prior_coordinate=_coordinate(),
        recorded_at=NOW,
        **extra,
    )
    assert status.prior_coordinate == _coordinate()


def test_non_initial_import_state_without_prior_coordinate_fails() -> None:
    with pytest.raises(ValidationError, match="exact prior ledger coordinate"):
        SessionIngestionStatusV1Alpha1(
            job_id="agent_memory_import_job:fixture",
            state=ImportState.FAILED,
            attempt=1,
            previous_state=ImportState.NORMALIZING,
            failure_reason_ref="failure_reason:failed",
            recorded_at=NOW,
        )


def test_batch_requires_gap_free_order_and_stream_requires_exact_predecessor() -> None:
    first = _source_event(ordinal=1)
    second = _source_event(ordinal=2)
    batch = BatchIngestionProposalV1Alpha1(
        intent_id="agent_memory_import_intent:fixture",
        adapter_id="agent_memory_source_adapter:fixture",
        events=(first, second),
    )
    stream_one = StreamIngestionProposalV1Alpha1(
        intent_id=batch.intent_id,
        adapter_id=batch.adapter_id,
        event=first,
        stream_ordinal=1,
    )
    stream_two = StreamIngestionProposalV1Alpha1(
        intent_id=batch.intent_id,
        adapter_id=batch.adapter_id,
        event=second,
        stream_ordinal=2,
        prior_proposal_ref=stream_one.proposal_id,
        terminal=True,
    )

    assert stream_two.prior_proposal_ref == stream_one.proposal_id
    with pytest.raises(ValidationError, match="gap-free deterministic"):
        BatchIngestionProposalV1Alpha1(
            intent_id=batch.intent_id,
            adapter_id=batch.adapter_id,
            events=(second,),
        )
    with pytest.raises(ValidationError, match="first stream proposal"):
        StreamIngestionProposalV1Alpha1(
            intent_id=batch.intent_id,
            adapter_id=batch.adapter_id,
            event=second,
            stream_ordinal=2,
        )


def test_event_rejects_any_source_version_mismatch() -> None:
    event = _source_event()
    foreign_session = CanonicalSessionIdentityV1Alpha1(
        scope_id=event.scope.scope_id,
        source_id=event.scope.source_id,
        source_version_id="source_version:foreign-v2",
        native_session_coordinate="fixture-001",
    )
    foreign_participant = CanonicalParticipantIdentityV1Alpha1(
        session_id=foreign_session.session_id,
        native_participant_coordinate="user-001",
        role=ParticipantRole.USER,
    )
    foreign_identity = CanonicalEventIdentityV1Alpha1(
        session_id=foreign_session.session_id,
        source_version_id=event.identity.source_version_id,
        native_event_coordinate=event.identity.native_event_coordinate,
        content_digest=event.identity.content_digest,
        event_kind=event.identity.event_kind,
    )

    with pytest.raises(ValidationError, match="exact source version"):
        EpisodicSourceEventV1Alpha1(
            **{
                **event.model_dump(mode="python"),
                "session": foreign_session,
                "participant": foreign_participant,
                "identity": foreign_identity,
            }
        )


def test_import_status_evidence_fields_are_state_exclusive() -> None:
    coordinate = _coordinate()
    common = {
        "job_id": "agent_memory_import_job:fixture",
        "attempt": 1,
        "previous_state": ImportState.NORMALIZING,
        "prior_coordinate": coordinate,
        "recorded_at": NOW,
    }

    with pytest.raises(ValidationError, match="reserved for ready"):
        SessionIngestionStatusV1Alpha1(
            **common,
            state=ImportState.FAILED,
            normalization_receipt_ref="normalization_receipt:premature",
            failure_reason_ref="failure_reason:failed",
        )
    with pytest.raises(ValidationError, match="reserved for failed, partial, and stale"):
        SessionIngestionStatusV1Alpha1(
            **common,
            state=ImportState.READY,
            normalization_receipt_ref="normalization_receipt:ready",
            failure_reason_ref="failure_reason:contradictory",
        )


@pytest.mark.parametrize(
    ("disposition", "required", "contradictory"),
    [
        (
            IngestionDisposition.EXACT_REPLAY,
            {"prior_receipt_ref": "ingestion_receipt:prior"},
            {"session_id": "agent_memory_session:contradictory"},
        ),
        (
            IngestionDisposition.REJECTED,
            {"failure_reason_ref": "failure_reason:rejected"},
            {"prior_receipt_ref": "ingestion_receipt:contradictory"},
        ),
        (
            IngestionDisposition.INDETERMINATE,
            {"prior_receipt_ref": "receipt_lookup:required"},
            {"failure_reason_ref": "failure_reason:contradictory"},
        ),
    ],
)
def test_non_committed_receipts_forbid_contradictory_evidence(
    disposition: IngestionDisposition,
    required: dict[str, str],
    contradictory: dict[str, str],
) -> None:
    base = {
        "job_id": "agent_memory_import_job:fixture",
        "intent_id": "agent_memory_import_intent:fixture",
        "idempotency_id": "agent_memory_idempotency:fixture",
        "disposition": disposition,
        **required,
    }
    SessionIngestionReceiptV1Alpha1(**base)
    with pytest.raises(ValidationError):
        SessionIngestionReceiptV1Alpha1(**base, **contradictory)
