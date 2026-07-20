from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.cognition.models import InstrumentSpec, RecipePhase
from core.engine.cognition.phase_evaluator import EvaluationResult, PhaseEvaluator
from core.engine.cognition.phase_output import PhaseOutput


def _make_phase(must_not=None, must_verify=None) -> RecipePhase:
    return RecipePhase(
        cognitive_function="frame",
        instruments=[InstrumentSpec(fallback_slug="fp")],
        min_depth=3,
        output_schema="constraints",
        must_not=must_not or [],
        must_verify=must_verify or [],
    )


def _make_po(output: str = "analysis result", confidence: float = 0.7) -> PhaseOutput:
    return PhaseOutput(output=output, confidence=confidence, evidence=["fact A"], gaps=[])


@pytest.mark.asyncio
async def test_evaluator_returns_float_between_0_and_1():
    """evaluate() returns EvaluationResult with score in [0, 1]."""
    mock_llm = MagicMock()
    mock_llm.complete_structured = AsyncMock(return_value=EvaluationResult(score=0.75, reasoning="solid output"))
    with patch("core.engine.cognition.phase_evaluator.get_llm", return_value=mock_llm):
        evaluator = PhaseEvaluator()
        result = await evaluator.evaluate("build cache", _make_po(), _make_phase())
    assert 0.0 <= result.score <= 1.0
    assert result.score == 0.75


@pytest.mark.asyncio
async def test_evaluator_returns_neutral_on_llm_error():
    """evaluate() returns neutral EvaluationResult (score=0.5) on any LLM exception — never raises."""
    with patch("core.engine.cognition.phase_evaluator.get_llm", side_effect=RuntimeError("boom")):
        evaluator = PhaseEvaluator()
        result = await evaluator.evaluate("task", _make_po(), _make_phase())
    assert result.score == 0.5
    assert result.reasoning == "evaluation error"


# --- Phase 0: self-consistency disagreement discount on close calls -----------


@pytest.mark.asyncio
async def test_close_call_discounts_score_on_high_disagreement():
    """A close-call where the 3 samples disagree is scored lower (honest) and the
    disagreement is surfaced — the spread is no longer discarded."""
    mock_llm = MagicMock()
    mock_llm.complete_structured = AsyncMock(return_value=EvaluationResult(score=0.5, reasoning="primary"))
    samples = [EvaluationResult(score=0.2, reasoning="a"), EvaluationResult(score=0.8, reasoning="b")]
    with (
        patch("core.engine.cognition.phase_evaluator.get_llm", return_value=mock_llm),
        patch("core.engine.cognition.phase_evaluator.sample_structured", AsyncMock(return_value=samples)),
    ):
        result = await PhaseEvaluator().evaluate("task", _make_po(confidence=0.5), _make_phase())
    # avg(0.5, 0.2, 0.8) = 0.5 ; disagreement = 0.8 - 0.2 = 0.6 ; discount = 0.5*(1 - 0.2*0.6) = 0.44
    assert result.disagreement == pytest.approx(0.6)
    assert result.score == pytest.approx(0.44, abs=1e-3)
    assert result.score < 0.5


@pytest.mark.asyncio
async def test_agreeing_close_call_is_not_discounted():
    """When the 3 samples agree, disagreement is 0 and the score is the plain average."""
    mock_llm = MagicMock()
    mock_llm.complete_structured = AsyncMock(return_value=EvaluationResult(score=0.5, reasoning="primary"))
    samples = [EvaluationResult(score=0.5, reasoning="a"), EvaluationResult(score=0.5, reasoning="b")]
    with (
        patch("core.engine.cognition.phase_evaluator.get_llm", return_value=mock_llm),
        patch("core.engine.cognition.phase_evaluator.sample_structured", AsyncMock(return_value=samples)),
    ):
        result = await PhaseEvaluator().evaluate("task", _make_po(confidence=0.5), _make_phase())
    assert result.disagreement == 0.0
    assert result.score == pytest.approx(0.5, abs=1e-3)


@pytest.mark.asyncio
async def test_evaluator_prompt_includes_must_not():
    """must_not constraints must appear in the prompt sent to the LLM."""
    captured_prompt: list[str] = []
    mock_llm = MagicMock()

    async def capture_call(prompt, schema, **kwargs):
        captured_prompt.append(prompt)
        return EvaluationResult(score=0.5, reasoning="ok")

    mock_llm.complete_structured = capture_call
    with patch("core.engine.cognition.phase_evaluator.get_llm", return_value=mock_llm):
        evaluator = PhaseEvaluator()
        phase = _make_phase(must_not=["propose solutions before constraints", "skip edge cases"])
        await evaluator.evaluate("build a cache", _make_po(), phase)

    assert len(captured_prompt) >= 1
    assert "propose solutions before constraints" in captured_prompt[0]
    assert "skip edge cases" in captured_prompt[0]


