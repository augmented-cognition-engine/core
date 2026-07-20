# tests/test_decay_manager_archival.py
"""Tests for utilization-based insight archival in decay_manager.

When an insight has been loaded many times but rarely attributed, it's noise:
it wastes tokens on every future context build. Archive it so it's excluded from
loads but still inspectable for audit.

Rule: loaded_count >= _ARCHIVE_LOADED_MIN AND attributed_count < _ARCHIVE_ATTRIBUTED_MAX
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_archival_constants_exist_and_are_sensible():
    """Constants must be defined and reasonable."""
    from core.engine.sentinel.decay_manager import _ARCHIVE_ATTRIBUTED_MAX, _ARCHIVE_LOADED_MIN

    assert _ARCHIVE_LOADED_MIN >= 10  # need a meaningful sample
    assert _ARCHIVE_ATTRIBUTED_MAX < _ARCHIVE_LOADED_MIN  # must be << loaded to signal "unused"


@pytest.mark.asyncio
async def test_archive_unused_insights_marks_correct_rows():
    """Insights with high load, low attribution → status='archived'."""
    from core.engine.sentinel.decay_manager import _archive_unused_insights

    # high-load / low-attribution → archive
    target_rows = [
        {"insight_id": "insight:dead_weight_1", "loaded_count": 60, "attributed_count": 2},
        {"insight_id": "insight:dead_weight_2", "loaded_count": 100, "attributed_count": 4},
    ]

    archived_ids: list[str] = []

    async def fake_query(sql, params=None):
        if "insight_utilization" in sql and "SELECT" in sql.upper():
            return [target_rows]
        if "UPDATE" in sql.upper() and "archived" in sql:
            archived_ids.append((params or {}).get("id", ""))
            return [[]]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    archived_count = await _archive_unused_insights(mock_db, "product:test")

    assert archived_count == 2
    assert "insight:dead_weight_1" in archived_ids
    assert "insight:dead_weight_2" in archived_ids


@pytest.mark.asyncio
async def test_archive_ignores_well_attributed_insights():
    """Insights that ARE being used must not be archived even if loaded heavily."""
    from core.engine.sentinel.decay_manager import _archive_unused_insights

    async def fake_query(sql, params=None):
        # SELECT returns nothing — query filter is WHERE clause's job,
        # so this simulates the DB filter working correctly
        if "insight_utilization" in sql:
            return [[]]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    archived_count = await _archive_unused_insights(mock_db, "product:test")
    assert archived_count == 0


@pytest.mark.asyncio
async def test_run_decay_includes_archived_count():
    """_run_decay's return dict must include insights_archived."""
    from core.engine.sentinel.decay_manager import _run_decay

    async def fake_query(sql, params=None):
        if "FROM insight" in sql and "WHERE" in sql and "status = 'active'" in sql:
            return [[]]  # no active insights to decay
        if "insight_utilization" in sql:
            return [[{"insight_id": "insight:noise", "loaded_count": 75, "attributed_count": 1}]]
        if "UPDATE" in sql.upper() and "archived" in sql:
            return [[]]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    result = await _run_decay(mock_db, "product:test")
    assert "insights_archived" in result
    assert result["insights_archived"] == 1


@pytest.mark.asyncio
async def test_archive_failure_is_non_fatal():
    """Archival errors must not break the decay run."""
    from core.engine.sentinel.decay_manager import _archive_unused_insights

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("db gone"))

    # Must not raise
    count = await _archive_unused_insights(mock_db, "product:test")
    assert count == 0
