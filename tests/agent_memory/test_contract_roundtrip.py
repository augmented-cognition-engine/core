from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import TypeAdapter

from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    ByteRangeSpanV1Alpha1,
    FrameRegionSpanV1Alpha1,
    KnowledgeTimeKind,
    KnowledgeTimeV1Alpha1,
    MemoryVisibility,
    PageRegionSpanV1Alpha1,
    ParticipantRole,
    ParticipantV1Alpha1,
    RetentionClass,
    SessionRecordV1Alpha1,
    SourceProvenanceV1Alpha1,
    SourceSpanV1Alpha1,
    StructuredPointerSpanV1Alpha1,
    TextCharacterRangeSpanV1Alpha1,
    TimecodeSpanV1Alpha1,
    TurnRecordV1Alpha1,
    UnavailableSourceSpanV1Alpha1,
    UnavailableSpanReason,
    WholeSourceSpanV1Alpha1,
    WorldTimeKind,
    WorldTimeV1Alpha1,
)
from ace.core.agent_memory_ports import AgentMemoryPortError, AgentMemoryPortFailureCode
from ace.intelligence.contracts.agent_memory import (
    AgentMemoryQueryV1Alpha1,
    CandidateReceiptV1Alpha1,
    CandidateRecordV1Alpha1,
    CandidateSignalContributionV1Alpha1,
    MemoryEpistemicState,
    MemorySemanticFamily,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 11, 22, 0, tzinfo=UTC)
PRODUCT = "product:agent-memory-roundtrip"
SOURCE_VERSION = "source_version:roundtrip-v1"


def _scope() -> AgentMemoryScopeV1Alpha1:
    return AgentMemoryScopeV1Alpha1(
        product_id=PRODUCT,
        actor_id="principal:roundtrip-user",
        session_id="session:roundtrip",
        source_id="source:roundtrip",
        visibility=MemoryVisibility.PRIVATE,
        retention_class=RetentionClass.STANDARD,
        authority_receipt_ref="authority_receipt:roundtrip",
    )


def _provenance() -> SourceProvenanceV1Alpha1:
    return SourceProvenanceV1Alpha1(
        source_id="source:roundtrip",
        source_version_id=SOURCE_VERSION,
        content_digest="sha256:" + "a" * 64,
        span=ByteRangeSpanV1Alpha1(
            source_version_id=SOURCE_VERSION,
            start_byte=0,
            end_byte=10,
        ),
        acquisition_receipt_ref="receipt:roundtrip",
        capture_method_ref="session.adapter",
    )


def test_every_source_span_variant_round_trips_through_the_tagged_union() -> None:
    spans = (
        ByteRangeSpanV1Alpha1(source_version_id=SOURCE_VERSION, start_byte=0, end_byte=10),
        TextCharacterRangeSpanV1Alpha1(
            source_version_id=SOURCE_VERSION,
            normalization_version="text_normalization:v1",
            start_character=1,
            end_character=9,
        ),
        PageRegionSpanV1Alpha1(
            source_version_id=SOURCE_VERSION,
            page=2,
            x=0.1,
            y=0.2,
            width=0.3,
            height=0.4,
        ),
        FrameRegionSpanV1Alpha1(
            source_version_id=SOURCE_VERSION,
            frame=12,
            x=0.2,
            y=0.1,
            width=0.4,
            height=0.5,
        ),
        TimecodeSpanV1Alpha1(
            source_version_id=SOURCE_VERSION,
            start_milliseconds=100,
            end_milliseconds=900,
        ),
        StructuredPointerSpanV1Alpha1(
            source_version_id=SOURCE_VERSION,
            pointer="/records/0/name",
        ),
        WholeSourceSpanV1Alpha1(source_version_id=SOURCE_VERSION),
        UnavailableSourceSpanV1Alpha1(
            source_version_id=SOURCE_VERSION,
            reason=UnavailableSpanReason.ADAPTER_UNSUPPORTED,
            detail="the compatibility adapter supplied no stable locator",
        ),
    )
    adapter = TypeAdapter(SourceSpanV1Alpha1)

    round_tripped = tuple(adapter.validate_json(adapter.dump_json(span)) for span in spans)

    assert round_tripped == spans
    assert {span.kind for span in round_tripped} == {
        "byte_range",
        "frame_region",
        "page_region",
        "structured_pointer",
        "text_character_range",
        "timecode",
        "unavailable",
        "whole_source",
    }


