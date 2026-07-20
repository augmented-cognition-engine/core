# tests/test_automations_gap_to_idea.py
"""Tests for sentinel gap → idea queue wiring (Gap 3 closure).

Tests the extracted _create_ideas_for_critical_gaps() helper directly,
avoiding the full SurrealPool/briefing mock complexity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.engine.events.automations import _create_ideas_for_critical_gaps


@pytest.mark.asyncio
async def test_creates_idea_for_each_critical_gap():
    """One critical gap row → one idea CREATE call."""
    critical_rows = [
        {
            "capability_slug": "auth_module",
            "dimension": "security",
            "score": 0.1,
            "gaps": ["No input validation", "No auth checks"],
        }
    ]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=[critical_rows, [{"id": "idea:new"}]])

    await _create_ideas_for_critical_gaps("product:test", mock_db)

    calls_sql = [str(c) for c in mock_db.query.call_args_list]
    assert any("CREATE idea" in c for c in calls_sql)


@pytest.mark.asyncio
async def test_no_critical_gaps_skips_idea_creation():
    """Empty critical-gaps result → no CREATE idea."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    await _create_ideas_for_critical_gaps("product:test", mock_db)

    calls_sql = [str(c) for c in mock_db.query.call_args_list]
    assert not any("CREATE idea" in c for c in calls_sql)


@pytest.mark.asyncio
async def test_limits_to_three_worst_gaps():
    """Never creates more than 3 ideas per run regardless of gap count."""
    critical_rows = [
        {"capability_slug": f"cap_{i}", "dimension": "security", "score": 0.05, "gaps": ["gap"]} for i in range(10)
    ]

    created: list[str] = []

    async def fake_query(sql, params=None):
        if "capability_quality" in sql:
            return critical_rows
        if "CREATE idea" in sql:
            created.append(sql)
            return [{"id": f"idea:{len(created)}"}]
        return []

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await _create_ideas_for_critical_gaps("product:test", mock_db)

    assert len(created) <= 3


@pytest.mark.asyncio
async def test_idea_title_contains_capability_and_dimension():
    """Created idea title identifies the capability and dimension."""
    critical_rows = [{"capability_slug": "payments", "dimension": "security", "score": 0.05, "gaps": ["missing auth"]}]

    captured_params: list[dict] = []

    async def fake_query(sql, params=None):
        if "capability_quality" in sql:
            return critical_rows
        if "CREATE idea" in sql:
            if params:
                captured_params.append(params)
            return [{"id": "idea:1"}]
        return []

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await _create_ideas_for_critical_gaps("product:test", mock_db)

    assert captured_params
    title = captured_params[0].get("title", "")
    assert "payments" in title or "security" in title


@pytest.mark.asyncio
async def test_db_failure_is_non_fatal():
    """Exception in DB query does not propagate — handler must never crash."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("db exploded"))

    # Should not raise
    await _create_ideas_for_critical_gaps("product:test", mock_db)
