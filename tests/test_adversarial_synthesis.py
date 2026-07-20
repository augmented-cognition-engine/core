# tests/test_adversarial_synthesis.py
"""Tests for adversarial synthesis engine — challenging high-confidence beliefs."""

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


def test_engine_registration():
    """Adversarial synthesis is registered with correct cron."""
    from core.engine.sentinel.engines.adversarial_synthesis import run_adversarial_synthesis  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "adversarial_synthesis" in engine_registry
    assert _fires_on(engine_registry["adversarial_synthesis"]["cron"]) == {"Wednesday"}


@pytest.mark.asyncio
async def test_no_high_confidence_insights():
    """Returns {insights_challenged: 0} when no insights above threshold."""
    from core.engine.sentinel.engines.adversarial_synthesis import run_adversarial_synthesis

    with patch("core.engine.sentinel.engines.adversarial_synthesis.pool") as mock_pool:
        mock_conn = AsyncMock()
        # First query: insights with high-confidence → empty
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_adversarial_synthesis("product:test")

    assert result["insights_challenged"] == 0
    assert result["valid_challenges"] == 0


@pytest.mark.asyncio
async def test_valid_challenge_creates_conflict():
    """LLM evaluation > 0.6 creates a conflict record."""
    from core.engine.sentinel.engines.adversarial_synthesis import run_adversarial_synthesis

    call_idx = 0

    async def mock_query(query_str, params=None):
        nonlocal call_idx
        call_idx += 1
        if (
            "FROM insight" in query_str
            and "confidence" in query_str
            and "GROUP" not in query_str
            and "ORDER BY" not in query_str
        ):
            # Discipline discovery: insights with tags
            return [[{"tags": ["technology", "frontend"]}]]
        if "FROM insight" in query_str and "tags CONTAINS" in query_str:
            # Top insights for discipline
            return [
                [
                    {
                        "id": "insight:high1",
                        "content": "Always use APCA for contrast calculations",
                        "confidence": 0.95,
                        "product": "product:test",
                    }
                ]
            ]
        if "CREATE conflict" in query_str:
            return [[{"id": "conflict:adv1"}]]
        if "CREATE experiment_log" in query_str:
            return [[{"id": "experiment_log:1"}]]
        return [[]]

    with (
        patch("core.engine.sentinel.engines.adversarial_synthesis.pool") as mock_pool,
        patch("core.engine.sentinel.engines.adversarial_synthesis.llm") as mock_llm,
    ):
        mock_conn = AsyncMock()
        mock_conn.query = mock_query
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        # First LLM call: generate challenge
        # Second LLM call: evaluate challenge
        mock_llm.complete_json = AsyncMock(
            side_effect=[
                {"contradiction": "APCA has IE11 compatibility issues for legacy components"},
                {"score": 0.75, "reasoning": "Legitimate concern for legacy support"},
            ]
        )

        result = await run_adversarial_synthesis("product:test")

    assert result["insights_challenged"] >= 1
    assert result["valid_challenges"] >= 1
    assert result["conflicts_created"] >= 1


@pytest.mark.asyncio
async def test_invalid_challenge_no_conflict():
    """LLM evaluation < 0.6 logs to experiment_log but creates no conflict."""
    from core.engine.sentinel.engines.adversarial_synthesis import run_adversarial_synthesis

    create_calls = []

    async def mock_query(query_str, params=None):
        if "CREATE" in query_str:
            create_calls.append(query_str)
        if "FROM insight" in query_str and "tags CONTAINS" not in query_str and "ORDER BY" not in query_str:
            return [[{"tags": ["legal"]}]]
        if "FROM insight" in query_str and "tags CONTAINS" in query_str:
            return [
                [
                    {
                        "id": "insight:legal1",
                        "content": "Always include arbitration clause",
                        "confidence": 0.9,
                        "product": "product:test",
                    }
                ]
            ]
        if "CREATE experiment_log" in query_str:
            return [[{"id": "experiment_log:2"}]]
        return [[]]

    with (
        patch("core.engine.sentinel.engines.adversarial_synthesis.pool") as mock_pool,
        patch("core.engine.sentinel.engines.adversarial_synthesis.llm") as mock_llm,
    ):
        mock_conn = AsyncMock()
        mock_conn.query = mock_query
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(
            side_effect=[
                {"contradiction": "Arbitration isn't always best"},
                {"score": 0.3, "reasoning": "Too generic, not a real counter-argument"},
            ]
        )

        result = await run_adversarial_synthesis("product:test")

    assert result["valid_challenges"] == 0
    assert result["conflicts_created"] == 0
    # experiment_log was written but conflict was NOT
    experiment_creates = [c for c in create_calls if "experiment_log" in c]
    conflict_creates = [c for c in create_calls if "CREATE conflict" in c]
    assert len(experiment_creates) >= 1
    assert len(conflict_creates) == 0


