"""Tests for Phase C scenario builder."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_scenario_builder_produces_branches():
    """run_scenario_builder builds a Scenario with >= 1 branch per unbuilt signal."""
    signal_rows = [
        {
            "id": "signal:s1",
            "kind": "capability_decline",
            "description": "capability:auth score declined 0.20 over 7 days",
            "confidence": 0.8,
            "trend_data": {"scores": [0.75, 0.55], "days": 7},
            "scenario_built": False,
        }
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[signal_rows])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(
        return_value='{"branches": [{"probability": 0.6, "description": "Auth stays degraded — reliability incidents follow", "implication_for_product": "User churn risk increases", "horizon": "near_term"}, {"probability": 0.4, "description": "Team prioritizes auth — recovery within 2 weeks", "implication_for_product": "Feature velocity pauses temporarily", "horizon": "near_term"}]}'
    )

    with (
        patch("core.engine.foresight.scenario_builder.pool", mock_pool),
        patch("core.engine.foresight.scenario_builder.get_llm", return_value=mock_llm),
    ):
        from core.engine.foresight.scenario_builder import run_scenario_builder

        result = await run_scenario_builder("product:test")

    assert result["scenarios_built"] >= 1


@pytest.mark.asyncio
async def test_scenario_builder_empty_signals_is_noop():
    """Empty signal set → scenarios_built = 0, no error."""
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[[]])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.foresight.scenario_builder.pool", mock_pool):
        from core.engine.foresight.scenario_builder import run_scenario_builder

        result = await run_scenario_builder("product:test")

    assert result["scenarios_built"] == 0
    assert result["errors"] == 0


@pytest.mark.asyncio
async def test_scenario_builder_llm_failure_is_graceful():
    """LLM failure for a signal → skipped gracefully, no exception raised."""
    signal_rows = [
        {
            "id": "signal:s2",
            "kind": "gap_persistence",
            "description": "capability:observability gapped for 14 days",
            "confidence": 0.6,
            "trend_data": {"score": 0.28},
            "scenario_built": False,
        }
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[signal_rows])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=Exception("LLM timeout"))

    with (
        patch("core.engine.foresight.scenario_builder.pool", mock_pool),
        patch("core.engine.foresight.scenario_builder.get_llm", return_value=mock_llm),
    ):
        from core.engine.foresight.scenario_builder import run_scenario_builder

        result = await run_scenario_builder("product:test")

    assert result["scenarios_built"] == 0


@pytest.mark.asyncio
async def test_scenario_builder_registered_as_sentinel_engine():
    """scenario_builder is registered in the sentinel engine registry."""
    import core.engine.foresight.scenario_builder  # noqa: F401
    from core.engine.sentinel.registry import get_engine

    entry = get_engine("scenario_builder")
    assert entry is not None
    assert entry["cron"] == "0 * * * *"
