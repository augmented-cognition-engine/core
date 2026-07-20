# tests/test_utilization_live_score.py
"""Tests for live utilization_score update in update_utilization.

Before this fix: utilization_score only updated nightly by compute_utilization_scores.
After: when loaded_count crosses the 5-sample threshold, the score is recomputed inline
so re-ranking on the next task benefits from fresh attribution data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_update_utilization_sets_score_when_samples_sufficient():
    """When an insight has >=5 loads, score = attributed/loaded must be written inline."""
    from core.engine.intelligence.utilization import update_utilization

    calls: list[tuple[str, dict]] = []

    async def fake_query(sql, params=None):
        calls.append((sql, params or {}))
        # Return the current counters for the RETURN clause — simulate 10 loaded, 3 attributed
        if "UPSERT" in sql:
            return [{"loaded_count": 10, "attributed_count": 3}]
        return [{}]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await update_utilization(
        product_id="product:test",
        loaded_ids=["insight:abc"],
        attributed_ids=[],
        db=mock_db,
    )

    score_updates = [(sql, p) for (sql, p) in calls if "utilization_score" in sql and "UPDATE" in sql.upper()]
    assert score_updates, "Must update utilization_score inline when samples >= 5"
    # Score should be 3/10 = 0.3
    updated_score = score_updates[0][1].get("score")
    assert updated_score == pytest.approx(0.3, abs=0.01)


@pytest.mark.asyncio
async def test_update_utilization_skips_score_when_samples_insufficient():
    """Below 5 samples, score should NOT be updated — stays at default 0.5."""
    from core.engine.intelligence.utilization import update_utilization

    calls: list[tuple[str, dict]] = []

    async def fake_query(sql, params=None):
        calls.append((sql, params or {}))
        if "UPSERT" in sql:
            return [{"loaded_count": 2, "attributed_count": 1}]
        return [{}]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await update_utilization(
        product_id="product:test",
        loaded_ids=["insight:new"],
        attributed_ids=[],
        db=mock_db,
    )

    score_updates = [sql for (sql, _) in calls if "utilization_score" in sql and "UPDATE" in sql.upper()]
    assert not score_updates, "Must NOT update score with fewer than 5 samples"


@pytest.mark.asyncio
async def test_update_utilization_score_reflects_attributed_increment():
    """Attributed insights should bump the score on the same call."""
    from core.engine.intelligence.utilization import update_utilization

    calls: list[tuple[str, dict]] = []

    async def fake_query(sql, params=None):
        calls.append((sql, params or {}))
        if "UPSERT" in sql:
            # After UPSERT the counter would be 6 loaded, 4 attributed
            return [{"loaded_count": 6, "attributed_count": 4}]
        return [{}]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await update_utilization(
        product_id="product:test",
        loaded_ids=["insight:xyz"],
        attributed_ids=["insight:xyz"],
        db=mock_db,
    )

    score_updates = [(sql, p) for (sql, p) in calls if "utilization_score" in sql and "UPDATE" in sql.upper()]
    assert score_updates
    # Score should be 4/6 ≈ 0.667
    assert score_updates[0][1].get("score") == pytest.approx(4 / 6, abs=0.01)


@pytest.mark.asyncio
async def test_update_utilization_score_failure_non_fatal():
    """If the score UPDATE fails, the whole call must not propagate."""
    from core.engine.intelligence.utilization import update_utilization

    async def fake_query(sql, params=None):
        if "utilization_score" in sql and "UPDATE" in sql.upper():
            raise RuntimeError("score write exploded")
        if "UPSERT" in sql:
            return [{"loaded_count": 10, "attributed_count": 5}]
        return [{}]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    # Must not raise
    await update_utilization(
        product_id="product:test",
        loaded_ids=["insight:boom"],
        attributed_ids=["insight:boom"],
        db=mock_db,
    )
