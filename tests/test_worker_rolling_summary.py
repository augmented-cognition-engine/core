# tests/test_worker_rolling_summary.py
"""Tests for rolling summary compression in the ACE Session Intelligence Worker."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_compress_buffer_writes_rolling_summary():
    """After 8+ messages, buffer compression must write rolling_summary to DB."""
    from core.engine.worker.app import _compress_session_buffer

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = {
        "rolling_summary": "",
        "message_buffer": [f"msg {i}" for i in range(10)],
        "message_count": 10,
    }

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value="Exploring cognitive composition architecture.")

    with (
        patch("core.engine.worker.session.session_manager") as mock_sm,
        patch("core.engine.core.llm.get_llm", return_value=mock_llm),
        patch("core.engine.core.db.pool") as mock_pool,
    ):
        mock_sm.get_or_create = AsyncMock(return_value=mock_session)
        mock_pool.connection.return_value = mock_ctx
        await _compress_session_buffer("test-session", "product:platform")

    # Sentinel: summary must have been written to DB — not a silent no-op
    mock_db.query.assert_called_once()
    call_sql = mock_db.query.call_args[0][0]
    assert "rolling_summary" in call_sql
    assert "message_buffer" in call_sql
    assert "array::slice" in call_sql


@pytest.mark.asyncio
async def test_compress_buffer_skips_short_buffer():
    """Buffer with fewer than COMPRESS_EVERY messages must not trigger compression."""
    from core.engine.worker.app import _compress_session_buffer

    mock_session = {
        "rolling_summary": "",
        "message_buffer": ["msg 1", "msg 2"],
        "message_count": 2,
    }

    with patch("core.engine.worker.session.session_manager") as mock_sm:
        mock_sm.get_or_create = AsyncMock(return_value=mock_session)
        # Should return early — no LLM call, no DB write
        await _compress_session_buffer("test-session", "product:platform")
    # No exception = short-circuit worked


@pytest.mark.asyncio
async def test_compress_buffer_never_raises():
    """LLM or DB failure must be swallowed — never crash the background task."""
    from core.engine.worker.app import _compress_session_buffer

    mock_session = {
        "rolling_summary": "",
        "message_buffer": [f"msg {i}" for i in range(10)],
        "message_count": 10,
    }

    with (
        patch("core.engine.worker.session.session_manager") as mock_sm,
        patch("core.engine.core.llm.get_llm", side_effect=Exception("LLM down")),
    ):
        mock_sm.get_or_create = AsyncMock(return_value=mock_session)
        # Must not raise
        await _compress_session_buffer("test-session", "product:platform")


@pytest.mark.asyncio
async def test_background_classify_triggers_compression_on_eighth_message():
    """_background_classify must call _compress_session_buffer at message_count=8."""
    from core.engine.worker.app import _background_classify

    state = {
        "rolling_summary": "",
        "message_buffer": [f"msg {i}" for i in range(8)],
        "message_count": 8,  # divisible by _COMPRESS_EVERY (8)
        "classification": {},
    }

    with (
        patch("core.engine.worker.session.session_manager") as mock_sm,
        patch("core.engine.worker.app._compress_session_buffer") as mock_compress,
        patch("core.engine.worker.app._fetch_recent_decisions", return_value=[]),
        patch(
            "core.engine.worker.classifier.classify_with_context",
            return_value={"discipline": "architecture", "mode": "reactive", "depth": 1},
        ),
        patch("core.engine.worker.intelligence.build_compact_index", return_value=""),
    ):
        mock_sm.get_or_create = AsyncMock(return_value=state)
        mock_sm.update_classification = AsyncMock()
        mock_sm.update_compact_index = AsyncMock()
        mock_compress.return_value = None

        await _background_classify("sess-abc", "what is the architecture?", "product:platform")

    # Sentinel: compression must have been triggered
    mock_compress.assert_called_once_with("sess-abc", "product:platform")


@pytest.mark.asyncio
async def test_background_classify_skips_compression_on_other_messages():
    """_background_classify must NOT compress on non-multiple-of-8 message counts."""
    from core.engine.worker.app import _background_classify

    state = {
        "rolling_summary": "prior summary",
        "message_buffer": ["msg 1", "msg 2", "msg 3"],
        "message_count": 3,  # not divisible by 8
        "classification": {},
    }

    with (
        patch("core.engine.worker.session.session_manager") as mock_sm,
        patch("core.engine.worker.app._compress_session_buffer") as mock_compress,
        patch("core.engine.worker.app._fetch_recent_decisions", return_value=[]),
        patch(
            "core.engine.worker.classifier.classify_with_context",
            return_value={"discipline": "testing", "mode": "reactive", "depth": 1},
        ),
        patch("core.engine.worker.intelligence.build_compact_index", return_value=""),
    ):
        mock_sm.get_or_create = AsyncMock(return_value=state)
        mock_sm.update_classification = AsyncMock()
        mock_sm.update_compact_index = AsyncMock()

        await _background_classify("sess-abc", "write a test", "product:platform")

    mock_compress.assert_not_called()
