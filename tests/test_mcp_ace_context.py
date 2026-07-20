# tests/test_mcp_ace_context.py
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_ace_context_returns_all_sections():
    """ace_context returns all expected sections."""
    from core.engine.mcp.tools import ace_context

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = mock_cm

        result = await ace_context("product:default")

    assert "capabilities" in result
    assert "quality_summary" in result
    assert "recent_decisions" in result
    assert "active_work" in result
    assert "open_gaps" in result
    assert "recent_activity" in result
    assert "efficiency" in result


@pytest.mark.asyncio
async def test_ace_context_empty_org():
    """ace_context returns safe defaults for empty org."""
    from core.engine.mcp.tools import ace_context

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = mock_cm

        result = await ace_context("org:empty")

    assert result["capabilities"] == []
    assert result["recent_decisions"] == []
    assert result["open_gaps"] == []


@pytest.mark.asyncio
async def test_ace_context_connection_failure():
    """ace_context returns default dict if DB connection fails entirely."""
    from core.engine.mcp.tools import ace_context

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_pool.connection.side_effect = Exception("Connection failed")
        result = await ace_context("product:default")

    assert isinstance(result, dict)
    assert result["capabilities"] == []
