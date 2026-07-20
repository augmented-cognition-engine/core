# tests/test_forward_momentum.py
"""Unit tests for the enriched _get_forward_momentum in engine.api.canvas."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.foresight.models import RolloutBranch, RolloutResult


def _make_pool(rows: list[dict]):
    """Return a mock pool whose db.query() returns the given rows."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[rows])
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = mock_ctx
    return pool


def _make_rollout(score: float, path: list[str], risk: str) -> RolloutResult:
    branch = RolloutBranch(
        path=path,
        terminal_score=score,
        top_risk=risk,
        state_override={},
    )
    return RolloutResult(
        candidate=path[0],
        product_id="product:platform",
        branches=[branch],
        best_path=path,
        created_at="2026-05-11T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_forward_momentum_includes_rollout_fields_when_planner_succeeds():
    """Returned items include terminal_score, forced_decisions, top_risk when plan_rollout succeeds."""
    from core.engine.api.canvas import _get_forward_momentum

    initiative_rows = [
        {"title": "auth overhaul", "description": "Improve auth security", "status": "ready"},
    ]
    mock_rollout = _make_rollout(
        score=0.72,
        path=["auth overhaul", "add JWT middleware", "add auth tests"],
        risk="Migration complexity from legacy sessions",
    )

    mock_pool = _make_pool(initiative_rows)

    with (
        patch("core.engine.core.db.pool", mock_pool),
        patch("core.engine.foresight.planner.plan_rollout", AsyncMock(return_value=mock_rollout)),
    ):
        items = await _get_forward_momentum("product:platform")

    assert len(items) == 1
    item = items[0]
    assert item["title"] == "auth overhaul"
    assert item["terminal_score"] == pytest.approx(0.72)
    assert item["forced_decisions"] == ["add JWT middleware", "add auth tests"]
    assert item["top_risk"] == "Migration complexity from legacy sessions"


@pytest.mark.asyncio
async def test_forward_momentum_returns_basic_fields_when_planner_raises():
    """Items still returned with title + rationale when plan_rollout raises; no rollout fields."""
    from core.engine.api.canvas import _get_forward_momentum

    initiative_rows = [
        {"title": "api redesign", "description": "Redesign REST API", "status": "planning"},
    ]
    mock_pool = _make_pool(initiative_rows)

    with (
        patch("core.engine.core.db.pool", mock_pool),
        patch("core.engine.foresight.planner.plan_rollout", AsyncMock(side_effect=RuntimeError("LLM unavailable"))),
    ):
        items = await _get_forward_momentum("product:platform")

    assert len(items) == 1
    assert items[0]["title"] == "api redesign"
    assert items[0]["rationale"] == "Redesign REST API"
    assert "terminal_score" not in items[0]
    assert "forced_decisions" not in items[0]
    assert "top_risk" not in items[0]


@pytest.mark.asyncio
async def test_forward_momentum_returns_empty_when_no_initiatives():
    """Returns empty list when initiative table has no matching rows."""
    from core.engine.api.canvas import _get_forward_momentum

    mock_pool = _make_pool([])

    with patch("core.engine.core.db.pool", mock_pool):
        items = await _get_forward_momentum("product:platform")

    assert items == []
