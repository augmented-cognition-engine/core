# tests/test_cognition_fusion.py
import logging

import pytest

from core.engine.cognition.fusion import FALLBACK_SENTINEL, PromptFusion
from core.engine.cognition.models import CognitiveComposition, InstrumentSpec, RecipePhase


def _make_composition(depth: int, functions: list[str]) -> CognitiveComposition:
    phases = [
        RecipePhase(
            cognitive_function=fn,
            instruments=[InstrumentSpec(slug="first-principles", fallback_slug="mece")],
            min_depth=1,
            output_schema=f"{fn}_output",
            pattern="solo",
        )
        for fn in functions
    ]
    sections = [
        {
            "phase_idx": str(i),
            "cognitive_function": fn,
            "framework_slugs": ["first-principles"],
            "output_schema": f"{fn}_output",
            "pattern": "solo",
            "fusion_label": f"[{fn.upper()}]",
        }
        for i, fn in enumerate(functions)
    ]
    return CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=depth,
        active_phases=phases,
        resolved_instruments={str(i): ["first-principles"] for i in range(len(phases))},
        prompt_sections=sections,
        fusion_mode=depth <= 2,
    )


def test_fuse_returns_string():
    comp = _make_composition(1, ["frame", "prioritize"])
    result = PromptFusion().fuse(comp, framework_prompts={})
    assert isinstance(result, str)


def test_fuse_includes_all_phase_labels():
    comp = _make_composition(1, ["frame", "prioritize", "choose"])
    result = PromptFusion().fuse(comp, framework_prompts={})
    assert "[FRAME]" in result
    assert "[PRIORITIZE]" in result
    assert "[CHOOSE]" in result


def test_fuse_empty_composition_returns_empty():
    comp = CognitiveComposition(
        meta_skills=[],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    result = PromptFusion().fuse(comp, framework_prompts={})
    assert result == ""


def test_fuse_includes_framework_prompt_when_available():
    comp = _make_composition(1, ["frame"])
    framework_prompts = {"first-principles": "Apply first principles: ..."}
    result = PromptFusion().fuse(comp, framework_prompts=framework_prompts)
    assert "Apply first principles" in result
    assert "Apply frame reasoning to structure your thinking here." not in result


def test_fuse_includes_output_schema():
    comp = _make_composition(1, ["frame"])
    result = PromptFusion().fuse(comp, framework_prompts={})
    assert "frame_output" in result


def test_fuse_phases_appear_in_order():
    comp = _make_composition(1, ["frame", "prioritize", "critique"])
    result = PromptFusion().fuse(comp, framework_prompts={})
    frame_pos = result.index("[FRAME]")
    prioritize_pos = result.index("[PRIORITIZE]")
    critique_pos = result.index("[CRITIQUE]")
    assert frame_pos < prioritize_pos < critique_pos


def _make_composition_with_constraints(must_not=None, must_verify=None) -> CognitiveComposition:
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[InstrumentSpec(fallback_slug="first-principles")],
        min_depth=1,
        output_schema="real_constraints",
        must_not=must_not or [],
        must_verify=must_verify or [],
    )
    return CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=1,
        active_phases=[phase],
        resolved_instruments={"0": ["first-principles"]},
        prompt_sections=[
            {
                "phase_idx": "0",
                "cognitive_function": "frame",
                "framework_slugs": ["first-principles"],
                "output_schema": "real_constraints",
                "pattern": "solo",
                "fusion_label": "[FRAME]",
            }
        ],
        fusion_mode=True,
    )


def test_fusion_injects_phase_output_schema():
    composition = _make_composition_with_constraints()
    result = PromptFusion().fuse(composition, {})
    assert "confidence" in result
    assert "evidence" in result
    assert "gaps" in result


def test_fusion_injects_must_not_constraints():
    composition = _make_composition_with_constraints(must_not=["propose solutions before constraints"])
    result = PromptFusion().fuse(composition, {})
    assert "MUST NOT" in result
    assert "propose solutions before constraints" in result


