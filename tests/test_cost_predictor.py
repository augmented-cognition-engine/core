"""Tests for CostPredictor — pre-task cost estimation from token ledger."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(rows):
    async def fake_query(q, params=None):
        if "token_ledger_entry" in q:
            return [rows]
        return [[]]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn
    return mock_pool


@pytest.mark.asyncio
async def test_estimate_returns_p50_p90():
    costs = [{"cost_usd": c} for c in [0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.010]]
    pool = _make_pool(costs)
    with patch("core.engine.intelligence.cost_predictor.pool", pool):
        from core.engine.intelligence.cost_predictor import CostPredictor

        result = await CostPredictor().estimate("coding", "product:test")

    assert result["sample_count"] == 10
    assert result["p50_usd"] > 0
    assert result["p90_usd"] >= result["p50_usd"]
    assert result["discipline"] == "coding"


@pytest.mark.asyncio
async def test_estimate_zero_samples():
    pool = _make_pool([])
    with patch("core.engine.intelligence.cost_predictor.pool", pool):
        from core.engine.intelligence.cost_predictor import CostPredictor

        result = await CostPredictor().estimate("design", "product:test")

    assert result["sample_count"] == 0
    assert result["p50_usd"] == 0.0
    assert result["p90_usd"] == 0.0


@pytest.mark.asyncio
async def test_estimate_non_fatal_on_error():
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = RuntimeError("db down")
    with patch("core.engine.intelligence.cost_predictor.pool", mock_pool):
        from core.engine.intelligence.cost_predictor import CostPredictor

        result = await CostPredictor().estimate("coding", "product:test")

    assert result == {}


@pytest.mark.asyncio
async def test_estimate_single_sample():
    pool = _make_pool([{"cost_usd": 0.0055}])
    with patch("core.engine.intelligence.cost_predictor.pool", pool):
        from core.engine.intelligence.cost_predictor import CostPredictor

        result = await CostPredictor().estimate("coding", "product:test")

    assert result["sample_count"] == 1
    assert result["p50_usd"] == pytest.approx(0.0055)
    assert result["p90_usd"] == pytest.approx(0.0055)


@pytest.mark.asyncio
async def test_estimate_query_field_names_match_record_write_shape():
    """The predictor must read the fields TokenLedger.record() actually writes
    — `product` as a record link and `resolved_at`. The prior
    product_id/created_at read matched zero rows by construction (record()
    never writes those names), so every estimate was an empty-sample 0.0.
    The duration::from::days() bind matches token_ledger.py's idiom — the old
    raw-string `$window` bind was never a duration either."""
    captured: list[tuple[str, dict | None]] = []

    async def fake_query(q, params=None):
        captured.append((q, params))
        return [[]]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn
    with patch("core.engine.intelligence.cost_predictor.pool", mock_pool):
        from core.engine.intelligence.cost_predictor import CostPredictor

        await CostPredictor().estimate("coding", "product:test", window_days=14)

    sql, params = captured[0]
    assert "product = <record>$pid" in sql
    assert "resolved_at" in sql
    assert "product_id" not in sql
    assert "created_at" not in sql
    assert "duration::from::days($window_days)" in sql
    assert params["window_days"] == 14
