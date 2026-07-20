"""Tests for create_decision lineage fields (perspectives + frameworks_used)."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_pool():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


@pytest.mark.asyncio
async def test_create_decision_passes_perspectives_and_frameworks_in_query(mock_pool):
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[{"id": "decision:abc", "title": "x"}])

    from core.engine.product.decisions import create_decision

    perspectives = [
        {"archetype": "pm", "contribution_summary": "proposed JWT", "confidence": 0.8},
        {"archetype": "skeptic", "contribution_summary": "flagged rotation", "confidence": 0.7},
    ]
    frameworks_used = ["trade_off_matrix"]
    await create_decision(
        title="Use JWT",
        decision_type="trade_off",
        rationale="Stateless",
        product_id="product:test",
        perspectives=perspectives,
        frameworks_used=frameworks_used,
        pool=mock_p,
    )
    # Find the CREATE call kwargs
    create_call = next(c for c in mock_db.query.call_args_list if "CREATE decision SET" in c[0][0])
    sql, params = create_call[0]
    assert "perspectives = $perspectives" in sql
    assert "frameworks_used = $frameworks_used" in sql
    assert params["perspectives"] == perspectives
    assert params["frameworks_used"] == frameworks_used


@pytest.mark.asyncio
async def test_create_decision_defaults_lineage_to_empty_lists(mock_pool):
    """Backward-compat: callers that omit kwargs get empty lists."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[{"id": "decision:abc", "title": "x"}])

    from core.engine.product.decisions import create_decision

    await create_decision(
        title="Stateless workers",
        decision_type="architecture",
        rationale="Easier to scale.",
        product_id="product:test",
        pool=mock_p,
    )
    create_call = next(c for c in mock_db.query.call_args_list if "CREATE decision SET" in c[0][0])
    _, params = create_call[0]
    assert params["perspectives"] == []
    assert params["frameworks_used"] == []
