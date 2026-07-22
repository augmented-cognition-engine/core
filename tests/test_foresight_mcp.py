# tests/test_foresight_mcp.py
"""Tests for ace_forecast and ace_calibration MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(rows_by_keyword: dict):
    mock_db = AsyncMock()

    async def _query(q, params=None):
        for kw, result in rows_by_keyword.items():
            if kw in q:
                return result
        return [[]]

    mock_db.query = AsyncMock(side_effect=_query)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = mock_ctx
    return pool


@pytest.mark.asyncio
async def test_ace_forecast_returns_open_predictions():
    """ace_forecast returns a list of open predictions with required fields."""
    from core.engine.mcp.tools import ace_forecast

    predictions = [
        {
            "id": "decision_prediction:p1",
            "decision": "decision:d1",
            "archetype": "executor",
            "discipline": "testing",
            "horizon_days": 14,
            "primary_risk": "auth coverage stays low",
            "falsification_condition": "test coverage below 60% after 14 days",
            "closed": False,
            "created_at": "2026-05-01T00:00:00Z",
        }
    ]

    pool = _make_pool({"decision_prediction": [predictions]})

    with patch("core.engine.mcp.tools.pool", pool):
        result = await ace_forecast("product:platform")

    assert "predictions" in result
    assert len(result["predictions"]) == 1
    assert result["predictions"][0]["primary_risk"] == "auth coverage stays low"
    assert "total_open" in result


@pytest.mark.asyncio
async def test_ace_forecast_empty_when_no_predictions():
    """ace_forecast returns empty list when no open predictions exist."""
    from core.engine.mcp.tools import ace_forecast

    pool = _make_pool({"decision_prediction": [[]]})

    with patch("core.engine.mcp.tools.pool", pool):
        result = await ace_forecast("product:platform")

    assert result["total_open"] == 0
    assert result["predictions"] == []


@pytest.mark.asyncio
async def test_ace_calibration_returns_archetype_scores():
    """ace_calibration returns per-archetype scores with required fields."""
    from core.engine.mcp.tools import ace_calibration

    cal_rows = [
        {
            "archetype": "executor",
            "discipline": "testing",
            "calibration_score": 0.82,
            "sample_count": 7,
            "updated_at": "2026-05-09T02:00:00Z",
        }
    ]

    pool = _make_pool({"archetype_calibration": [cal_rows]})

    with patch("core.engine.mcp.tools.pool", pool):
        result = await ace_calibration("product:platform")

    assert "calibrations" in result
    assert len(result["calibrations"]) == 1
    cal = result["calibrations"][0]
    assert cal["archetype"] == "executor"
    assert cal["calibration_score"] == pytest.approx(0.82)
    assert cal["sample_count"] == 7

    query = pool.connection.return_value.__aenter__.return_value.query
    sql, params = query.await_args.args
    assert "WHERE product = <record>$product" in sql
    assert params == {"product": "product:platform"}


@pytest.mark.asyncio
async def test_ace_calibration_empty_db_returns_empty():
    """ace_calibration returns empty list and message when no data yet."""
    from core.engine.mcp.tools import ace_calibration

    pool = _make_pool({"archetype_calibration": [[]]})

    with patch("core.engine.mcp.tools.pool", pool):
        result = await ace_calibration("product:platform")

    assert result["calibrations"] == []
    assert "message" in result
