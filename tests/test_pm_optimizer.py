# tests/test_pm_optimizer.py
"""Tests for the PM Self-Optimizer overnight engine.

TDD: tests written before implementation.
"""

from unittest.mock import AsyncMock, patch

import pytest


def _fires_on(cron: str) -> set[str]:
    """The days a cron ACTUALLY fires, in APScheduler's reading of it.

    Asserting the cron STRING is the weak form and it is how this bug lived: the old
    assertion here was `== "0 5 * * 0"  # Sunday 5 AM`, which passed for months while the
    engine ran on MONDAY. APScheduler reads day-of-week 0=mon..6=sun, not the standard
    crontab 0=sun, and does not translate. Assert the behaviour, not the literal.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apscheduler.triggers.cron import CronTrigger

    tz = ZoneInfo("UTC")
    trigger = CronTrigger.from_crontab(cron, timezone=tz)
    days, prev = set(), datetime(2026, 7, 12, tzinfo=tz)  # a Sunday
    for _ in range(7):
        nxt = trigger.get_next_fire_time(None, prev)
        days.add(nxt.strftime("%A"))
        prev = nxt.replace(hour=23, minute=59)
    return days


def test_pm_optimizer_registers():
    """pm_optimizer should be in engine_registry with correct cron after import."""
    from core.engine.sentinel.engines.pm_optimizer import run_pm_optimizer  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "pm_optimizer" in engine_registry
    entry = engine_registry["pm_optimizer"]
    assert _fires_on(entry["cron"]) == {"Sunday"}  # ...and now it really is Sunday
    assert callable(entry["fn"])


@pytest.mark.asyncio
async def test_pm_optimizer_empty_org():
    """No specs, no feedback → returns zero counts without errors."""
    from core.engine.sentinel.engines.pm_optimizer import run_pm_optimizer

    with patch("core.engine.sentinel.engines.pm_optimizer.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])  # all queries return empty

        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_pm_optimizer("product:default")

    assert isinstance(result, dict)
    assert result["specs_analyzed"] == 0
    assert result["first_pass_rate"] == 0.0
    assert result["gap_closure_rate"] == 0.0
    assert result["insights_generated"] == 0


@pytest.mark.asyncio
async def test_pm_optimizer_with_data():
    """Mock DB with specs + feedback → returns calculated rates."""
    from core.engine.sentinel.engines.pm_optimizer import run_pm_optimizer

    specs = [
        {"status": "completed"},
        {"status": "completed"},
        {"status": "failed"},
        {"status": "completed"},
    ]
    feedbacks = [
        {"feedback_type": "blocker", "resolved": True},
        {"feedback_type": "blocker", "resolved": False},
        {"feedback_type": "clarification", "resolved": True},
    ]
    qualities = [
        {"capability": "auth", "dimension": "security", "score": 0.7},
        {"capability": "auth", "dimension": "testing", "score": 0.4},
        {"capability": "payments", "dimension": "security", "score": 0.8},
    ]

    with patch("core.engine.sentinel.engines.pm_optimizer.pool") as mock_pool:
        mock_db = AsyncMock()
        call_count = {"n": 0}

        async def _side_effect(query, params=None):
            call_count["n"] += 1
            n = call_count["n"]
            if n == 1:
                # agent_spec query
                return [specs]
            if n == 2:
                # agent_feedback query
                return [feedbacks]
            if n == 3:
                # capability_quality query
                return [qualities]
            # CREATE observation (insight write)
            return [[{"id": "observation:1"}]]

        mock_db.query = AsyncMock(side_effect=_side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_pm_optimizer("product:default")

    assert isinstance(result, dict)
    assert result["specs_analyzed"] == 4
    # 3 completed, 1 failed → 3/4 = 0.75
    assert result["first_pass_rate"] == pytest.approx(0.75)
    # 2 resolved out of 3 feedbacks → 2/3
    assert result["feedback_resolution_rate"] == pytest.approx(2 / 3)
    # 2 out of 3 quality dimensions score >= 0.6 → 2/3
    assert result["gap_closure_rate"] == pytest.approx(2 / 3)
    # first_pass_rate >= 0.5, so no low-quality insight should be generated
    assert result["insights_generated"] == 0
    # pm_health_score is average of the three rates
    expected_health = (0.75 + 2 / 3 + 2 / 3) / 3
    assert result["pm_health_score"] == pytest.approx(expected_health)
