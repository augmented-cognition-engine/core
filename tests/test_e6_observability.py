# tests/test_e6_observability.py
"""Tests for E6 observability improvements."""

import pytest


@pytest.mark.asyncio
async def test_chat_streaming_error_records_to_error_buffer():
    """Top-level exception in stream_chat_response is recorded to error_buffer."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.core.error_buffer import error_buffer

    error_buffer.clear()

    mock_pool = MagicMock()
    mock_db = AsyncMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_db.query = AsyncMock(return_value=[])

    with patch("core.engine.chat.streaming.pool", mock_pool):
        # Patch at the source module, not the streaming import
        with patch(
            "core.engine.chat.handler.get_session_history",
            AsyncMock(side_effect=RuntimeError("db failure")),
        ):
            from core.engine.chat.streaming import stream_chat_response

            events = []
            async for evt in stream_chat_response(
                session_id="chat_session:test",
                message="hello",
                product_id="product:test",
                workspace_id="ws:test",
                user_id="user:test",
            ):
                events.append(evt)

    # Must have emitted an error SSE event
    assert any(e.get("event") == "error" for e in events), f"No error event: {events}"

    # Must have recorded to error_buffer
    recent = error_buffer.recent(5)
    assert any(e["source"] == "chat.streaming" and "db failure" in e["message"] for e in recent), (
        f"Expected error in buffer, got: {recent}"
    )


@pytest.mark.asyncio
async def test_chat_streaming_error_includes_session_context():
    """Error buffer entry for chat streaming includes session_id in context."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.core.error_buffer import error_buffer

    error_buffer.clear()

    mock_pool = MagicMock()
    mock_db = AsyncMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_db.query = AsyncMock(return_value=[])

    test_session_id = "chat_session:abc123"

    with patch("core.engine.chat.streaming.pool", mock_pool):
        with patch(
            "core.engine.chat.handler.get_session_history",
            AsyncMock(side_effect=ValueError("test error")),
        ):
            from core.engine.chat.streaming import stream_chat_response

            async for _ in stream_chat_response(
                session_id=test_session_id,
                message="hi",
                product_id="product:test",
                workspace_id="ws:test",
                user_id="user:42",
            ):
                pass

    recent = error_buffer.recent(5)
    assert any(e.get("context", {}).get("session_id") == test_session_id for e in recent), (
        f"Expected session_id in error context, got: {recent}"
    )


@pytest.mark.asyncio
async def test_worker_rejects_oversized_content():
    """POST /observe with content > 10,000 chars returns error."""
    from httpx import ASGITransport, AsyncClient

    from core.engine.worker.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/observe", json={"content": "x" * 10_001})
    assert resp.status_code == 200
    body = resp.json()
    assert "content" in body.get("error", "").lower()


@pytest.mark.asyncio
async def test_worker_rejects_invalid_confidence():
    """POST /observe with confidence outside [0.0, 1.0] returns error."""
    from httpx import ASGITransport, AsyncClient

    from core.engine.worker.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/observe", json={"content": "valid content", "confidence": 1.5})
    assert resp.status_code == 200
    body = resp.json()
    assert "confidence" in body.get("error", "").lower()


@pytest.mark.asyncio
async def test_worker_accepts_valid_observation():
    """POST /observe with valid payload queues the observation."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from httpx import ASGITransport, AsyncClient

    from core.engine.worker.app import app

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.core.db.pool") as mock_pool,
        patch("core.engine.core.db.parse_rows", return_value=[{"id": "observation:test"}]),
    ):
        mock_pool.connection.return_value = mock_ctx
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/observe", json={"content": "something happened", "confidence": 0.8})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"


@pytest.mark.asyncio
async def test_timed_tool_records_duration():
    """_timed_tool() context manager calls observe() on the duration histogram."""
    from unittest.mock import MagicMock, patch

    mock_histogram = MagicMock()
    mock_labels = MagicMock()
    mock_histogram.labels.return_value = mock_labels

    with patch("core.engine.mcp.tools._mcp_tool_duration", mock_histogram):
        from core.engine.mcp.tools import _timed_tool

        async with _timed_tool("ace_load"):
            pass

    mock_histogram.labels.assert_called_once_with(tool="ace_load")
    assert mock_labels.observe.call_count == 1
    duration_recorded = mock_labels.observe.call_args[0][0]
    assert duration_recorded >= 0.0


@pytest.mark.asyncio
async def test_timed_tool_records_error_to_buffer():
    """_timed_tool() records exceptions to error_buffer and re-raises."""
    from core.engine.core.error_buffer import error_buffer
    from core.engine.mcp.tools import _timed_tool

    error_buffer.clear()

    with pytest.raises(RuntimeError, match="tool internal failure"):
        async with _timed_tool("ace_capture"):
            raise RuntimeError("tool internal failure")

    recent = error_buffer.recent(5)
    assert any(e["source"] == "mcp_tool.ace_capture" and "tool internal failure" in e["message"] for e in recent), (
        f"Expected tool error in buffer, got: {recent}"
    )


@pytest.mark.asyncio
async def test_timed_tool_reraises_exception():
    """_timed_tool() does not swallow exceptions — caller must handle them."""
    from core.engine.mcp.tools import _timed_tool

    with pytest.raises(ValueError, match="propagated"):
        async with _timed_tool("ace_task"):
            raise ValueError("propagated")
