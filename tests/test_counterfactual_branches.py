"""Tests for counterfactual branch persistence — speculative_decision nodes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_non_best_branches_written_as_speculative_decisions():
    """3 branches from plan_rollout → 2 non-best written as speculative_decision."""
    written_tables: list[str] = []

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    async def fake_query(q, params=None):
        if "speculative_decision" in q and "CREATE" in q:
            written_tables.append("speculative_decision")
        if "scenario_constraint" in q or ("rollout_cache" in q and "SELECT" in q):
            return [[]]
        if "capability_quality" in q:
            return [[{"capability": "capability:auth", "score": 0.7}]]
        return [[]]

    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "branches": [
                {"path": ["cand", "a1", "a2"], "score_deltas": {}, "top_risk": "risk A"},
                {"path": ["cand", "b1", "b2"], "score_deltas": {}, "top_risk": "risk B"},
                {"path": ["cand", "c1", "c2"], "score_deltas": {}, "top_risk": "risk C"},
            ]
        }
    )

    with (
        patch("core.engine.foresight.planner.default_pool", mock_pool),
        patch("core.engine.foresight.planner.llm", mock_llm),
        patch("core.engine.core.db.pool", mock_pool),
    ):
        from core.engine.foresight.planner import plan_rollout

        await plan_rollout("candidate decision", "product:test", pool=mock_pool)

    assert written_tables.count("speculative_decision") == 2


@pytest.mark.asyncio
async def test_single_branch_no_speculative_decisions():
    """Single branch (best = only) → no speculative_decision written."""
    written_speculative: list[bool] = []

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    async def fake_query(q, params=None):
        if "speculative_decision" in q and "CREATE" in q:
            written_speculative.append(True)
        if "scenario_constraint" in q or ("rollout_cache" in q and "SELECT" in q):
            return [[]]
        if "capability_quality" in q:
            return [[{"capability": "capability:auth", "score": 0.7}]]
        return [[]]

    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={"branches": [{"path": ["cand", "a1", "a2"], "score_deltas": {}, "top_risk": "only branch"}]}
    )

    with (
        patch("core.engine.foresight.planner.default_pool", mock_pool),
        patch("core.engine.foresight.planner.llm", mock_llm),
        patch("core.engine.core.db.pool", mock_pool),
    ):
        from core.engine.foresight.planner import plan_rollout

        await plan_rollout("solo candidate", "product:test", pool=mock_pool)

    assert written_speculative == []


@pytest.mark.asyncio
async def test_speculative_write_failure_does_not_abort_rollout():
    """DB failure writing speculative_decision still returns a valid RolloutResult."""
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    async def fake_query(q, params=None):
        if "speculative_decision" in q and "CREATE" in q:
            raise Exception("write error")
        if "scenario_constraint" in q or ("rollout_cache" in q and "SELECT" in q):
            return [[]]
        if "capability_quality" in q:
            return [[{"capability": "capability:auth", "score": 0.7}]]
        return [[]]

    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "branches": [
                {"path": ["cand", "a1", "a2"], "score_deltas": {}, "top_risk": "risk A"},
                {"path": ["cand", "b1", "b2"], "score_deltas": {}, "top_risk": "risk B"},
            ]
        }
    )

    with (
        patch("core.engine.foresight.planner.default_pool", mock_pool),
        patch("core.engine.foresight.planner.llm", mock_llm),
        patch("core.engine.core.db.pool", mock_pool),
    ):
        from core.engine.foresight.planner import plan_rollout

        result = await plan_rollout("candidate", "product:test", pool=mock_pool)

    assert result.candidate == "candidate"
    assert len(result.branches) >= 1
