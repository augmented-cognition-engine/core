# tests/cognition/test_multiphase_on_phase.py
import json

import pytest

from core.engine.cognition.models import CognitiveComposition, RecipePhase
from core.engine.cognition.multiphase import MultiPhaseExecutor


def _phase(fn: str) -> RecipePhase:
    return RecipePhase(cognitive_function=fn, instruments=[], min_depth=1, output_schema="x")


def _composition() -> CognitiveComposition:
    return CognitiveComposition(
        meta_skills=["strategic_intelligence"],
        depth=3,
        active_phases=[_phase("frame"), _phase("prioritize")],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=False,
    )


@pytest.mark.unit
async def test_on_phase_fires_once_per_active_phase():
    seen = []

    async def on_phase(phase_idx, total_phases, cognitive_function, output, confidence, gaps):
        seen.append((phase_idx, total_phases, cognitive_function, output, confidence))

    async def fake_llm(system_prompt, user_prompt):
        return json.dumps({"output": "ok", "confidence": 0.7, "evidence": [], "gaps": []})

    ex = MultiPhaseExecutor(llm_call=fake_llm, on_phase=on_phase)
    await ex.execute(description="t", composition=_composition(), framework_prompts={})

    assert [s[0] for s in seen] == [0, 1]
    assert [s[2] for s in seen] == ["frame", "prioritize"]
    assert seen[0][1] == 2  # total_phases
    assert seen[0][4] == 0.7  # confidence parsed from PhaseOutput
