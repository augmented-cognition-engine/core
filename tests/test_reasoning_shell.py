from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.intelligence.complexity_router import TIER_EXECUTOR, TIER_REVIEWER, ComplexityTier
from core.engine.intelligence.failure_classifier import FailureCategory
from core.engine.orchestration.shells.reasoning_shell import ReasoningShell, ReviewResult


@pytest.mark.asyncio
async def test_passes_on_first_try():
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value="def foo(): return 42")
    mock_llm.complete_structured = AsyncMock(return_value=ReviewResult(passed=True, confidence=0.95))
    shell = ReasoningShell(llm=mock_llm)
    result = await shell.run("write a function that returns 42", "coding", ComplexityTier.SIMPLE)
    assert result.output == "def foo(): return 42"
    assert len(result.passes) == 1
    assert not result.escalated
    assert mock_llm.complete.call_count == 1


@pytest.mark.asyncio
async def test_retries_on_failure():
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(side_effect=["bad output", "good output"])
    mock_llm.complete_structured = AsyncMock(
        side_effect=[
            ReviewResult(
                passed=False,
                confidence=0.3,
                failure_category=FailureCategory.INCOMPLETE_IMPL,
                issues=["missing return type"],
            ),
            ReviewResult(passed=True, confidence=0.9),
        ]
    )
    mock_clf = AsyncMock()
    shell = ReasoningShell(llm=mock_llm, failure_classifier=mock_clf)
    result = await shell.run("write a typed function", "coding", ComplexityTier.MODERATE)
    assert result.output == "good output"
    assert len(result.passes) == 2
    assert not result.escalated
    mock_clf.capture.assert_called_once()


@pytest.mark.asyncio
async def test_executor_and_reviewer_are_different_models():
    used_models: list[tuple] = []
    mock_llm = MagicMock()

    async def _complete(prompt, model=None, **kwargs):
        used_models.append(("complete", model))
        return "output"

    async def _complete_structured(prompt, schema, model=None, **kwargs):
        used_models.append(("structured", model))
        return ReviewResult(passed=True, confidence=0.9)

    mock_llm.complete = _complete
    mock_llm.complete_structured = _complete_structured
    shell = ReasoningShell(llm=mock_llm)
    await shell.run("task", "coding", ComplexityTier.SIMPLE)
    executor_model = next(m for kind, m in used_models if kind == "complete")
    reviewer_model = next(m for kind, m in used_models if kind == "structured")
    assert executor_model != reviewer_model
    assert executor_model == TIER_EXECUTOR[ComplexityTier.SIMPLE]
    assert reviewer_model == TIER_REVIEWER[ComplexityTier.SIMPLE]


@pytest.mark.asyncio
async def test_escalates_after_max_passes():
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value="output")
    mock_llm.complete_structured = AsyncMock(
        return_value=ReviewResult(passed=False, confidence=0.2, issues=["still wrong"])
    )
    mock_clf = AsyncMock()
    shell = ReasoningShell(llm=mock_llm, failure_classifier=mock_clf)
    result = await shell.run("hard task", "coding", ComplexityTier.MODERATE)
    assert result.escalated
    assert result.pass_count == 4  # 3 normal + 1 opus
