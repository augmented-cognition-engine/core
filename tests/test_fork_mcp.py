# tests/test_fork_mcp.py
"""Tests for the ace_fork_reasoning MCP tool — forkable foresight reachability.

fork_and_compare is mocked (it's covered by tests/test_fork_planner.py); these assert the tool's
dict shape + the error paths + registration, with no real LLM."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.foresight.fork_models import ForkBranch, ForkResult


def _result(best_label="adversarial"):
    original = ForkBranch(
        variation_label="original", lens="conclude", conclusion="ship it", eval_score=0.3, combined_score=0.3
    )
    fork = ForkBranch(
        variation_label="adversarial",
        lens="adversarial",
        conclusion="a forked view",
        eval_score=0.8,
        combined_score=0.8,
    )
    best = fork if best_label != "original" else original
    return ForkResult(
        run_id="reasoning_run:abc",
        checkpoint_seq=2,
        original=original,
        forks=[fork],
        best=best,
        created_at="2026-06-24T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_ace_fork_reasoning_returns_comparison():
    from core.engine.mcp.tools import ace_fork_reasoning

    with patch("core.engine.foresight.fork_planner.fork_and_compare", AsyncMock(return_value=_result())):
        out = await ace_fork_reasoning("reasoning_run:abc", 2, product_id="product:platform")
    assert out["recommendation"] == "fork"  # a fork beat the original
    assert out["best"]["lens"] == "adversarial"
    assert out["best"]["score"] == 0.8
    assert len(out["forks"]) == 1
    assert out["original"]["score"] == 0.3


@pytest.mark.asyncio
async def test_ace_fork_reasoning_keep_original():
    from core.engine.mcp.tools import ace_fork_reasoning

    with patch(
        "core.engine.foresight.fork_planner.fork_and_compare", AsyncMock(return_value=_result(best_label="original"))
    ):
        out = await ace_fork_reasoning("reasoning_run:abc", 2)
    assert out["recommendation"] == "keep_original"


@pytest.mark.asyncio
async def test_ace_fork_reasoning_none_is_error():
    from core.engine.mcp.tools import ace_fork_reasoning

    with patch("core.engine.foresight.fork_planner.fork_and_compare", AsyncMock(return_value=None)):
        out = await ace_fork_reasoning("reasoning_run:missing", 9)
    assert "error" in out
    assert out["run_id"] == "reasoning_run:missing"


@pytest.mark.asyncio
async def test_ace_fork_reasoning_exception_is_error():
    from core.engine.mcp.tools import ace_fork_reasoning

    with patch("core.engine.foresight.fork_planner.fork_and_compare", AsyncMock(side_effect=RuntimeError("boom"))):
        out = await ace_fork_reasoning("reasoning_run:abc", 2)
    assert "error" in out
    assert "boom" in out["error"]


@pytest.mark.asyncio
async def test_ace_fork_reasoning_is_registered_on_server():
    """Reachability guard: the tool must be REGISTERED with the MCP server (a wrapper exists +
    delegates), not just defined in tools.py — the 'orphan MCP tool' failure mode."""
    from core.engine.mcp import server

    assert hasattr(server, "ace_fork_reasoning"), "ace_fork_reasoning wrapper missing from server.py"
    tools = await server.mcp.list_tools()
    names = {getattr(t, "name", None) for t in tools}
    assert "ace_fork_reasoning" in names, (
        f"ace_fork_reasoning not registered with mcp; got {sorted(n for n in names if n)}"
    )


@pytest.mark.asyncio
async def test_ace_fork_reasoning_resolves_conclusion_checkpoint_on_zero():
    """checkpoint_seq<=0 means 'fork the conclusion' — resolve_conclusion_checkpoint is consulted and
    its result is what fork_and_compare receives (not 0)."""
    from core.engine.mcp.tools import ace_fork_reasoning

    with (
        patch("core.engine.foresight.fork_planner.resolve_conclusion_checkpoint", AsyncMock(return_value=4)) as resolve,
        patch("core.engine.foresight.fork_planner.fork_and_compare", AsyncMock(return_value=_result())) as fac,
    ):
        out = await ace_fork_reasoning("reasoning_run:abc", 0)
    resolve.assert_awaited_once()
    assert fac.call_args.args[1] == 4  # resolved checkpoint, not 0
    assert out["recommendation"] == "fork"