def test_fusion_injects_must_verify():
    composition = _make_composition_with_constraints(must_verify=["hot path is actually hot"])
    result = PromptFusion().fuse(composition, {})
    assert "MUST VERIFY" in result
    assert "hot path is actually hot" in result


def test_fusion_skips_empty_constraints():
    composition = _make_composition_with_constraints()
    result = PromptFusion().fuse(composition, {})
    assert "MUST NOT" not in result
    assert "MUST VERIFY" not in result


# ── Sentinel boundary tests ────────────────────────────────────────────────────
# FALLBACK_SENTINEL must be ABSENT whenever real framework prompts are supplied.
# If it appears, framework content failed to load — this is a critical quality gate.

DEMO_PROMPT = (
    "When I encounter a problem that resists clear analysis, the first thing I do is ask: "
    "what is the complete space? I'm not looking for the answer yet — I'm building the map. "
    "I draw a boundary around the system and enumerate what lives inside it."
)


@pytest.mark.parametrize(
    "cognitive_function",
    ["frame", "prioritize", "critique", "choose", "synthesize", "evaluate"],
)
def test_sentinel_absent_when_framework_prompt_provided(cognitive_function: str):
    """Sentinel must not appear when framework_prompts covers the slugs in use."""
    comp = _make_composition(1, [cognitive_function])
    result = PromptFusion().fuse(comp, framework_prompts={"first-principles": DEMO_PROMPT})
    assert FALLBACK_SENTINEL not in result, (
        f"Fallback sentinel fired for cognitive_function={cognitive_function!r} "
        "even though framework_prompts was populated. "
        "Check that framework_slugs in prompt_sections match keys in framework_prompts."
    )


def test_sentinel_present_when_no_framework_prompt():
    """Sentinel fires (and documents expected fallback behaviour) when prompts are absent."""
    comp = _make_composition(1, ["frame"])
    result = PromptFusion().fuse(comp, framework_prompts={})
    assert FALLBACK_SENTINEL in result


def test_sentinel_absent_when_any_slug_matches():
    """If a phase lists multiple slugs and at least one resolves, no sentinel fires."""
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[
            InstrumentSpec(slug="missing-slug", fallback_slug="first-principles"),
        ],
        min_depth=1,
        output_schema="frame_output",
    )
    comp = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=1,
        active_phases=[phase],
        resolved_instruments={"0": ["missing-slug", "first-principles"]},
        prompt_sections=[
            {
                "phase_idx": "0",
                "cognitive_function": "frame",
                "framework_slugs": ["missing-slug", "first-principles"],
                "output_schema": "frame_output",
                "pattern": "solo",
                "fusion_label": "[FRAME]",
            }
        ],
        fusion_mode=True,
    )
    # Only the second slug resolves — sentinel must still be absent.
    result = PromptFusion().fuse(comp, framework_prompts={"first-principles": DEMO_PROMPT})
    assert FALLBACK_SENTINEL not in result


def test_sentinel_triggers_warning_log(caplog):
    """Fallback must emit a WARNING so ops can detect framework loading failures in logs."""
    comp = _make_composition(1, ["frame"])
    with caplog.at_level(logging.WARNING, logger="core.engine.cognition.fusion"):
        PromptFusion().fuse(comp, framework_prompts={})
    assert any("PromptFusion fallback fired" in r.message for r in caplog.records), (
        "Expected a WARNING log from PromptFusion when framework_prompts is empty"
    )


def test_sentinel_no_warning_when_prompt_resolved(caplog):
    """No WARNING should be emitted when framework content loads successfully."""
    comp = _make_composition(1, ["frame"])
    with caplog.at_level(logging.WARNING, logger="core.engine.cognition.fusion"):
        PromptFusion().fuse(comp, framework_prompts={"first-principles": DEMO_PROMPT})
    assert not any("PromptFusion fallback fired" in r.message for r in caplog.records)