def test_session_and_turn_round_trip_preserves_scope_order_and_independent_time() -> None:
    scope = _scope()
    session = SessionRecordV1Alpha1(
        scope=scope,
        session_id="session:roundtrip",
        participants=(
            ParticipantV1Alpha1(participant_id="participant:user", role=ParticipantRole.USER),
            ParticipantV1Alpha1(participant_id="participant:assistant", role=ParticipantRole.ASSISTANT),
        ),
        source_refs=("source:roundtrip",),
        started_at=NOW - timedelta(minutes=5),
    )
    turn = TurnRecordV1Alpha1(
        scope=scope,
        turn_id="turn:roundtrip-1",
        session_id="session:roundtrip",
        participant_id="participant:user",
        ordinal=0,
        provenance=_provenance(),
        knowledge_time=KnowledgeTimeV1Alpha1(
            kind=KnowledgeTimeKind.KNOWN,
            first_known_at=NOW,
            basis_refs=("source:roundtrip",),
        ),
        world_time=WorldTimeV1Alpha1(
            kind=WorldTimeKind.UNKNOWN,
            unknown_reason="the turn states no external-world validity",
        ),
    )

    restored_session = SessionRecordV1Alpha1.model_validate_json(session.model_dump_json())
    restored_turn = TurnRecordV1Alpha1.model_validate_json(turn.model_dump_json())

    assert restored_session == session
    assert [participant.participant_id for participant in restored_session.participants] == [
        "participant:assistant",
        "participant:user",
    ]
    assert restored_turn == turn
    assert restored_turn.knowledge_time.first_known_at == NOW
    assert restored_turn.world_time.kind is WorldTimeKind.UNKNOWN


def test_query_and_candidate_receipt_round_trip_without_creating_use_evidence() -> None:
    query = AgentMemoryQueryV1Alpha1(
        scope=_scope(),
        query_digest="sha256:" + "b" * 64,
        eligible_families=(MemorySemanticFamily.LEARNED_FACT,),
        eligible_states=(MemoryEpistemicState.ACCEPTED,),
        receiver_ref="briefing_stage:roundtrip",
        policy_ref="memory_policy:roundtrip-v1",
    )
    receipt = CandidateReceiptV1Alpha1(
        query_id=query.query_id,
        scope_id=query.scope.scope_id,
        policy_ref=query.policy_ref,
        authorization_filter_receipt_ref="authority_receipt:roundtrip-filter",
        lifecycle_snapshot_ref="lifecycle_snapshot:roundtrip",
        candidates=(
            CandidateRecordV1Alpha1(
                assertion_ref="memory_assertion:roundtrip",
                family=MemorySemanticFamily.LEARNED_FACT,
                epistemic_state=MemoryEpistemicState.ACCEPTED,
                source_id="source:roundtrip",
                source_version_id=SOURCE_VERSION,
                selected=True,
                aggregate_score=0.7,
                signals=(
                    CandidateSignalContributionV1Alpha1(
                        signal_ref="signal:lexical",
                        available=True,
                        score=0.7,
                    ),
                ),
            ),
        ),
        generated_at=NOW,
    )

    assert AgentMemoryQueryV1Alpha1.model_validate_json(query.model_dump_json()) == query
    assert CandidateReceiptV1Alpha1.model_validate_json(receipt.model_dump_json()) == receipt
    assert {
        "injected",
        "materially_used",
        "decision_material",
        "beneficial",
    }.isdisjoint(type(receipt).model_fields)


@pytest.mark.parametrize(
    ("code", "retry_safe"),
    [
        (AgentMemoryPortFailureCode.INVALID_CONTRACT, False),
        (AgentMemoryPortFailureCode.UNAUTHORIZED, False),
        (AgentMemoryPortFailureCode.CONFLICT, False),
        (AgentMemoryPortFailureCode.UNAVAILABLE, True),
        (AgentMemoryPortFailureCode.INDETERMINATE, False),
        (AgentMemoryPortFailureCode.DEPENDENCY_INCOMPLETE, False),
    ],
)
def test_port_failure_preserves_typed_retry_and_receipt_semantics(
    code: AgentMemoryPortFailureCode,
    retry_safe: bool,
) -> None:
    error = AgentMemoryPortError(
        code,
        "bounded failure",
        retry_safe=retry_safe,
        receipt_ref="receipt:recovery" if code is AgentMemoryPortFailureCode.INDETERMINATE else None,
    )

    assert error.code is code
    assert error.retry_safe is retry_safe
    assert error.receipt_ref == ("receipt:recovery" if code is AgentMemoryPortFailureCode.INDETERMINATE else None)
    assert error.receipt_lookup_required is (code is AgentMemoryPortFailureCode.INDETERMINATE)


def test_indeterminate_port_failure_forbids_blind_retry_and_requires_receipt_lookup() -> None:
    with pytest.raises(ValueError, match="never safe for blind retry"):
        AgentMemoryPortError(
            AgentMemoryPortFailureCode.INDETERMINATE,
            "commit state is unknown",
            retry_safe=True,
            receipt_ref="receipt:recovery",
        )

    with pytest.raises(ValueError, match="receipt lookup reference"):
        AgentMemoryPortError(
            AgentMemoryPortFailureCode.INDETERMINATE,
            "commit state is unknown",
            retry_safe=False,
        )
