"""Tests for /remember and /catchup chat slash commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db():
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[])
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_pool, mock_conn


def test_parse_window():
    from datetime import timedelta

    from core.engine.chat.handler import _parse_window

    assert _parse_window("3d") == timedelta(days=3)
    assert _parse_window("1w") == timedelta(weeks=1)
    assert _parse_window("12h") == timedelta(hours=12)
    assert _parse_window("") == timedelta(days=7)
    assert _parse_window("garbage") == timedelta(days=7)


@pytest.mark.asyncio
async def test_remember_creates_observation(mock_db):
    mock_pool, mock_conn = mock_db

    with patch("core.engine.chat.handler.pool", mock_pool):
        from core.engine.chat.handler import _handle_remember

        result = await _handle_remember("Always use snake_case", "sess:1", "product:default", "workspace:default")

    assert result["output"] == "Noted. I'll remember that."
    assert result["slash_command"] == "remember"
    # Verify DB was called (CREATE observation + 2 chat messages)
    assert mock_conn.query.call_count == 3


@pytest.mark.asyncio
async def test_remember_empty_shows_usage(mock_db):
    mock_pool, mock_conn = mock_db

    with patch("core.engine.chat.handler.pool", mock_pool):
        from core.engine.chat.handler import _handle_remember

        result = await _handle_remember("", "sess:1", "product:default", "workspace:default")

    assert "Usage" in result["output"]
    # No DB calls when text is empty
    assert mock_conn.query.call_count == 0


@pytest.mark.asyncio
async def test_catchup_gathers_context(mock_db):
    mock_pool, mock_conn = mock_db

    mock_execute = AsyncMock(return_value={"output": "Here's your catch-up...", "id": "task:1"})

    with (
        patch("core.engine.chat.handler.pool", mock_pool),
        patch("core.engine.orchestrator.executor.execute_task", mock_execute),
    ):
        from core.engine.chat.handler import _handle_catchup

        result = await _handle_catchup("3d", "sess:1", "product:default", "workspace:default", "user:default")

    assert result["slash_command"] == "catchup"
    # execute_task was called with the composed prompt
    assert mock_execute.called
    call_args = mock_execute.call_args
    assert "catch-up summary" in call_args.kwargs.get("description", call_args[1].get("description", ""))


@pytest.mark.asyncio
async def test_handle_message_routes_remember(mock_db):
    mock_pool, mock_conn = mock_db

    with patch("core.engine.chat.handler.pool", mock_pool):
        from core.engine.chat.handler import handle_message

        result = await handle_message(
            "sess:1", "/remember Use TypeScript", "product:default", "workspace:default", "user:default"
        )

    assert result["slash_command"] == "remember"
    assert "Noted" in result["output"]


@pytest.mark.asyncio
async def test_handle_message_routes_catchup(mock_db):
    mock_pool, mock_conn = mock_db

    mock_execute = AsyncMock(return_value={"output": "Catch-up summary...", "id": "task:2"})

    with (
        patch("core.engine.chat.handler.pool", mock_pool),
        patch("core.engine.orchestrator.executor.execute_task", mock_execute),
    ):
        from core.engine.chat.handler import handle_message

        result = await handle_message("sess:1", "/catchup 3d", "product:default", "workspace:default", "user:default")

    assert result["slash_command"] == "catchup"
    assert mock_execute.called


@pytest.mark.asyncio
async def test_handle_message_bare_catchup(mock_db):
    """Test /catchup with no arguments uses default 7d window."""
    mock_pool, mock_conn = mock_db

    mock_execute = AsyncMock(return_value={"output": "Catch-up summary...", "id": "task:3"})

    with (
        patch("core.engine.chat.handler.pool", mock_pool),
        patch("core.engine.orchestrator.executor.execute_task", mock_execute),
    ):
        from core.engine.chat.handler import handle_message

        result = await handle_message("sess:1", "/catchup", "product:default", "workspace:default", "user:default")

    assert result["slash_command"] == "catchup"


@pytest.mark.asyncio
async def test_handle_message_non_slash_passes_through(mock_db):
    """Non-slash messages go through the normal orchestrator path."""
    mock_pool, mock_conn = mock_db

    mock_execute = AsyncMock(
        return_value={
            "id": "task:4",
            "output": "Normal response",
            "domain_path": "",
            "archetype": "",
            "mode": "",
        }
    )

    with (
        patch("core.engine.chat.handler.pool", mock_pool),
        patch("core.engine.orchestrator.executor.execute_task", mock_execute),
    ):
        from core.engine.chat.handler import handle_message

        result = await handle_message(
            "sess:1", "Please refactor the auth module", "product:default", "workspace:default", "user:default"
        )

    assert "slash_command" not in result
    assert result["output"] == "Normal response"
    assert mock_execute.called
