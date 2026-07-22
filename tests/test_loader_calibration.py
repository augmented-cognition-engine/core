from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_calibration_weights_returned_in_loaded():
    """load_intelligence includes calibration_weights dict when data exists."""
    cal_rows = [
        {"archetype": "analyst", "calibration_score": 0.82, "sample_count": 5},
        {"archetype": "advisor", "calibration_score": 0.61, "sample_count": 3},
    ]

    async def fake_query(q, params=None):
        if "archetype_calibration" in q:
            assert "product = <record>$product" in q
            assert params == {"product": "product:test", "discipline": "architecture"}
            return [cal_rows]
        return [[]]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.orchestrator.loader.pool", mock_pool):
        from core.engine.orchestrator.loader import load_intelligence

        result = await load_intelligence(
            discipline="architecture",
            product_id="product:test",
            mode="reactive",
        )

    assert "calibration_weights" in result
    weights = result["calibration_weights"]
    assert weights["analyst"] == pytest.approx(0.82)
    assert weights["advisor"] == pytest.approx(0.61)


@pytest.mark.asyncio
async def test_calibration_weights_empty_when_no_data():
    """calibration_weights is {} when no archetype_calibration rows exist."""

    async def fake_query(q, params=None):
        return [[]]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.orchestrator.loader.pool", mock_pool):
        from core.engine.orchestrator.loader import load_intelligence

        result = await load_intelligence(
            discipline="architecture",
            product_id="product:test",
            mode="reactive",
        )

    assert result["calibration_weights"] == {}


@pytest.mark.asyncio
async def test_calibration_weights_degrade_gracefully_on_error():
    """calibration_weights is {} when DB query raises — never blocks the load."""

    async def fake_query(q, params=None):
        if "archetype_calibration" in q:
            raise Exception("db error")
        return [[]]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.orchestrator.loader.pool", mock_pool):
        from core.engine.orchestrator.loader import load_intelligence

        result = await load_intelligence(
            discipline="architecture",
            product_id="product:test",
            mode="reactive",
        )

    assert result["calibration_weights"] == {}
