# tests/test_framework_executor.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.reasoning.executor import build_framework_context, execute_with_frameworks
from core.engine.reasoning.models import Framework, FrameworkSelection


def _fw(slug="test", family="diagnostic", prompt="Analyze this."):
    return Framework(slug=slug, name=slug, family=family, system_prompt=prompt)


def test_build_framework_context_single():
    sel = FrameworkSelection(frameworks=[_fw("fp")], composition_pattern="stacked")
    ctx = build_framework_context(sel)
    assert '<framework slug="fp"' in ctx
    assert "Analyze this." in ctx


def test_build_framework_context_multiple():
    sel = FrameworkSelection(frameworks=[_fw("a"), _fw("b")], composition_pattern="layered")
    ctx = build_framework_context(sel)
    assert 'priority="1"' in ctx
    assert 'priority="2"' in ctx


@pytest.mark.asyncio
async def test_stacked_single_call():
    fw = _fw("first-principles", prompt="Apply first principles...")
    sel = FrameworkSelection(frameworks=[fw], composition_pattern="stacked")

    with patch("core.engine.reasoning.executor.llm") as mock_llm:
        mock_llm.complete = AsyncMock(return_value="First principles analysis...")
        result = await execute_with_frameworks(sel, "Why is X happening?", "")

    assert result["composition_pattern"] == "stacked"
    assert result["output"] == "First principles analysis..."
    assert result["frameworks_used"] == ["first-principles"]
    mock_llm.complete.assert_called_once()


@pytest.mark.asyncio
async def test_layered_single_call():
    fws = [_fw("mece", prompt="Use MECE..."), _fw("rca", prompt="Root cause...")]
    sel = FrameworkSelection(frameworks=fws, composition_pattern="layered")

    with patch("core.engine.reasoning.executor.llm") as mock_llm:
        mock_llm.complete = AsyncMock(return_value="Layered analysis...")
        result = await execute_with_frameworks(sel, "Analyze problem", "")

    assert result["composition_pattern"] == "layered"
    assert len(result["frameworks_used"]) == 2
    mock_llm.complete.assert_called_once()


@pytest.mark.asyncio
async def test_iterative_generates_and_evaluates():
    gen = _fw("design-thinking", family="generative", prompt="Generate ideas...")
    evl = _fw("decision-matrix", family="evaluative", prompt="Evaluate options...")
    sel = FrameworkSelection(frameworks=[gen, evl], composition_pattern="iterative")

    call_count = 0

    async def mock_complete(prompt, model=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "Initial ideas: A, B, C"
        elif call_count == 2:
            return "Evaluation: A is strongest"
        elif call_count == 3:
            return "Refined: A with improvements"
        else:
            return "Final evaluation"

    with patch("core.engine.reasoning.executor.llm") as mock_llm:
        mock_llm.complete = mock_complete
        result = await execute_with_frameworks(sel, "Design a solution", "")

    assert result["composition_pattern"] == "iterative"
    assert len(result["per_framework_results"]) >= 3  # generate, evaluate, refine
    assert call_count >= 3
