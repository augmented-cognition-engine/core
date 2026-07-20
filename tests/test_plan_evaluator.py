# tests/test_plan_evaluator.py
"""Tests for PlanEvaluator — LLM-based plan quality scorer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_units(n: int = 2):
    from core.engine.product.smart_decompose import WorkUnit

    return [
        WorkUnit(
            id=f"unit-{i}",
            title=f"Task {i}",
            description=f"Do thing {i}",
            archetype="creator",
            mode="deliberative",
        )
        for i in range(1, n + 1)
    ]


_SPEC = {"objective": "Add rate limiting", "acceptance_criteria": [], "constraints": []}


@pytest.mark.asyncio
async def test_plan_evaluator_returns_score():
    """Primary LLM call produces score."""
    from pydantic import BaseModel, Field

    class FakeScore(BaseModel):
        score: float = Field(default=0.8)
        reasoning: str = Field(default="Good plan")

    with patch("core.engine.cognition.plan_evaluator.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.complete_structured = AsyncMock(return_value=FakeScore())
        mock_get_llm.return_value = mock_llm
        with patch("core.engine.cognition.plan_evaluator.settings") as mock_settings:
            mock_settings.llm_budget_model = "claude-haiku-4-5-20251001"

            from core.engine.cognition.plan_evaluator import PlanEvaluator

            evaluator = PlanEvaluator()
            score = await evaluator.evaluate(_SPEC, _make_units())

    assert score == pytest.approx(0.8)
    mock_llm.complete_structured.assert_called_once()


@pytest.mark.asyncio
async def test_plan_evaluator_returns_0_5_on_failure():
    """LLM error → 0.5."""
    with patch("core.engine.cognition.plan_evaluator.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.complete_structured = AsyncMock(side_effect=RuntimeError("LLM down"))
        mock_get_llm.return_value = mock_llm
        with patch("core.engine.cognition.plan_evaluator.settings"):
            from core.engine.cognition.plan_evaluator import PlanEvaluator

            evaluator = PlanEvaluator()
            score = await evaluator.evaluate(_SPEC, _make_units())

    assert score == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_plan_evaluator_self_consistency_on_close_call():
    """Sentinel: close-call score triggers self-consistency, not advisor escalation.

    Contract: 3 total calls to budget_model (primary + 2 self-consistency), all to the
    same model. Score is averaged. No Opus/Sonnet escalation.
    """
    from pydantic import BaseModel, Field

    class FakeScore(BaseModel):
        score: float = Field(default=0.5)
        reasoning: str = Field(default="Uncertain")

    call_models: list[str] = []

    async def capture_call(prompt, schema, model=None, **kwargs):
        call_models.append(model or "default")
        return FakeScore()

    with (
        patch("core.engine.cognition.plan_evaluator.get_llm") as mock_get_llm,
        patch("core.engine.cognition.self_consistency.get_llm") as mock_sc_llm,
    ):
        mock_llm = MagicMock()
        mock_llm.complete_structured = capture_call
        mock_get_llm.return_value = mock_llm
        mock_sc_llm.return_value = mock_llm

        with patch("core.engine.cognition.plan_evaluator.settings") as mock_settings:
            mock_settings.llm_budget_model = "claude-haiku-4-5-20251001"

            from core.engine.cognition.plan_evaluator import PlanEvaluator

            evaluator = PlanEvaluator()
            score = await evaluator.evaluate(_SPEC, _make_units())

    # 3 total calls, all to budget model
    assert len(call_models) == 3, f"Expected 3 self-consistency calls, got {len(call_models)}"
    for m in call_models:
        assert m == "claude-haiku-4-5-20251001", f"Call went to {m!r} — must stay on budget model"

    # Score is average of 3×0.5 = 0.5
    assert score == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_plan_evaluator_skips_self_consistency_on_high_confidence():
    """Score > 0.65 → no extra samples drawn."""
    from pydantic import BaseModel, Field

    class FakeScore(BaseModel):
        score: float = Field(default=0.9)
        reasoning: str = Field(default="Excellent")

    with patch("core.engine.cognition.plan_evaluator.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.complete_structured = AsyncMock(return_value=FakeScore())
        mock_get_llm.return_value = mock_llm
        with patch("core.engine.cognition.plan_evaluator.settings") as mock_settings:
            mock_settings.llm_budget_model = "claude-haiku-4-5-20251001"

            from core.engine.cognition.plan_evaluator import PlanEvaluator

            evaluator = PlanEvaluator(advisor_model="claude-opus-4-6")
            score = await evaluator.evaluate(_SPEC, _make_units())

    assert score == pytest.approx(0.9)
    assert mock_llm.complete_structured.call_count == 1  # no extra samples


@pytest.mark.asyncio
async def test_plan_evaluator_advisor_model_ignored():
    """advisor_model= accepted for backward compat but ignored."""
    from pydantic import BaseModel, Field

    class FakeScore(BaseModel):
        score: float = Field(default=0.5)
        reasoning: str = Field(default="Uncertain")

    call_models: list[str] = []

    async def capture_call(prompt, schema, model=None, **kwargs):
        call_models.append(model or "default")
        return FakeScore()

    with (
        patch("core.engine.cognition.plan_evaluator.get_llm") as mock_get_llm,
        patch("core.engine.cognition.self_consistency.get_llm") as mock_sc_llm,
    ):
        mock_llm = MagicMock()
        mock_llm.complete_structured = capture_call
        mock_get_llm.return_value = mock_llm
        mock_sc_llm.return_value = mock_llm

        with patch("core.engine.cognition.plan_evaluator.settings") as mock_settings:
            mock_settings.llm_budget_model = "claude-haiku-4-5-20251001"

            from core.engine.cognition.plan_evaluator import PlanEvaluator

            evaluator = PlanEvaluator(advisor_model="claude-opus-4-6")
            await evaluator.evaluate(_SPEC, _make_units())

    assert "claude-opus-4-6" not in call_models, (
        "Opus called despite being deprecated — self-consistency must replace it"
    )
