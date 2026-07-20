import pytest

from core.engine.orchestration import deep_committee as dc
from core.engine.orchestration.deep_committee import MAX_LENSES, resolve_lenses


@pytest.mark.unit
def test_focused_build_resolves_one_lens():
    lenses = resolve_lenses({"discipline": "architecture", "specialties": []})
    assert lenses == ["architecture"]


@pytest.mark.unit
def test_cross_cutting_build_resolves_multiple_distinct_lenses():
    lenses = resolve_lenses(
        {
            "discipline": "architecture",
            "specialties": ["security-hardening", "data-modeling"],
        }
    )
    # primary + distinct disciplines implied by specialties, deduped, capped
    assert lenses[0] == "architecture"
    assert "security" in lenses and "data" in lenses
    assert len(lenses) == len(set(lenses)) <= MAX_LENSES


@pytest.mark.unit
def test_dynamic_not_fixed():
    a = resolve_lenses({"discipline": "product_strategy", "specialties": []})
    b = resolve_lenses({"discipline": "architecture", "specialties": []})
    assert a != b  # composition depends on the problem


@pytest.mark.integration
async def test_run_deep_committee_runs_each_lens_deep_in_parallel(monkeypatch):
    calls = []

    async def _fake_run_reasoning(*, thought, classification, composition, product_id, model, on_phase):
        calls.append(classification["discipline"])
        if on_phase:
            await on_phase(0, 1, "frame", f"{classification['discipline']} framing", 0.8, [])
        from core.engine.cognition.reasoning_run import ReasoningResult

        return ReasoningResult(
            conclusion=f"{classification['discipline']} conclusion",
            phases=[{"cognitive_function": "frame", "output": "x", "confidence": 0.8}],
        )

    async def _fake_compose(classification, product_id):
        from core.engine.cognition.models import CognitiveComposition, RecipePhase

        return CognitiveComposition(
            meta_skills=[classification["discipline"]],
            depth=3,
            active_phases=[RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")],
            resolved_instruments={},
            prompt_sections=[],
            fusion_mode=False,
        )

    monkeypatch.setattr(dc, "run_reasoning", _fake_run_reasoning)
    monkeypatch.setattr(dc, "_compose_for_lens", _fake_compose, raising=False)

    phase_events = []

    async def _on_event(et, payload):
        phase_events.append(et)

    result = await dc.run_deep_committee(
        "redesign the importer",
        ["architecture", "data"],
        "product:platform",
        event_callback=_on_event,
    )
    assert set(calls) == {"architecture", "data"}  # each lens ran deep
    assert len(result.lens_outputs) == 2  # each captured
    assert result.synthesis  # synthesized


@pytest.mark.integration
async def test_one_lens_failure_does_not_crash_committee(monkeypatch):
    """A single lens raising must not take down its siblings."""

    async def _fake_run_reasoning(*, thought, classification, composition, product_id, model, on_phase):
        disc = classification["discipline"]
        if disc == "data":
            raise RuntimeError("data lens exploded")
        from core.engine.cognition.reasoning_run import ReasoningResult

        return ReasoningResult(conclusion=f"{disc} conclusion", phases=[])

    async def _fake_compose(classification, product_id):
        from core.engine.cognition.models import CognitiveComposition, RecipePhase

        return CognitiveComposition(
            meta_skills=[classification["discipline"]],
            depth=3,
            active_phases=[RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")],
            resolved_instruments={},
            prompt_sections=[],
            fusion_mode=False,
        )

    monkeypatch.setattr(dc, "run_reasoning", _fake_run_reasoning)
    monkeypatch.setattr(dc, "_compose_for_lens", _fake_compose, raising=False)

    result = await dc.run_deep_committee(
        "do the thing",
        ["architecture", "data"],
        "product:platform",
    )
    # surviving lens's conclusion still came through; failed lens is dropped, not raised
    assert "architecture" in result.lens_outputs
    assert "data" not in result.lens_outputs
    assert result.synthesis


@pytest.mark.unit
async def test_empty_lenses_returns_empty_committee_result():
    """Defensive: an empty lens set produces an empty result, not a crash."""
    result = await dc.run_deep_committee("anything", [], "product:platform")
    assert result.lens_outputs == {}
    assert result.lens_lineage == {}
    assert result.synthesis == ""


@pytest.mark.integration
async def test_run_deep_committee_records_recipe_slugs(monkeypatch):
    """CommitteeResult exposes recipe_slugs — per-lens recipe identifiers
    used by Phase B's signal emitter."""
    from core.engine.cognition.reasoning_run import ReasoningResult

    async def _fake_run_reasoning(*, thought, classification, composition, product_id, model, on_phase):
        return ReasoningResult(conclusion=f"{classification['discipline']} concl", phases=[])

    async def _fake_compose(classification, product_id):
        from core.engine.cognition.models import CognitiveComposition, RecipePhase

        return CognitiveComposition(
            meta_skills=[f"{classification['discipline']}_intelligence"],
            depth=3,
            active_phases=[RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")],
            resolved_instruments={},
            prompt_sections=[],
            fusion_mode=False,
        )

    monkeypatch.setattr(dc, "run_reasoning", _fake_run_reasoning)
    monkeypatch.setattr(dc, "_compose_for_lens", _fake_compose, raising=False)

    result = await dc.run_deep_committee(
        "redesign",
        ["architecture", "security"],
        "product:platform",
    )
    assert result.recipe_slugs == {
        "architecture": "architecture_intelligence",
        "security": "security_intelligence",
    }
