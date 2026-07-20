# tests/cognition/test_egr_executor.py
import json

import pytest

from core.engine.cognition.multiphase import MultiPhaseExecutor
from core.engine.cognition.phase_evaluator import EvaluationResult


def _low(text):  # confidence below the 0.6 gate so Wave 5 engages
    return json.dumps({"output": text, "confidence": 0.3, "evidence": [], "gaps": ["g"]})


class _Phase:
    def __init__(self, fn="choose"):
        self.cognitive_function = fn
        self.must_not = []
        self.must_verify = []
        self.load_context = None
        self.capture_as = None


class _Composition:
    def __init__(self, fn="choose"):
        self.active_phases = [_Phase(fn)]
        self.prompt_sections = [{}]
        self.fusion_mode = False
        self.depth = 3


class _ScriptedLLM:
    """Returns queued outputs in order across all _llm_call invocations."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = []

    async def __call__(self, system_prompt, user_prompt):
        self.calls.append(user_prompt)
        return self._outputs.pop(0) if self._outputs else _low("default")


class _Evaluator:
    """Scores by output content; carries violations until a 'fixed' output appears."""

    def __init__(self, score_map, violations_map):
        self.score_map = score_map
        self.violations_map = violations_map

    async def evaluate(self, description, phase_output, phase):
        key = phase_output.output
        return EvaluationResult(
            score=self.score_map.get(key, 0.4),
            reasoning="stub",
            violated_constraints=self.violations_map.get(key, []),
        )


@pytest.mark.asyncio
async def test_refine_accepts_improving_revision_and_uses_evaluator_violations():
    # initial 'v1' has a violation + low score; revision 'v2' clears it + higher score.
    llm = _ScriptedLLM([_low("v1"), _low("v2")])
    ev = _Evaluator(score_map={"v1": 0.4, "v2": 0.85}, violations_map={"v1": ["must cite source"], "v2": []})
    ex = MultiPhaseExecutor(llm_call=llm, phase_evaluator=ev, branch_count=1, self_refine_rounds=2)

    out = await ex.execute(description="decide", composition=_Composition("choose"), framework_prompts={})

    assert json.loads(out)["output"] == "v2"  # improvement accepted
    tr = ex._last_trace[0]
    assert tr["self_refined"] is True
    assert tr["refine_rounds"] == 1
    assert tr["violations_before"] == 1 and tr["violations_after"] == 0
    # the revise prompt was grounded in the evaluator's named violation
    assert any("must cite source" in c for c in llm.calls)


@pytest.mark.asyncio
async def test_refine_rejects_regressing_revision_keeps_prior():
    # revision 'v2' scores LOWER than 'v1' → non-regression guard rejects it.
    llm = _ScriptedLLM([_low("v1"), _low("v2")])
    ev = _Evaluator(score_map={"v1": 0.5, "v2": 0.2}, violations_map={"v1": ["x"], "v2": ["x"]})
    ex = MultiPhaseExecutor(llm_call=llm, phase_evaluator=ev, branch_count=1, self_refine_rounds=2)

    out = await ex.execute(description="decide", composition=_Composition("choose"), framework_prompts={})

    assert json.loads(out)["output"] == "v1"  # prior kept, regression rejected
    assert ex._last_trace[0].get("self_refined") is False  # no accepted round


@pytest.mark.asyncio
async def test_refine_early_stops_when_verifier_satisfied():
    # 'v1' has no violations and (to force the gate-not-firing branch) high confidence on re-check.
    # Use a high-confidence initial so should_retrieve is False after the seed eval → no revise call.
    high = json.dumps({"output": "v1", "confidence": 0.95, "evidence": ["e"], "gaps": []})
    llm = _ScriptedLLM([high, _low("should-not-be-used")])
    ev = _Evaluator(score_map={"v1": 0.9}, violations_map={"v1": []})
    ex = MultiPhaseExecutor(llm_call=llm, phase_evaluator=ev, branch_count=1, self_refine_rounds=2)

    await ex.execute(description="decide", composition=_Composition("choose"), framework_prompts={})
    # only the initial generation call happened — no revise (verifier satisfied / gate didn't fire)
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_refine_low_confidence_no_violations_uses_strengthen_instruction():
    # Gate fires (low confidence) but the evaluator names NO violations → the revise
    # prompt must use the "strengthen the weakest, least-evidenced claims" instruction
    # (not a violation list), and the improving revision is still accepted per the guard.
    llm = _ScriptedLLM([_low("v1"), _low("v2")])
    ev = _Evaluator(score_map={"v1": 0.4, "v2": 0.7}, violations_map={"v1": [], "v2": []})
    ex = MultiPhaseExecutor(llm_call=llm, phase_evaluator=ev, branch_count=1, self_refine_rounds=2)

    out = await ex.execute(description="decide", composition=_Composition("choose"), framework_prompts={})

    # The revise prompt used the low-confidence strengthen instruction, not a violation list.
    revise_calls = [c for c in llm.calls if "Your previous output:" in c]
    assert revise_calls, "expected at least one revise call"
    assert any("strengthen the weakest, least-evidenced claims" in c.lower() for c in revise_calls)
    assert not any("constraint violations" in c.lower() for c in revise_calls)
    # The improving revision (0.7 >= 0.4) is accepted per the non-regression guard.
    assert json.loads(out)["output"] == "v2"
    tr = ex._last_trace[0]
    assert tr["self_refined"] is True
    assert tr["violations_before"] == 0 and tr["violations_after"] == 0


@pytest.mark.asyncio
async def test_refine_off_when_no_evaluator_or_zero_rounds():
    llm = _ScriptedLLM([_low("v1")])
    ex = MultiPhaseExecutor(llm_call=llm, phase_evaluator=None, self_refine_rounds=2)
    await ex.execute(description="d", composition=_Composition("choose"), framework_prompts={})
    assert ex._last_trace[0].get("self_refined") is False
    assert len(llm.calls) == 1  # no refinement without the grounding evaluator
