# tests/test_planner.py
"""Unit tests for engine.foresight.planner.plan_rollout."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.foresight.models import HypotheticalScore


def _make_pool(rows_by_keyword: dict):
    """Mock pool whose query() returns results keyed by query keyword."""
    mock_db = AsyncMock()

    def _query(q, params=None):
        for kw, result in rows_by_keyword.items():
            if kw in q:
                return result
        return [[]]

    mock_db.query = AsyncMock(side_effect=_query)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = mock_ctx
    return pool


_VALID_LLM_BRANCHES = {
    "branches": [
        {
            "path": ["auth overhaul", "add JWT middleware", "add auth tests"],
            "score_deltas": {"auth": 0.3, "testing": 0.2},
            "top_risk": "Migration complexity from legacy sessions",
        },
        {
            "path": ["auth overhaul", "add OAuth integration", "remove passwords"],
            "score_deltas": {"auth": 0.4, "security": 0.1},
            "top_risk": "Breaking change for existing users",
        },
        {
            "path": ["auth overhaul", "add MFA", "add recovery flows"],
            "score_deltas": {"auth": 0.2, "security": 0.3},
            "top_risk": "Increased user friction during migration",
        },
    ]
}

_CAP_ROWS = [
    [
        {"capability": "capability:auth", "score": 0.4},
        {"capability": "capability:testing", "score": 0.5},
        {"capability": "capability:security", "score": 0.6},
    ]
]


@pytest.mark.asyncio
async def test_plan_rollout_returns_rollout_result_with_three_branches():
    """plan_rollout returns a RolloutResult with 3 scored branches."""
    from core.engine.foresight.planner import plan_rollout

    pool = _make_pool(
        {
            "rollout_cache": [[]],  # cache miss
            "capability_quality": _CAP_ROWS,
            "CREATE rollout_cache": [[]],  # cache write
        }
    )

    scored = HypotheticalScore(gap_score=0.72, top_risks=[], capability_scores={})

    with (
        patch("core.engine.foresight.planner.llm") as mock_llm,
        patch("core.engine.foresight.planner.score_hypothetical_state", AsyncMock(return_value=scored)),
    ):
        mock_llm.complete_json = AsyncMock(return_value=_VALID_LLM_BRANCHES)
        result = await plan_rollout("auth overhaul", "product:platform", pool=pool)

    assert result.candidate == "auth overhaul"
    assert len(result.branches) == 3
    assert all(b.terminal_score == pytest.approx(0.72) for b in result.branches)
    assert result.best_path == result.branches[0].path  # first wins when all tied


@pytest.mark.asyncio
async def test_plan_rollout_depth_zero_returns_single_node_no_llm_call():
    """depth=0 returns one branch with only the candidate; no LLM call made."""
    from core.engine.foresight.planner import plan_rollout

    pool = _make_pool({"rollout_cache": [[]]})

    with patch("core.engine.foresight.planner.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock()
        result = await plan_rollout("auth overhaul", "product:platform", depth=0, pool=pool)

    mock_llm.complete_json.assert_not_called()
    assert len(result.branches) == 1
    assert result.branches[0].path == ["auth overhaul"]
    assert result.best_path == ["auth overhaul"]


@pytest.mark.asyncio
async def test_plan_rollout_best_path_is_from_highest_terminal_score():
    """best_path comes from the branch with the highest terminal_score."""
    from core.engine.foresight.planner import plan_rollout

    pool = _make_pool(
        {
            "rollout_cache": [[]],
            "capability_quality": _CAP_ROWS,
            "CREATE rollout_cache": [[]],
        }
    )

    scores = [
        HypotheticalScore(gap_score=0.50, top_risks=[], capability_scores={}),
        HypotheticalScore(gap_score=0.85, top_risks=[], capability_scores={}),  # best
        HypotheticalScore(gap_score=0.60, top_risks=[], capability_scores={}),
    ]

    with (
        patch("core.engine.foresight.planner.llm") as mock_llm,
        patch("core.engine.foresight.planner.score_hypothetical_state", AsyncMock(side_effect=scores)),
    ):
        mock_llm.complete_json = AsyncMock(return_value=_VALID_LLM_BRANCHES)
        result = await plan_rollout("auth overhaul", "product:platform", pool=pool)

    assert result.best_path == _VALID_LLM_BRANCHES["branches"][1]["path"]
    assert result.branches[1].terminal_score == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_plan_rollout_returns_cached_result_without_llm_call():
    """When a fresh cache entry exists, returns it without calling LLM."""
    from core.engine.foresight.planner import plan_rollout

    cached_branch = {
        "path": ["auth overhaul", "step1", "step2"],
        "terminal_score": 0.77,
        "top_risk": "cached risk",
        "state_override": {},
    }
    cached_row = [
        {
            "candidate": "auth overhaul",
            "product": "product:platform",
            "branches": [cached_branch],
            "best_path": cached_branch["path"],
            "created_at": "2026-05-11T00:00:00Z",
        }
    ]

    pool = _make_pool({"rollout_cache": [cached_row]})

    with patch("core.engine.foresight.planner.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock()
        result = await plan_rollout("auth overhaul", "product:platform", pool=pool)

    mock_llm.complete_json.assert_not_called()
    assert result.best_path == cached_branch["path"]
    assert result.branches[0].terminal_score == pytest.approx(0.77)


@pytest.mark.asyncio
async def test_plan_rollout_empty_capabilities_uses_zero_state():
    """When product has no capability_quality rows, state_override is empty and scoring still runs."""
    from core.engine.foresight.planner import plan_rollout

    pool = _make_pool(
        {
            "rollout_cache": [[]],
            "capability_quality": [[]],  # empty
            "CREATE rollout_cache": [[]],
        }
    )

    scored = HypotheticalScore(gap_score=0.0, top_risks=[], capability_scores={})

    with (
        patch("core.engine.foresight.planner.llm") as mock_llm,
        patch("core.engine.foresight.planner.score_hypothetical_state", AsyncMock(return_value=scored)),
    ):
        mock_llm.complete_json = AsyncMock(return_value=_VALID_LLM_BRANCHES)
        result = await plan_rollout("auth overhaul", "product:platform", pool=pool)

    assert len(result.branches) == 3
    assert all(b.terminal_score == pytest.approx(0.0) for b in result.branches)


@pytest.mark.asyncio
async def test_plan_rollout_llm_failure_returns_placeholder_branch():
    """When LLM returns unexpected output, returns one placeholder branch without crashing."""
    from core.engine.foresight.planner import plan_rollout

    pool = _make_pool(
        {
            "rollout_cache": [[]],
            "capability_quality": _CAP_ROWS,
            "CREATE rollout_cache": [[]],
        }
    )

    with (
        patch("core.engine.foresight.planner.llm") as mock_llm,
        patch(
            "core.engine.foresight.planner.score_hypothetical_state",
            AsyncMock(return_value=HypotheticalScore(gap_score=0.0, top_risks=[], capability_scores={})),
        ),
    ):
        mock_llm.complete_json = AsyncMock(return_value={"unexpected": "shape"})
        result = await plan_rollout("auth overhaul", "product:platform", pool=pool)

    assert len(result.branches) >= 1
    assert result.branches[0].path == ["auth overhaul"]
    assert "insufficient data" in result.branches[0].top_risk
