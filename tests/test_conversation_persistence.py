# tests/test_conversation_persistence.py
"""A.7 — Conversation persistence: save/load messages and turns."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_save_user_message_returns_id(monkeypatch):
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[[{"id": "conversation_message:msg1"}]])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn
    monkeypatch.setattr("core.engine.canvas.conversation.pool", mock_pool)

    from core.engine.canvas.conversation import save_message

    msg_id = await save_message(
        session_id="canvas_session:s1",
        role="user",
        content="should we use JWT?",
        run_id="run:r1",
    )
    assert msg_id == "conversation_message:msg1"


@pytest.mark.asyncio
async def test_save_message_returns_none_on_db_error(monkeypatch):
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = Exception("DB down")
    monkeypatch.setattr("core.engine.canvas.conversation.pool", mock_pool)

    from core.engine.canvas.conversation import save_message

    result = await save_message(session_id="canvas_session:s1", role="user", content="test")
    assert result is None


@pytest.mark.asyncio
async def test_load_recent_messages_returns_list(monkeypatch):
    rows = [
        {"id": "conversation_message:1", "role": "user", "content": "hello", "created_at": "2026-05-11T00:00:00Z"},
        {
            "id": "conversation_message:2",
            "role": "ace",
            "content": "We should consider...",
            "created_at": "2026-05-11T00:00:01Z",
        },
    ]
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[rows])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn
    monkeypatch.setattr("core.engine.canvas.conversation.pool", mock_pool)

    from core.engine.canvas.conversation import load_recent_messages

    messages = await load_recent_messages(session_id="canvas_session:s1", limit=10)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"


@pytest.mark.asyncio
async def test_load_recent_messages_returns_empty_on_error(monkeypatch):
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = Exception("DB down")
    monkeypatch.setattr("core.engine.canvas.conversation.pool", mock_pool)

    from core.engine.canvas.conversation import load_recent_messages

    result = await load_recent_messages(session_id="canvas_session:s1")
    assert result == []


@pytest.mark.asyncio
async def test_save_turn_links_user_and_synthesis(monkeypatch):
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[[{"id": "conversation_turn:t1"}]])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn
    monkeypatch.setattr("core.engine.canvas.conversation.pool", mock_pool)

    from core.engine.canvas.conversation import save_turn

    turn_id = await save_turn(
        session_id="canvas_session:s1",
        run_id="run:r1",
        user_message_id="conversation_message:m1",
        synthesis_message_id="conversation_message:m2",
        decision_ids=["decision:d1"],
        prediction_ids=["decision_prediction:p1"],
    )
    assert turn_id == "conversation_turn:t1"


@pytest.mark.asyncio
async def test_save_turn_returns_none_on_error(monkeypatch):
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = Exception("DB down")
    monkeypatch.setattr("core.engine.canvas.conversation.pool", mock_pool)

    from core.engine.canvas.conversation import save_turn

    result = await save_turn(
        session_id="canvas_session:s1",
        run_id="run:r1",
        user_message_id="conversation_message:m1",
    )
    assert result is None
