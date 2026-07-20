# tests/test_calibration_engine.py
"""Tests for calibration sentinel engine."""

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


def test_engine_registered():
    """Calibration engine is registered in the sentinel registry."""
    from core.engine.sentinel.engines.calibration_engine import run_calibration  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "calibration" in engine_registry
    assert _fires_on(engine_registry["calibration"]["cron"]) == {"Sunday"}


@pytest.mark.asyncio
async def test_calibration_engine_full_run():
    """Full run with mock DB returns calibrated domains."""
    from core.engine.sentinel.engines.calibration_engine import run_calibration

    with patch("core.engine.sentinel.engines.calibration_engine.pool") as mock_pool:
        mock_conn = AsyncMock()
        call_count = 0

        async def mock_query(query_str, params=None):
            nonlocal call_count
            call_count += 1
            if "FROM task" in query_str:
                return [
                    [
                        {"discipline": "architecture", "self_assessment": 0.8, "feedback_human": "accepted"},
                        {"discipline": "architecture", "self_assessment": 0.8, "feedback_human": "accepted"},
                        {"discipline": "architecture", "self_assessment": 0.8, "feedback_human": "accepted"},
                        {"discipline": "architecture", "self_assessment": 0.8, "feedback_human": "accepted"},
                        {"discipline": "architecture", "self_assessment": 0.8, "feedback_human": "rejected"},
                    ]
                ]
            if "UPSERT calibration" in query_str:
                return [[]]
            return [[]]

        mock_conn.query = mock_query
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_calibration("product:test")

    assert result["domains_calibrated"] >= 1


@pytest.mark.asyncio
async def test_calibration_engine_uses_grader_only_tasks():
    """Un-starve: tasks with grader_score but NO human feedback must now feed the curve (keystone #1
    payoff). Previously the feedback_human IS NOT NONE filter excluded them entirely."""
    from core.engine.sentinel.engines.calibration_engine import run_calibration

    with patch("core.engine.sentinel.engines.calibration_engine.pool") as mock_pool:
        mock_conn = AsyncMock()
        captured_query = {}

        async def mock_query(query_str, params=None):
            if "FROM task" in query_str:
                captured_query["task"] = query_str
                return [
                    [
                        {"discipline": "security", "self_assessment": 0.9, "feedback_human": None, "grader_score": 0.2},
                        {"discipline": "security", "self_assessment": 0.9, "feedback_human": None, "grader_score": 0.1},
                        {"discipline": "security", "self_assessment": 0.9, "feedback_human": None, "grader_score": 0.3},
                        {"discipline": "security", "self_assessment": 0.9, "feedback_human": None, "grader_score": 0.0},
                        {"discipline": "security", "self_assessment": 0.9, "feedback_human": None, "grader_score": 0.2},
                    ]
                ]
            return [[]]

        mock_conn.query = mock_query
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_calibration("product:test")

    # The query must admit grader-only tasks, and the curve must reflect overconfidence (0.9 predicted,
    # all grades < 0.7 success threshold → high miscalibration), sourced entirely from the grader.
    assert "grader_score IS NOT NONE" in captured_query["task"]
    assert result["domains_calibrated"] >= 1
    assert result["grader_samples"] == 5
    assert result["human_samples"] == 0


@pytest.mark.asyncio
async def test_calibration_engine_no_tasks():
    """Engine handles no tasks gracefully."""
    from core.engine.sentinel.engines.calibration_engine import run_calibration

    with patch("core.engine.sentinel.engines.calibration_engine.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_calibration("product:test")

    assert result["domains_calibrated"] == 0
