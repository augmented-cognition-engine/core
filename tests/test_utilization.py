"""Tests for the utilization tracking module."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_update_utilization_increments_loaded_count():
    from core.engine.intelligence.utilization import update_utilization

    mock_db = AsyncMock()
    mock_db.query.return_value = [{}]
    await update_utilization(
        product_id="product:test",
        loaded_ids=["insight:1", "insight:2", "insight:3"],
        attributed_ids=["insight:1"],
        db=mock_db,
    )
    # 3 loaded insights → 3 UPSERT calls (1 attributed + 2 loaded-only)
    assert mock_db.query.call_count == 3


@pytest.mark.asyncio
async def test_update_utilization_increments_attributed_count():
    from core.engine.intelligence.utilization import update_utilization

    mock_db = AsyncMock()
    mock_db.query.return_value = [{}]
    await update_utilization(
        product_id="product:test",
        loaded_ids=["insight:1", "insight:2"],
        attributed_ids=["insight:2"],
        db=mock_db,
    )
    # 2 loaded insights → 2 UPSERT calls (1 attributed + 1 loaded-only)
    assert mock_db.query.call_count == 2


@pytest.mark.asyncio
async def test_update_utilization_noop_on_empty():
    from core.engine.intelligence.utilization import update_utilization

    mock_db = AsyncMock()
    await update_utilization(product_id="product:test", loaded_ids=[], attributed_ids=[], db=mock_db)
    mock_db.query.assert_not_called()
