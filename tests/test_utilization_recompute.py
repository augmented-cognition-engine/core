from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_compute_updates_scores_for_insights_with_5_plus_loads():
    from core.engine.intelligence.utilization import compute_utilization_scores

    mock_db = AsyncMock()
    rows = [
        {"id": "insight_utilization:a", "loaded_count": 10, "attributed_count": 8},
        {"id": "insight_utilization:b", "loaded_count": 5, "attributed_count": 1},
    ]
    with patch("core.engine.intelligence.utilization.parse_rows", return_value=rows):
        result = await compute_utilization_scores("product:test", mock_db)

    assert result["updated"] == 2
    assert result["low_utilization_count"] == 0
    assert mock_db.query.call_count == 3  # 1 SELECT + 2 UPDATEs


@pytest.mark.asyncio
async def test_compute_counts_low_utilization_after_10_loads():
    from core.engine.intelligence.utilization import compute_utilization_scores

    mock_db = AsyncMock()
    rows = [{"id": "insight_utilization:x", "loaded_count": 15, "attributed_count": 0}]
    with patch("core.engine.intelligence.utilization.parse_rows", return_value=rows):
        result = await compute_utilization_scores("product:test", mock_db)

    assert result["updated"] == 1
    assert result["low_utilization_count"] == 1


@pytest.mark.asyncio
async def test_compute_skips_cold_start_insights():
    from core.engine.intelligence.utilization import compute_utilization_scores

    mock_db = AsyncMock()
    with patch("core.engine.intelligence.utilization.parse_rows", return_value=[]):
        result = await compute_utilization_scores("product:test", mock_db)

    assert result["updated"] == 0
    assert result["low_utilization_count"] == 0
    assert mock_db.query.call_count == 1  # only the SELECT


@pytest.mark.asyncio
async def test_compute_score_formula():
    from core.engine.intelligence.utilization import compute_utilization_scores

    mock_db = AsyncMock()
    rows = [{"id": "insight_utilization:z", "loaded_count": 3, "attributed_count": 1}]
    with patch("core.engine.intelligence.utilization.parse_rows", return_value=rows):
        await compute_utilization_scores("product:test", mock_db)

    update_call = mock_db.query.call_args_list[1]
    params = update_call[0][1]
    assert params["score"] == round(1 / 3, 4)
