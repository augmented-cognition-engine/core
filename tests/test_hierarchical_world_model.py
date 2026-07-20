"""Tests for hierarchical world model — planner reads scenario_constraint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_planner_injects_constraint_into_prompt():
    """Active scenario_constraint is prepended to the LLM prompt during plan_rollout."""
    constraint_rows = [
        {
            "description": "capability:auth trending down — avoid expanding auth surface area",
            "affected_domains": ["auth", "security"],
        }
    ]

    call_prompt: dict = {}

    async def fake_complete_json(prompt, model=None):
        call_prompt["prompt"] = prompt
        return {"branches": [{"path": ["candidate", "f1", "f2"], "score_deltas": {}, "top_risk": "risk A"}]}

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    async def fake_query(q, params=None):
        if "scenario_constraint" in q:
            return [constraint_rows]
        if "rollout_cache" in q and "SELECT" in q:
            return [[]]
        if "capability_quality" in q:
            return [[{"capability": "capability:auth", "score": 0.55}]]
        return [[]]

    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(side_effect=fake_complete_json)

    with (
        patch("core.engine.foresight.planner.default_pool", mock_pool),
        patch("core.engine.foresight.planner.llm", mock_llm),
        patch("core.engine.core.db.pool", mock_pool),
    ):
        from core.engine.foresight.planner import plan_rollout

        await plan_rollout("ship ML feature", "product:test", pool=mock_pool)

    assert "capability:auth trending down" in call_prompt.get("prompt", "")


@pytest.mark.asyncio
async def test_planner_proceeds_when_no_constraints():
    """plan_rollout works normally when no scenario_constraint records exist."""
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    async def fake_query(q, params=None):
        if "scenario_constraint" in q or "rollout_cache" in q:
            return [[]]
        if "capability_quality" in q:
            return [[{"capability": "capability:auth", "score": 0.7}]]
        return [[]]

    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={"branches": [{"path": ["cand", "a1", "a2"], "score_deltas": {}, "top_risk": "risk"}]}
    )

    with (
        patch("core.engine.foresight.planner.default_pool", mock_pool),
        patch("core.engine.foresight.planner.llm", mock_llm),
        patch("core.engine.core.db.pool", mock_pool),
    ):
        from core.engine.foresight.planner import plan_rollout

        result = await plan_rollout("ship feature", "product:test", pool=mock_pool)

    assert result.candidate == "ship feature"
