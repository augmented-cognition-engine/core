"""Tests for the product_decision_intelligence recipe shape."""

import pytest


@pytest.mark.unit
def test_recipe_has_five_phases_with_product_reasoning_identity():
    """The recipe must have exactly 5 phases in the order Frame → Reality →
    Voices → Tradeoffs → Recommend, each with the expected cognitive_function."""
    from extensions.reference.recipe import get_meta_skill

    skill = get_meta_skill()
    assert skill.slug == "product_decision_intelligence"
    assert "product" in skill.domain_intelligences

    cogs = [p.cognitive_function for p in skill.recipe.phases]
    assert cogs == ["frame", "assess", "engage", "prioritize", "recommend"]


@pytest.mark.unit
def test_frame_phase_uses_product_framing_instrument():
    """Phase 1 must reference the product-framing instrument by slug."""
    from extensions.reference.recipe import get_meta_skill

    frame = get_meta_skill().recipe.phases[0]
    slugs = [i.slug for i in frame.instruments]
    assert "product-framing" in slugs


@pytest.mark.unit
def test_voices_phase_uses_multi_voice_engage_instrument():
    """Phase 3 (Voices) is the partnership thesis in a phase — it MUST invoke
    multi-voice-engage. This is the load-bearing identity of the recipe."""
    from extensions.reference.recipe import get_meta_skill

    voices = get_meta_skill().recipe.phases[2]
    slugs = [i.slug for i in voices.instruments]
    assert "multi-voice-engage" in slugs
    assert voices.pattern == "parallel"


@pytest.mark.unit
def test_recommend_phase_names_kill_criteria_in_output_schema():
    """The Recommend phase's output_schema must name kill_criteria — the
    PM-distinctive move that binds the recommendation to exit conditions."""
    from extensions.reference.recipe import get_meta_skill

    recommend = get_meta_skill().recipe.phases[4]
    assert recommend.cognitive_function == "recommend"
    assert "kill_criteria" in recommend.output_schema
