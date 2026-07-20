"""Boundary tests for the Session model — AC 1, 2, sentinel check."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.engine.session.models import Session, SessionEvent, SessionTurn

# ---------------------------------------------------------------------------
# AC 1 — Session dataclass shape
# ---------------------------------------------------------------------------


def test_session_dataclass_shape():
    """Session must expose the fields required by the spec."""
    now = datetime.now(timezone.utc)
    session = Session(
        id="test-id",
        product_id="product:ace",
        source="claude_code",
        started_at=now,
    )
    assert session.id == "test-id"
    assert session.product_id == "product:ace"
    assert session.source == "claude_code"
    assert session.started_at == now
    assert session.turns == []
    assert session.events == []


def test_session_event_shape():
    now = datetime.now(timezone.utc)
    event = SessionEvent(
        id="ev-1",
        session_id="sess-1",
        event_type="text",
        content="hello world",
        timestamp=now,
    )
    assert event.id == "ev-1"
    assert event.event_type == "text"
    assert event.content == "hello world"
    assert event.metadata is None


def test_session_turn_shape():
    now = datetime.now(timezone.utc)
    turn = SessionTurn(
        turn_index=0,
        human="What's the plan?",
        assistant="Here's the plan...",
        events=[],
        started_at=now,
        ended_at=now,
    )
    assert turn.turn_index == 0
    assert turn.human == "What's the plan?"


# ---------------------------------------------------------------------------
# AC 1 — to_dict / serialization
# ---------------------------------------------------------------------------


def test_session_to_dict_is_serializable():
    now = datetime.now(timezone.utc)
    session = Session(id="s1", product_id="p1", source="claude_code", started_at=now)
    d = session.to_dict()
    serialized = json.dumps(d)
    assert "s1" in serialized
    assert "claude_code" in serialized


# ---------------------------------------------------------------------------
# Sentinel check — AC sentinel: no "claude_code_event" in serialized Session
# ---------------------------------------------------------------------------


def test_no_raw_claude_event_leakage():
    """Adapter normalization must erase tool-specific field names."""
    sample_event = {
        "event_type": "text",
        "content": "We decided to use SurrealDB.",
        "session_id": "sess-abc",
    }
    session = Session.from_raw_claude_event(sample_event, product_id="product:ace")
    serialized = json.dumps(session.to_dict())
    assert "claude_code_event" not in serialized, (
        "Raw Claude Code event shape leaked through adapter — normalization is broken"
    )


def test_from_raw_claude_event_produces_valid_session():
    sample_event = {
        "event_type": "text",
        "content": "Decision: JWT tokens for auth.",
        "session_id": "sess-xyz",
    }
    session = Session.from_raw_claude_event(sample_event, product_id="product:ace")
    assert session.source == "claude_code"
    assert len(session.events) == 1
    assert session.events[0].content == "Decision: JWT tokens for auth."
    assert session.events[0].event_type == "text"


# ---------------------------------------------------------------------------
# AC 4 — orchestrator context loads from Session (source-agnostic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_context_loads_from_session():
    """load_full_context accepts product_id from any Session source — not Claude-specific."""
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, patch

    from core.engine.orchestrator.context import load_full_context
    from core.engine.session.models import Session

    cc_session = Session(
        id="sess-cc",
        product_id="product:test",
        source="claude_code",
        started_at=datetime.now(timezone.utc),
    )
    generic_session = Session(
        id="sess-gen",
        product_id="product:test",
        source="cursor",
        started_at=datetime.now(timezone.utc),
    )

    with patch("core.engine.orchestrator.context.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value = mock_conn

        ctx_cc = await load_full_context(cc_session.product_id)
        ctx_gen = await load_full_context(generic_session.product_id)

    assert isinstance(ctx_cc, dict)
    assert isinstance(ctx_gen, dict)
    assert set(ctx_cc.keys()) == set(ctx_gen.keys())
    assert "decisions" in ctx_cc
