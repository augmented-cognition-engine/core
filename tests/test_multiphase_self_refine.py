# tests/test_multiphase_self_refine.py
"""Tests for Wave 5 EVALUATOR-GUIDED REFINEMENT loop in MultiPhaseExecutor.

The old naive self-critique path (critique call → suggestions → revise unconditionally)
has been replaced with evaluator-guided refinement: revise against the evaluator's named
violated_constraints; accept a revision ONLY if the evaluator scores it no worse than
the prior (non-regression guard → monotonic). Wave 5 requires the evaluator; without it
the block is skipped entirely (no naive fallback).
"""

import json

import pytest

from core.engine.cognition.models import CognitiveComposition, InstrumentSpec, RecipePhase
from core.engine.cognition.phase_evaluator import EvaluationResult
from core.engine.cognition.phase_output import PhaseOutput


def _make_composition():
    return CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=3,
        active_phases=[
            RecipePhase(
                cognitive_function="analysis",
                instruments=[InstrumentSpec(fallback_slug="mece")],
                min_depth=1,
                output_schema="analysis",
                must_not=[],
                must_verify=[],
            )
        ],
        resolved_instruments={},
        prompt_sections=[{"framework_slugs": [], "output_schema": "analysis", "fusion_label": "[ANALYSIS]"}],
        fusion_mode=False,
    )


def _po(confidence: float, gaps: list = None, output: str = "result") -> str:
    po = PhaseOutput(output=output, confidence=confidence, evidence=[], gaps=gaps or [])
    return json.dumps(po.model_dump())


class _Evaluator:
    """Simple scripted evaluator: scores by exact output text."""

    def __init__(self, score_map, violations_map=None):
        self.score_map = score_map
        self.violations_map = violations_map or {}

    async def evaluate(self, description, phase_output, phase):
        key = phase_output.output
        return EvaluationResult(
            score=self.score_map.get(key, 0.4),
            reasoning="stub",
            violated_constraints=self.violations_map.get(key, ["needs-work"]),
        )


# test_self_refine_revises_when_gate_fires: low confidence + evaluator → revise → improved output accepted
@pytest.mark.asyncio
async def test_self_refine_revises_when_gate_fires():
    from core.engine.cognition.multiphase import MultiPhaseExecutor

    # Call sequence:
    # 1. Initial phase output (low confidence, output="result")
    # 2. Revision call → higher confidence output (output="refined")
    ev = _Evaluator(
        score_map={"result": 0.4, "refined": 0.85},
        violations_map={"result": ["add more detail"], "refined": []},
    )

    call_idx = 0
    responses = [
        _po(confidence=0.4, gaps=["missing edge cases"], output="result"),  # initial
        _po(confidence=0.85, output="refined"),  # revision
    ]

    async def llm_call(system, user):
        nonlocal call_idx
        r = responses[call_idx]
        call_idx += 1
        return r

    executor = MultiPhaseExecutor(llm_call=llm_call, phase_evaluator=ev, branch_count=1, self_refine_rounds=1)
    result = await executor.execute("describe the system", _make_composition(), {})

    assert call_idx == 2  # initial + revision (no separate critique call)
    assert executor._last_trace[0].get("self_refined") is True
    assert executor._last_trace[0].get("refine_rounds") == 1
    assert json.loads(result)["output"] == "refined"


# test_self_refine_skips_when_gate_does_not_fire: high confidence → Wave 5 never enters refine loop
@pytest.mark.asyncio
async def test_self_refine_skips_when_gate_does_not_fire():
    from core.engine.cognition.multiphase import MultiPhaseExecutor

    ev = _Evaluator(score_map={"result": 0.9}, violations_map={"result": []})

    call_count = 0

    async def llm_call(system, user):
        nonlocal call_count
        call_count += 1
        return _po(confidence=0.9)  # above threshold, no gaps

    executor = MultiPhaseExecutor(llm_call=llm_call, phase_evaluator=ev, branch_count=1, self_refine_rounds=3)
    await executor.execute("describe the system", _make_composition(), {})

    assert call_count == 1  # only the initial call
    assert executor._last_trace[0].get("self_refined", False) is False


# test_self_refine_not_fired_when_rounds_zero: self_refine_rounds=0 → no refinement calls
@pytest.mark.asyncio
async def test_self_refine_not_fired_when_rounds_zero():
    from core.engine.cognition.multiphase import MultiPhaseExecutor

    ev = _Evaluator(score_map={"result": 0.3}, violations_map={"result": ["violation"]})

    call_count = 0

    async def llm_call(system, user):
        nonlocal call_count
        call_count += 1
        return _po(confidence=0.3, gaps=["gap"])  # gate would fire

    executor = MultiPhaseExecutor(llm_call=llm_call, phase_evaluator=ev, branch_count=1, self_refine_rounds=0)
    await executor.execute("describe the system", _make_composition(), {})

    assert call_count == 1  # no critique, no revision
    assert executor._last_trace[0].get("self_refined", False) is False


# test_self_refine_not_fired_when_no_evaluator: evaluator=None → block skipped (no naive fallback)
@pytest.mark.asyncio
async def test_self_refine_not_fired_when_no_evaluator():
    from core.engine.cognition.multiphase import MultiPhaseExecutor

    call_count = 0

    async def llm_call(system, user):
        nonlocal call_count
        call_count += 1
        return _po(confidence=0.3, gaps=["gap"])  # gate would fire if evaluator were present

    executor = MultiPhaseExecutor(llm_call=llm_call, phase_evaluator=None, self_refine_rounds=2)
    await executor.execute("describe the system", _make_composition(), {})

    assert call_count == 1  # no refinement without the grounding evaluator
    assert executor._last_trace[0].get("self_refined") is False
