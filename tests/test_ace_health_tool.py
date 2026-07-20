# tests/test_ace_health_tool.py
"""Tests for ace_health MCP tool."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_ace_health_returns_working_status():
    """ace_health must return a dict with 'status' and 'summary' fields."""
    from core.engine.mcp.tools import ace_health

    worker_status = {
        "pipeline_status": "active",
        "hook_post_count": 42,
        "capture_count": 15,
        "idle_seconds": 5.0,
        "last_synthesis_at": 1000.0,
        "uptime_seconds": 3600.0,
        "last_error": None,
        "worker_version": "1.0.0",
    }

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.mcp.tools.pool") as mock_pool,
        patch("core.engine.mcp.tools.parse_rows", return_value=[{"n": 10}]),
        patch("core.engine.mcp.tools._fetch_worker_health_status", return_value=worker_status),
    ):
        mock_pool.connection.return_value = mock_ctx
        result = await ace_health()

    assert result["status"] == "healthy"
    assert "summary" in result
    assert result["hook_post_count"] == 42
    assert result["capture_count"] == 15


@pytest.mark.asyncio
async def test_ace_health_reports_stale():
    """ace_health status='degraded' when pipeline is stale."""
    from core.engine.mcp.tools import ace_health

    worker_status = {
        "pipeline_status": "stale",
        "hook_post_count": 3,
        "capture_count": 3,
        "idle_seconds": 2200.0,
        "last_synthesis_at": None,
        "uptime_seconds": 7200.0,
        "last_error": None,
        "worker_version": "1.0.0",
    }

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.mcp.tools.pool") as mock_pool,
        patch("core.engine.mcp.tools.parse_rows", return_value=[]),
        patch("core.engine.mcp.tools._fetch_worker_health_status", return_value=worker_status),
    ):
        mock_pool.connection.return_value = mock_ctx
        result = await ace_health()

    assert result["status"] == "degraded"
    assert "stale" in result["summary"].lower() or "idle" in result["summary"].lower()


@pytest.mark.asyncio
async def test_ace_health_worker_unreachable_restart_fails():
    """ace_health status='down' when worker unreachable and restart fails."""
    from core.engine.mcp.tools import ace_health

    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.mcp.tools.pool") as mock_pool,
        patch("core.engine.mcp.tools.parse_rows", return_value=[]),
        patch("core.engine.mcp.tools._fetch_worker_health_status", side_effect=Exception("connection refused")),
        patch("core.engine.mcp.tools._try_restart_worker", return_value=False),
    ):
        mock_pool.connection.return_value = mock_ctx
        result = await ace_health()

    assert result["status"] == "down"
    assert "worker" in result["summary"].lower()


@pytest.mark.asyncio
async def test_ace_health_worker_unreachable_restart_succeeds():
    """ace_health status='recovered' when worker was down but restart succeeded."""
    from core.engine.mcp.tools import ace_health

    recovered_status = {
        "pipeline_status": "never_used",
        "hook_post_count": 0,
        "capture_count": 0,
        "idle_seconds": None,
        "last_synthesis_at": None,
        "uptime_seconds": 2.0,
        "last_error": None,
        "worker_version": "1.0.0",
    }

    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    # First call raises (worker down), second call succeeds (after restart)
    fetch_calls = [Exception("connection refused"), recovered_status]
    fetch_mock = AsyncMock(side_effect=fetch_calls)

    with (
        patch("core.engine.mcp.tools.pool") as mock_pool,
        patch("core.engine.mcp.tools.parse_rows", return_value=[]),
        patch("core.engine.mcp.tools._fetch_worker_health_status", fetch_mock),
        patch("core.engine.mcp.tools._try_restart_worker", return_value=True),
    ):
        mock_pool.connection.return_value = mock_ctx
        result = await ace_health()

    assert result["status"] == "recovered"
    assert "restart" in result["summary"].lower()


@pytest.mark.asyncio
async def test_ace_health_restart_timeout_returns_down():
    """ace_health must return status='down' (not raise) when restart times out."""
    import asyncio as _asyncio

    from core.engine.mcp.tools import ace_health

    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.mcp.tools.pool") as mock_pool,
        patch("core.engine.mcp.tools.parse_rows", return_value=[]),
        patch("core.engine.mcp.tools._fetch_worker_health_status", side_effect=Exception("refused")),
        patch("core.engine.mcp.tools._try_restart_worker", new_callable=AsyncMock, return_value=False),
        patch("core.engine.mcp.tools.asyncio.wait_for", side_effect=_asyncio.TimeoutError),
    ):
        mock_pool.connection.return_value = mock_ctx
        result = await ace_health()

    assert result["status"] == "down"
    assert "worker" in result["summary"].lower()