@pytest.mark.asyncio
async def test_evaluator_prompt_includes_must_verify():
    """must_verify constraints must appear in the prompt sent to the LLM."""
    captured_prompt: list[str] = []
    mock_llm = MagicMock()

    async def capture_call(prompt, schema, **kwargs):
        captured_prompt.append(prompt)
        return EvaluationResult(score=0.8, reasoning="ok")

    mock_llm.complete_structured = capture_call
    with patch("core.engine.cognition.phase_evaluator.get_llm", return_value=mock_llm):
        evaluator = PhaseEvaluator()
        phase = _make_phase(must_verify=["hot path is actually measured", "failure mode is named"])
        await evaluator.evaluate("design the system", _make_po(), phase)

    assert "hot path is actually measured" in captured_prompt[0]
    assert "failure mode is named" in captured_prompt[0]


@pytest.mark.asyncio
async def test_self_consistency_fires_on_close_call():
    """Sentinel: when primary score is in [0.35, 0.65], self-consistency runs extra samples.

    Contract: 3 total calls to budget_model (primary + 2 self-consistency), all to the
    same model. Score is averaged across samples. No advisor model escalation.
    """
    call_models: list[str] = []
    mock_llm = MagicMock()

    async def capture_call(prompt, schema, model=None, **kwargs):
        call_models.append(model or "default")
        # All three samples return a score close to 0.5 (all in close-call zone)
        return EvaluationResult(score=0.5, reasoning="borderline")

    mock_llm.complete_structured = capture_call

    with (
        patch("core.engine.cognition.phase_evaluator.get_llm", return_value=mock_llm),
        patch("core.engine.cognition.self_consistency.get_llm", return_value=mock_llm),
    ):
        evaluator = PhaseEvaluator()
        result = await evaluator.evaluate("build cache", _make_po(), _make_phase())

    # 3 total calls: primary + 2 self-consistency samples
    assert len(call_models) == 3, f"Expected 3 calls, got {len(call_models)}"

    # All calls use budget model (Haiku) — no escalation
    from core.engine.core.config import settings

    for model in call_models:
        assert model == settings.llm_budget_model, (
            f"Self-consistency called model {model!r} instead of budget_model — "
            "Opus/Sonnet escalation must not fire in close-call zone"
        )

    # Averaged score and self-consistency label in reasoning
    assert "self-consistency" in result.reasoning


@pytest.mark.asyncio
async def test_self_consistency_not_called_on_clear_score():
    """When primary score is outside [0.35, 0.65], no extra samples are drawn."""
    call_count = 0
    mock_llm = MagicMock()

    async def count_call(prompt, schema, **kwargs):
        nonlocal call_count
        call_count += 1
        return EvaluationResult(score=0.9, reasoning="clear pass")

    mock_llm.complete_structured = count_call
    with patch("core.engine.cognition.phase_evaluator.get_llm", return_value=mock_llm):
        evaluator = PhaseEvaluator()
        result = await evaluator.evaluate("build cache", _make_po(), _make_phase())

    assert call_count == 1, (
        f"Expected 1 call, got {call_count} — self-consistency must not fire outside close-call zone"
    )
    assert result.score == 0.9


@pytest.mark.asyncio
async def test_advisor_model_param_is_accepted_but_ignored():
    """advisor_model= param accepted for backward compat — self-consistency used regardless."""
    call_models: list[str] = []
    mock_llm = MagicMock()

    async def capture_call(prompt, schema, model=None, **kwargs):
        call_models.append(model or "default")
        return EvaluationResult(score=0.5, reasoning="borderline")

    mock_llm.complete_structured = capture_call

    with (
        patch("core.engine.cognition.phase_evaluator.get_llm", return_value=mock_llm),
        patch("core.engine.cognition.self_consistency.get_llm", return_value=mock_llm),
    ):
        # Pass advisor_model=Opus — must be ignored; all calls go to budget_model
        evaluator = PhaseEvaluator(advisor_model="claude-opus-4-6")
        await evaluator.evaluate("build cache", _make_po(), _make_phase())

    assert "claude-opus-4-6" not in call_models, (
        "Opus was called despite advisor_model being deprecated — self-consistency must replace it"
    )
