# tests/test_rollout_mcp.py
"""Tests for ace_rollout MCP tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.foresight.models import RolloutBranch, RolloutResult


def _make_result(scores: list[float]) -> RolloutResult:
    branches = [
        RolloutBranch(
            path=["auth overhaul", f"step{i + 1}a", f"step{i + 1}b"],
            terminal_score=score,
            top_risk=f"risk {i}",
            state_override={},
        )
        for i, score in enumerate(scores)
    ]
    best = max(branches, key=lambda b: b.terminal_score)
    return RolloutResult(
        candidate="auth overhaul",
        product_id="product:platform",
        branches=branches,
        best_path=best.path,
        created_at="2026-05-11T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_ace_rollout_returns_branches_and_best_path():
    """ace_rollout returns candidate, best_path, and branch list with required fields."""
    from core.engine.mcp.tools import ace_rollout

    mock_result = _make_result([0.5, 0.85, 0.6])

    with patch("core.engine.foresight.planner.plan_rollout", AsyncMock(return_value=mock_result)):
        result = await ace_rollout("auth overhaul", "product:platform")

    assert result["candidate"] == "auth overhaul"
    assert result["best_path"] == mock_result.best_path
    assert len(result["branches"]) == 3
    branch = result["branches"][0]
    assert "path" in branch
    assert "terminal_score" in branch
    assert "top_risk" in branch


@pytest.mark.asyncio
async def test_ace_rollout_empty_branches_returns_safe_response():
    """ace_rollout with no branches returns a valid dict without crashing."""
    from core.engine.mcp.tools import ace_rollout

    empty_result = RolloutResult(
        candidate="empty",
        product_id="product:platform",
        branches=[],
        best_path=[],
        created_at="2026-05-11T00:00:00Z",
    )

    with patch("core.engine.foresight.planner.plan_rollout", AsyncMock(return_value=empty_result)):
        result = await ace_rollout("empty", "product:platform")

    assert result["branches"] == []
    assert result["best_path"] == []
