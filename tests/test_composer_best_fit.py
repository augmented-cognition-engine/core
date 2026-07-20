"""Best-fit-per-slot blend: pure, hermetic (no live DB/LLM)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.cognition.composer import CognitiveComposer, _blend_best_fit
from core.engine.cognition.models import (
    InstrumentSpec,
    MetaSkill,
    MetaSkillRecipe,
    RecipePhase,
)


def _phase(fn: str, *, min_depth: int = 1, signature: float = 0.5) -> RecipePhase:
    return RecipePhase(
        cognitive_function=fn,
        instruments=[InstrumentSpec(fallback_slug="first-principles")],
        min_depth=min_depth,
        output_schema="x",
        signature=signature,
    )


def _skill(slug: str, phases: list[RecipePhase]) -> MetaSkill:
    return MetaSkill(
        slug=slug,
        name=slug,
        description=slug,
        domain_intelligences=[],
        recipe=MetaSkillRecipe(phases=phases),
    )


def test_higher_signature_wins_shared_slot_despite_lower_score():
    # generalist scores higher overall, specialist owns the slot by signature
    generalist = _skill("generalist", [_phase("validate", min_depth=1, signature=0.5)])
    specialist = _skill("specialist", [_phase("validate", min_depth=1, signature=0.9)])
    blended = _blend_best_fit([("generalist", generalist, 0.82), ("specialist", specialist, 0.75)], depth=1)
    winners = {p.cognitive_function: slug for slug, p in blended}
    assert winners["validate"] == "specialist"  # 0.75+0.225 > 0.82+0.125


def test_equal_signature_falls_back_to_rank_order():
    first = _skill("first", [_phase("frame", signature=0.5)])
    second = _skill("second", [_phase("frame", signature=0.5)])
    blended = _blend_best_fit([("first", first, 0.80), ("second", second, 0.70)], depth=1)
    winners = {p.cognitive_function: slug for slug, p in blended}
    assert winners["frame"] == "first"  # higher score wins on equal signature


def test_min_depth_gate_excludes_deep_phases():
    skill = _skill("s", [_phase("frame", min_depth=1), _phase("critique", min_depth=4)])
    blended = _blend_best_fit([("s", skill, 0.9)], depth=3)
    fns = {p.cognitive_function for _, p in blended}
    assert "frame" in fns
    assert "critique" not in fns  # min_depth 4 > depth 3


def test_canonical_function_order_is_emitted():
    # a's phases are seen in [frame, validate] order and b's [choose] is seen
    # last, but emission must follow the canonical spine order
    # (frame, prioritize, choose, validate, review, allocate, critique), not
    # first-seen order — so choose (seen last) is emitted before validate
    # (seen first).
    a = _skill("a", [_phase("frame"), _phase("validate")])
    b = _skill("b", [_phase("choose")])
    blended = _blend_best_fit([("a", a, 0.9), ("b", b, 0.5)], depth=1)
    order = [p.cognitive_function for _, p in blended]
    assert order == ["frame", "choose", "validate"]


def test_exact_tie_keeps_first_seen_incumbent():
    # Identical score AND identical signature — the incumbent (first-seen) must hold
    # the slot. This exercises the `elif slot_score > cur[0]` strict-greater rule that
    # is load-bearing for golden equivalence: an equal slot_score never displaces.
    first = _skill("first", [_phase("frame", signature=0.5)])
    second = _skill("second", [_phase("frame", signature=0.5)])
    blended = _blend_best_fit([("first", first, 0.70), ("second", second, 0.70)], depth=1)
    winners = {p.cognitive_function: slug for slug, p in blended}
    assert winners["frame"] == "first"  # exact tie -> first-seen incumbent wins


def test_uniform_signature_matches_first_wins_golden():
    # With all signatures equal, best-fit picks the SAME winners as legacy
    # first-in-rank-order-wins — the golden guarantee is winner-equivalence,
    # not byte-identical emission order. Emission order is now canonical
    # (_CANONICAL_FUNCTION_ORDER), which can differ from first-seen order
    # whenever functions are first seen out of spine order (as here: 'choose'
    # is first seen after 'frame'/'validate' from skill 'a', but canonical
    # order still places it before 'validate').
    from core.engine.cognition.composer import _CANONICAL_FUNCTION_ORDER

    a = _skill("a", [_phase("frame"), _phase("validate")])
    b = _skill("b", [_phase("frame"), _phase("choose")])  # shares 'frame'
    skills = [("a", a, 0.80), ("b", b, 0.60)]
    blended = _blend_best_fit(skills, depth=1)

    # Replicate legacy first-wins inline as the golden reference (winner set only).
    seen: set[str] = set()
    expected_winners: dict[str, str] = {}
    for slug, skill, _ in skills:
        for ph in skill.recipe.phases:
            if ph.cognitive_function in seen:
                continue
            seen.add(ph.cognitive_function)
            expected_winners[ph.cognitive_function] = slug

    actual_winners = {p.cognitive_function: slug for slug, p in blended}
    assert actual_winners == expected_winners  # (a) same winners as first-wins

    expected_order = [fn for fn in _CANONICAL_FUNCTION_ORDER if fn in expected_winners]
    actual_order = [p.cognitive_function for _, p in blended]
    assert actual_order == expected_order  # (b) emitted in canonical order


def test_coding_wins_its_signature_slots_over_higher_scored_systems():
    from core.engine.cognition.recipes.coding import get_meta_skill as get_coding
    from core.engine.cognition.recipes.systems import get_meta_skill as get_systems

    coding = get_coding()
    systems = get_systems()
    # systems scores HIGHER overall (0.82 vs 0.75); coding must still own its slots.
    blended = _blend_best_fit(
        [("systems_intelligence", systems, 0.82), ("coding_intelligence", coding, 0.75)],
        depth=4,  # deep enough that critique (min_depth 4) and review (3) are active
    )
    winners = {p.cognitive_function: slug for slug, p in blended}

    assert winners["review"] == "coding_intelligence"  # unique to coding
    assert winners["validate"] == "coding_intelligence"  # 0.75+0.225 > 0.82+0.125
    assert winners["critique"] == "coding_intelligence"
    # sanity: systems still contributes a slot it is better-fit for
    assert "frame" in winners


# ---------------------------------------------------------------------------
# IMP-2: compose-through reachability — drives the REAL await composer.compose()
# path (dynamic meta-skill selection, real coding/systems recipes, real
# _blend_best_fit call inside _compose_inner), not a hand-assembled call to
# _blend_best_fit. Only FrameworkClassifier.resolve_instrument is mocked
# (mirrors the hermetic pattern in tests/test_cognition_composer.py); no live
# DB/LLM is touched — ToolClassifier.resolve_tool fails open to its static
# fallback when tool_perf is unreachable, and the canvas emit is fire-and-forget.
# ---------------------------------------------------------------------------


def _owning_meta_skill(composer: CognitiveComposer, phase: RecipePhase) -> str:
    """Identify which cached recipe a phase object came from, by identity.

    _blend_best_fit never copies RecipePhase objects — composition.active_phases
    holds the exact same object references as the source MetaSkill.recipe.phases
    lists cached on `composer`. Comparing by identity (not content) lets the test
    determine real ownership without re-deriving the best-fit algorithm itself.
    """
    for slug in composer._recipe_cache:
        skill = composer._recipe_cache[slug]
        if any(phase is p for p in skill.recipe.phases):
            return slug
    return "<unowned>"


@pytest.mark.asyncio
async def test_compose_through_coding_wins_signature_slots_despite_lower_score():
    """Reachability guarantee: coding_intelligence owns validate/review/critique
    through the REAL compose() path — not just the hand-scored unit test above.

    Classification is an architecture-flavored code task carrying both strong
    systems signals (scaling architecture, throughput, latency, capacity,
    infrastructure, distributed topology) and strong coding signals (refactor,
    module, API endpoint, integration) at depth 4 (reflective mode), so both
    systems_intelligence and coding_intelligence are selected and genuinely
    compete on relevance score.
    """
    composer = CognitiveComposer()
    classification = {
        "discipline": "architecture",
        "task_type": "design",
        "mode": "reflective",
        "complexity": "complex",
        "archetype": "analyst",
        "description": (
            "Assess the system's scaling architecture, throughput and latency under "
            "load, capacity and infrastructure boundaries, and distributed topology — "
            "while also refactoring the module and rebuilding the API endpoint to fix "
            "the integration."
        ),
    }
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        composition = await composer.compose(classification, "product:test")

    assert "coding_intelligence" in composition.meta_skills
    assert "systems_intelligence" in composition.meta_skills
    assert composition.depth == 4  # reflective mode -> depth 4, so critique (min_depth 4) is active

    owners = {phase.cognitive_function: _owning_meta_skill(composer, phase) for phase in composition.active_phases}

    # Real relevance scoring puts systems_intelligence AHEAD of coding_intelligence
    # overall on this task (systems ~0.94 vs coding ~0.85 at time of writing) — so
    # systems wins the shared slots it has no signature advantage on...
    assert owners["frame"] == "systems_intelligence"
    assert owners["choose"] == "systems_intelligence"
    # ...but coding's high-signature slots (validate/review/critique, signature=0.9)
    # still go to coding despite the lower overall score — the guarantee this
    # feature exists for, proven through the real compose() path.
    assert owners["validate"] == "coding_intelligence"
    assert owners["review"] == "coding_intelligence"
    assert owners["critique"] == "coding_intelligence"
