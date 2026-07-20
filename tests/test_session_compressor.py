# tests/test_session_compressor.py
"""Tests for the session compressor sentinel engine.

TDD: tests written before implementation.
"""

from unittest.mock import AsyncMock, patch

import pytest


def test_session_compressor_registered():
    """session_compressor should be in registry with correct cron."""
    import importlib

    import core.engine.sentinel.engines.session_compressor
    from core.engine.sentinel.registry import engine_registry

    # Force re-registration if another test cleared the registry
    if "session_compressor" not in engine_registry:
        importlib.reload(core.engine.sentinel.engines.session_compressor)

    assert "session_compressor" in engine_registry
    entry = engine_registry["session_compressor"]
    assert entry["cron"] == "0 2 * * *"
    assert callable(entry["fn"])


@pytest.mark.asyncio
async def test_session_compressor_no_sessions_returns_empty():
    """With no data in any table, engine returns zero counts."""
    from core.engine.sentinel.engines.session_compressor import run_session_compressor

    with patch("core.engine.sentinel.engines.session_compressor.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_session_compressor("product:default")

    assert result["sessions_processed"] == 0
    assert result["digests_written"] == 0
    assert result["insights_written"] == 0


@pytest.mark.asyncio
async def test_session_compressor_produces_digest():
    """With task + observation rows, engine writes digest and insights."""
    from core.engine.sentinel.engines.session_compressor import run_session_compressor

    task_row = {
        "id": "task:t1",
        "session_id": "ses_abc",
        "description": "Implement OAuth flow",
        "discipline": "security",
        "status": "completed",
        "created_at": "2026-03-30T10:00:00Z",
    }
    observation_row = {
        "id": "observation:o1",
        "session_id": "ses_abc",
        "content": "User prefers JWT tokens",
        "insight_type": "preference",
        "created_at": "2026-03-30T10:05:00Z",
    }

    digest_response = {
        "summary": "Implemented OAuth flow with JWT token preference noted.",
        "decisions": ["Use JWT tokens for auth"],
        "blockers": [],
        "outcomes": ["OAuth flow completed"],
        "quality_signals": ["Good security practice"],
    }

    synthesis_response = [
        {
            "content": "Teams prefer JWT over session cookies for stateless auth.",
            "insight_type": "preference",
            "discipline": "security",
            "confidence": 0.8,
        }
    ]

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(side_effect=[digest_response, synthesis_response])

    call_count = {"n": 0}

    async def _side_effect(query, params=None):
        call_count["n"] += 1
        n = call_count["n"]
        if n == 1:
            # task query
            return [[task_row]]
        if n == 2:
            # observation query
            return [[observation_row]]
        if n == 3:
            # orchestration_run query
            return [[]]
        if n == 4:
            # decision query
            return [[]]
        if "CREATE session_digest" in query:
            return [[{"id": "session_digest:d1"}]]
        if "CREATE insight" in query:
            return [[{"id": "insight:i1"}]]
        if "SELECT id, slug FROM specialty" in query:
            return [[]]
        return [[]]

    with (
        patch("core.engine.sentinel.engines.session_compressor.pool") as mock_pool,
        patch("core.engine.sentinel.engines.session_compressor.get_llm", return_value=mock_llm),
    ):
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_session_compressor("product:default")

    assert result["sessions_processed"] == 1
    assert result["digests_written"] == 1
    assert mock_llm.complete_json.call_count >= 2
