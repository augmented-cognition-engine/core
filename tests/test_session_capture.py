# tests/test_session_capture.py
"""Tests for session capture — observation extraction from archived chat sessions."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_extracts_observations_from_session():
    """Session capture writes observations to DB."""
    from core.engine.chat.session_capture import extract_session_observations

    with (
        patch("core.engine.chat.session_capture.pool") as mock_pool,
        patch("core.engine.chat.session_capture.llm") as mock_llm,
    ):
        mock_conn = AsyncMock()
        # First call: load messages. Second+: write observations
        mock_conn.query = AsyncMock(
            side_effect=[
                [
                    [
                        {"role": "user", "content": "Use rem not px for spacing"},
                        {"role": "assistant", "content": "Got it, I'll use rem."},
                        {"role": "user", "content": "Also prefer TypeScript over JavaScript"},
                    ]
                ],
                [[{"id": "obs:1"}]],
                [[{"id": "obs:2"}]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(
            return_value=[
                {
                    "observation_type": "correction",
                    "content": "Use rem not px for spacing",
                    "domain_path": "design.tokens",
                    "confidence": 0.9,
                },
                {
                    "observation_type": "preference",
                    "content": "Prefer TypeScript over JavaScript",
                    "domain_path": "architecture",
                    "confidence": 0.85,
                },
            ]
        )

        result = await extract_session_observations("session:1", "product:test")

    assert len(result) == 2
    assert result[0]["observation_type"] == "correction"
    assert result[1]["observation_type"] == "preference"


@pytest.mark.asyncio
async def test_skips_sessions_with_few_messages():
    """Session capture skips sessions with fewer than 2 messages."""
    from core.engine.chat.session_capture import extract_session_observations

    with patch("core.engine.chat.session_capture.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"role": "user", "content": "Hi"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await extract_session_observations("session:2", "product:test")

    assert result == []


@pytest.mark.asyncio
async def test_caps_at_max_observations():
    """Session capture writes at most MAX_OBSERVATIONS."""
    from core.engine.chat.session_capture import MAX_OBSERVATIONS, extract_session_observations

    with (
        patch("core.engine.chat.session_capture.pool") as mock_pool,
        patch("core.engine.chat.session_capture.llm") as mock_llm,
    ):
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {"role": "user", "content": "msg1"},
                    {"role": "assistant", "content": "resp1"},
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        # LLM returns more than MAX_OBSERVATIONS
        mock_llm.complete_json = AsyncMock(
            return_value=[{"observation_type": "learning", "content": f"obs {i}", "confidence": 0.5} for i in range(10)]
        )

        result = await extract_session_observations("session:3", "product:test")

    assert len(result) <= MAX_OBSERVATIONS


@pytest.mark.asyncio
async def test_handles_llm_failure_gracefully():
    """Session capture returns empty list on LLM failure."""
    from core.engine.chat.session_capture import extract_session_observations

    with (
        patch("core.engine.chat.session_capture.pool") as mock_pool,
        patch("core.engine.chat.session_capture.llm") as mock_llm,
    ):
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {"role": "user", "content": "msg"},
                    {"role": "assistant", "content": "resp"},
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(side_effect=Exception("LLM unavailable"))

        result = await extract_session_observations("session:4", "product:test")

    assert result == []
