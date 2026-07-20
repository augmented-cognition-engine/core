# tests/test_synthetic_runner.py
"""Tests for synthetic task runner and scoring."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_run_synthetic_task():
    """run_synthetic_task calls LLM with intelligence context and returns (output, tokens) tuple."""
    from core.engine.intelligence.synthetic_runner import run_synthetic_task

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="Here is the solution using React components...")

    output, tokens = await run_synthetic_task(
        task_desc="Build a button component",
        intelligence_context="## Intelligence\n- Use TypeScript\n- Follow accessibility guidelines",
        domain="ux",
        llm=mock_llm,
    )

    assert "solution" in output.lower()
    assert isinstance(tokens, int)
    mock_llm.complete.assert_called_once()


@pytest.mark.asyncio
async def test_score_output_weighted():
    """score_output applies 4 weighted criteria correctly."""
    from core.engine.intelligence.synthetic_runner import score_output

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "patterns_followed": 0.8,
            "correct_complete": 0.9,
            "anti_patterns_avoided": 0.7,
            "conventions_used": 0.6,
        }
    )

    score = await score_output(
        task_desc="Build button",
        output="A React button component...",
        quality_signals=["Uses TypeScript", "Has aria labels"],
        llm=mock_llm,
    )

    # 0.8*0.3 + 0.9*0.3 + 0.7*0.2 + 0.6*0.2 = 0.24+0.27+0.14+0.12 = 0.77
    assert score == pytest.approx(0.77, abs=0.01)


@pytest.mark.asyncio
async def test_score_output_clamps_values():
    """Scores outside 0-1 are clamped."""
    from core.engine.intelligence.synthetic_runner import score_output

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "patterns_followed": 1.5,  # above 1.0
            "correct_complete": -0.2,  # below 0.0
            "anti_patterns_avoided": 0.5,
            "conventions_used": 0.5,
        }
    )

    score = await score_output("task", "output", ["signal"], llm=mock_llm)

    # 1.0*0.3 + 0.0*0.3 + 0.5*0.2 + 0.5*0.2 = 0.3+0+0.1+0.1 = 0.5
    assert score == pytest.approx(0.5, abs=0.01)


@pytest.mark.asyncio
async def test_score_output_handles_failure():
    """LLM failure returns default 0.5."""
    from core.engine.intelligence.synthetic_runner import score_output

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(side_effect=Exception("LLM error"))

    score = await score_output("task", "output", ["signal"], llm=mock_llm)
    assert score == 0.5
