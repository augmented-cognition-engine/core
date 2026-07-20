# tests/test_tension_telemetry.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.graph.tension_telemetry import record_tension_surfaces


def _buckets():
    return {
        "tensions": [{"insight_id": "insight:brk", "via_insight": "insight:a", "relationship": "breaks"}],
        "consequences": [{"insight_id": "insight:cz", "via_insight": "insight:a", "relationship": "causes"}],
    }


@pytest.mark.asyncio
async def test_record_writes_row_per_surfacing_and_increments_metric():
    mock_db = AsyncMock()
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn
    with (
        patch("core.engine.graph.tension_telemetry.pool", mock_pool),
        patch("core.engine.graph.tension_telemetry.bus") as mock_bus,
        patch("core.engine.graph.tension_telemetry.graph_tension_surfaced_total") as mock_metric,
    ):
        mock_bus.emit = AsyncMock()
        n = await record_tension_surfaces(_buckets(), surface="ace_load", product_id="product:test")
    assert n == 2  # one tension + one consequence
    assert mock_db.query.await_count == 2
    assert mock_metric.labels.call_count == 2
    assert mock_bus.emit.await_count == 2


@pytest.mark.asyncio
async def test_record_non_fatal_on_db_error():
    with (
        patch("core.engine.graph.tension_telemetry.pool") as mock_pool,
        patch("core.engine.graph.tension_telemetry.bus") as mock_bus,
        patch("core.engine.graph.tension_telemetry.graph_tension_surfaced_total"),
    ):
        mock_pool.connection.side_effect = RuntimeError("db down")
        mock_bus.emit = AsyncMock()
        n = await record_tension_surfaces(_buckets(), surface="ace_load", product_id="product:test")
    assert n == 0  # nothing recorded, but no raise


@pytest.mark.asyncio
async def test_record_empty_buckets_no_writes():
    with patch("core.engine.graph.tension_telemetry.pool") as mock_pool:
        n = await record_tension_surfaces({"tensions": [], "consequences": []}, surface="ace_load", product_id="p:x")
    assert n == 0
    mock_pool.connection.assert_not_called()
