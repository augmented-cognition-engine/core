"""Tests for Phase C MCP tools — ace_signals and ace_scenario."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_ace_signals_returns_signals():
    """ace_signals returns recent internal signals for a product."""
    signal_rows = [
        {
            "id": "signal:s1",
            "kind": "capability_decline",
            "description": "capability:auth score declined 0.20",
            "confidence": 0.85,
            "subject": "capability:auth",
            "created_at": "2026-05-11T00:00:00+00:00",
        }
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[signal_rows])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.mcp.tools.pool", mock_pool):
        from core.engine.mcp.tools import ace_signals

        result = await ace_signals(product_id="product:test")

    assert "signals" in result
    assert len(result["signals"]) == 1
    assert result["signals"][0]["kind"] == "capability_decline"


@pytest.mark.asyncio
async def test_ace_scenario_returns_branches():
    """ace_scenario returns scenario branches for a given signal."""
    scenario_rows = [
        {
            "id": "scenario:sc1",
            "root_signal_id": "signal:s1",
            "kind": "capability_decline",
            "created_at": "2026-05-11T00:00:00+00:00",
        }
    ]
    branch_rows = [
        {
            "probability": 0.6,
            "description": "Auth stays degraded — incidents follow",
            "implication_for_product": "User churn risk",
            "horizon": "near_term",
        }
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    async def fake_query(q, params=None):
        if "root_signal_id" in q:
            return [scenario_rows]
        if "scenario_branch" in q:
            return [branch_rows]
        return [[]]

    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.mcp.tools.pool", mock_pool):
        from core.engine.mcp.tools import ace_scenario

        result = await ace_scenario(signal_id="signal:s1", product_id="product:test")

    assert "scenario" in result
    assert result["scenario"] is not None
    assert result["scenario"]["branches"][0]["probability"] == 0.6