@pytest.mark.asyncio
async def test_all_results_logged_to_experiment_log():
    """Both valid and invalid results are logged to experiment_log."""
    from core.engine.sentinel.engines.adversarial_synthesis import run_adversarial_synthesis

    experiment_log_params = []

    async def mock_query(query_str, params=None):
        if "CREATE experiment_log" in query_str:
            experiment_log_params.append(params)
            return [[{"id": f"experiment_log:{len(experiment_log_params)}"}]]
        if "FROM insight" in query_str and "tags CONTAINS" not in query_str and "ORDER BY" not in query_str:
            return [[{"tags": ["technology"]}]]
        if "FROM insight" in query_str and "tags CONTAINS" in query_str:
            return [
                [
                    {
                        "id": "insight:a",
                        "content": "Use TypeScript",
                        "confidence": 0.95,
                        "product": "product:test",
                    },
                    {
                        "id": "insight:b",
                        "content": "Use React 19",
                        "confidence": 0.9,
                        "product": "product:test",
                    },
                ]
            ]
        if "CREATE conflict" in query_str:
            return [[{"id": "conflict:x"}]]
        return [[]]

    with (
        patch("core.engine.sentinel.engines.adversarial_synthesis.pool") as mock_pool,
        patch("core.engine.sentinel.engines.adversarial_synthesis.llm") as mock_llm,
    ):
        mock_conn = AsyncMock()
        mock_conn.query = mock_query
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        # insight:a → valid challenge, insight:b → invalid challenge
        mock_llm.complete_json = AsyncMock(
            side_effect=[
                {"contradiction": "TypeScript adds build complexity"},
                {"score": 0.7, "reasoning": "Valid for small scripts"},
                {"contradiction": "React 18 is more stable"},
                {"score": 0.2, "reasoning": "Not a real argument"},
            ]
        )

        result = await run_adversarial_synthesis("product:test")

    assert result["insights_challenged"] == 2
    assert len(experiment_log_params) == 2  # Both logged


@pytest.mark.asyncio
async def test_budget_limit():
    """Only processes up to budget disciplines."""
    from core.engine.sentinel.engines.adversarial_synthesis import run_adversarial_synthesis

    with (
        patch("core.engine.sentinel.engines.adversarial_synthesis.pool") as mock_pool,
        patch("core.engine.sentinel.engines.adversarial_synthesis.llm") as mock_llm,
    ):
        mock_conn = AsyncMock()

        async def mock_query(query_str, params=None):
            if "FROM insight" in query_str and "tags CONTAINS" not in query_str and "ORDER BY" not in query_str:
                # Return many tags to produce many disciplines
                return [[{"tags": [f"discipline_{i}"]} for i in range(50)]]
            if "FROM insight" in query_str and "tags CONTAINS" in query_str:
                return [
                    [
                        {
                            "id": "insight:x",
                            "content": "test",
                            "confidence": 0.9,
                            "product": "product:test",
                        }
                    ]
                ]
            if "CREATE experiment_log" in query_str:
                return [[{"id": "experiment_log:x"}]]
            return [[]]

        mock_conn.query = mock_query
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(return_value={"contradiction": "test", "score": 0.3, "reasoning": "weak"})

        # Budget = 3 → only 3 disciplines processed
        result = await run_adversarial_synthesis("product:test", budget=3)

    # With budget=3, max 3 disciplines processed
    assert result["domains_processed"] <= 3
