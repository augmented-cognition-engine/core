from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application.agent_memory_ingestion import (
    AgentMemoryAuthorizationDenied,
    AuthorizedAgentMemoryUse,
)
from ace.core.agent_memory import AgentMemoryScopeV1Alpha1, LifecycleState, MemoryVisibility, RetentionClass
from ace.core.agent_memory_ingestion import (
    EventListReceiptV1Alpha1,
    SessionNormalizationReceiptV1Alpha1,
    TranscriptViewReceiptV1Alpha1,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
DIGEST = f"sha256:{'a' * 64}"


def _scope(*, product_id: str = "product:am1-private", actor_id: str = "principal:owner") -> AgentMemoryScopeV1Alpha1:
    return AgentMemoryScopeV1Alpha1(
        product_id=product_id,
        actor_id=actor_id,
        session_id="session:private",
        source_id="source:private",
        visibility=MemoryVisibility.PRIVATE,
        retention_class=RetentionClass.RESTRICTED,
        authority_receipt_ref="authority_receipt:current",
    )


def test_normalization_and_query_receipts_are_content_free() -> None:
    normalization = SessionNormalizationReceiptV1Alpha1(
        intent_id="agent_memory_import_intent:fixture",
        adapter_id="agent_memory_source_adapter:fixture",
        immutable_input_digest=DIGEST,
        session_id="agent_memory_session:fixture",
        participant_refs=("agent_memory_participant:user",),
        turn_refs=("agent_memory_turn:user",),
        ordered_event_refs=("agent_memory_event:one",),
        source_span_refs=("agent_memory_span:one",),
    )
    listing = EventListReceiptV1Alpha1(
        query_id="agent_memory_event_list_query:fixture",
        authorization_receipt_ref="authority_receipt:read",
        lifecycle_snapshot_ref="lifecycle_snapshot:fixture",
        ordered_event_refs=("agent_memory_event:one",),
    )
    transcript = TranscriptViewReceiptV1Alpha1(
        scope_id=_scope().scope_id,
        query_id="agent_memory_span_read_query:fixture",
        authorization_receipt_ref="authority_receipt:read-span",
        lifecycle_snapshot_ref="lifecycle_snapshot:fixture",
        returned_event_refs=("agent_memory_event:one",),
        returned_span_refs=("agent_memory_span:one",),
        expires_at=NOW + timedelta(minutes=1),
    )

    forbidden = {"body", "content", "prompt", "transcript", "tool_result", "hidden_reasoning"}
    for receipt in (normalization, listing, transcript):
        payload = receipt.model_dump(mode="json")
        assert forbidden.isdisjoint(payload)
        assert not any(secret in str(payload) for secret in ("private transcript body", "api-key"))


def test_receipts_reject_attempted_body_injection() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EventListReceiptV1Alpha1.model_validate(
            {
                "query_id": "agent_memory_event_list_query:fixture",
                "authorization_receipt_ref": "authority_receipt:read",
                "lifecycle_snapshot_ref": "lifecycle_snapshot:fixture",
                "ordered_event_refs": ["agent_memory_event:one"],
                "body": "private transcript body",
            }
        )


def test_public_authorization_projection_is_bounded_and_non_reusable() -> None:
    result = AuthorizedAgentMemoryUse(
        product_id="product:am1-private",
        actor_id="principal:owner",
        operation="read_span",
        subject_ref="agent_memory_event:one",
        authority_receipt_ref="authority_receipt:present-tense",
        evaluated_at=NOW,
        lifecycle_snapshot_ref="lifecycle_snapshot:fixture-current",
        lifecycle_state=LifecycleState.ACTIVE,
        expires_at=NOW + timedelta(minutes=1),
    )
    assert result.reusable_authority is False
    assert not hasattr(result, "body")


@pytest.mark.parametrize(
    "reason",
    [
        "foreign product",
        "foreign principal",
        "expired authority",
        "revoked authority",
        "rotated authority",
        "stale authority",
        "nonexistent resource",
    ],
)
def test_denial_is_identical_and_does_not_disclose_existence(reason: str) -> None:
    del reason
    error = AgentMemoryAuthorizationDenied()
    assert str(error) == "agent memory operation is unavailable"
    assert "exist" not in str(error)
    assert not hasattr(error, "record_ref")
