"""Tests for the problem-derived meta-skill selector.

Covers _score_meta_skill_relevance (pure scoring) and
CognitiveComposer._select_meta_skills_dynamic (composition).
"""

from __future__ import annotations

from core.engine.cognition.composer import (
    CognitiveComposer,
    _score_meta_skill_relevance,
)
from core.engine.cognition.recipes.coding import get_meta_skill as get_coding
from core.engine.cognition.recipes.creative import get_meta_skill as get_creative

# ---------------------------------------------------------------------------
# _score_meta_skill_relevance — pure scoring
# ---------------------------------------------------------------------------


def test_score_returns_value_in_unit_interval():
    """Score must always be in [0.0, 1.0]."""
    ms = get_coding()
    score = _score_meta_skill_relevance(
        ms,
        {"discipline": "architecture", "archetype": "executor", "mode": "deliberative"},
        task_text="build a function",
    )
    assert 0.0 <= score <= 1.0


def test_score_signal_match_boosts_relevance():
    """A task whose text matches activation signals should score higher than one that doesn't."""
    ms = get_creative()
    classification = {"discipline": "ux", "archetype": "creator", "mode": "deliberative"}

    with_signals = _score_meta_skill_relevance(
        ms, classification, task_text="design the user experience with strong visual hierarchy"
    )
    without_signals = _score_meta_skill_relevance(ms, classification, task_text="refactor the build pipeline")

    assert with_signals > without_signals


def test_score_archetype_affinity_matters():
    """A meta-skill should score higher when its preferred archetype is active."""
    ms = get_creative()  # creator archetype affinity = 0.95
    task = "make the interface look better"

    creator_score = _score_meta_skill_relevance(
        ms, {"archetype": "creator", "mode": "deliberative", "discipline": "ux"}, task_text=task
    )
    executor_score = _score_meta_skill_relevance(
        ms, {"archetype": "executor", "mode": "deliberative", "discipline": "ux"}, task_text=task
    )

    assert creator_score > executor_score


def test_score_mode_affinity_penalizes_reactive_for_deliberative_skills():
    """Creative intelligence has low reactive affinity (0.15); it should score lower in reactive mode."""
    ms = get_creative()
    task = "design a component"

    deliberative_score = _score_meta_skill_relevance(
        ms, {"archetype": "creator", "mode": "deliberative", "discipline": "ux"}, task_text=task
    )
    reactive_score = _score_meta_skill_relevance(
        ms, {"archetype": "creator", "mode": "reactive", "discipline": "ux"}, task_text=task
    )

    assert deliberative_score > reactive_score


def test_score_domain_match_contributes():
    """A meta-skill whose domain_intelligences include the classified discipline should score higher."""
    ms = get_coding()  # domain_intelligences includes "architecture"
    task = "do something"

    matching = _score_meta_skill_relevance(
        ms, {"discipline": "architecture", "archetype": "executor", "mode": "procedural"}, task_text=task
    )
    non_matching = _score_meta_skill_relevance(
        ms,
        {"discipline": "marketing", "archetype": "executor", "mode": "procedural"},
        task_text=task,
    )

    assert matching > non_matching


def test_score_empty_inputs_does_not_crash():
    """Empty classification should produce a score, not an exception."""
    ms = get_coding()
    score = _score_meta_skill_relevance(ms, {}, task_text="")
    assert 0.0 <= score <= 1.0


def test_score_handles_unpopulated_metaskill():
    """A meta-skill without activation_signals/affinities should still score (using defaults)."""
    from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase

    bare = MetaSkill(
        slug="bare_intelligence",
        name="Bare",
        description="No metadata",
        domain_intelligences=[],
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(fallback_slug="first-principles")],
                    min_depth=1,
                    output_schema="x",
                )
            ]
        ),
    )
    score = _score_meta_skill_relevance(
        bare,
        {"discipline": "architecture", "archetype": "analyst", "mode": "deliberative"},
        task_text="some task",
    )
    # With zero signals and zero affinities, score reduces to defaults (0.5 archetype, 0.5 mode)
    # 0.45 * 0 + 0.20 * 0.5 + 0.25 * 0.5 + 0.10 * 0 = 0.225
    assert 0.20 <= score <= 0.30


# ---------------------------------------------------------------------------
# _select_meta_skills_dynamic — composition selection
# ---------------------------------------------------------------------------


def test_dynamic_select_ui_build_co_fires_creative_and_coding():
    """A UI-touching build task should self-nominate both creative and coding intelligences
    without any hardcoded co-fire rule — purely from activation_signals + composability."""
    composer = CognitiveComposer()

    classification = {
        "discipline": "ux",
        "task_type": "build",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
        "description": "Build a new UI component for the canvas with strong visual hierarchy",
    }

    selected = composer._select_meta_skills_dynamic(classification)

    assert "creative_intelligence" in selected, f"Creative did not co-fire on UI build: {selected}"
    assert "coding_intelligence" in selected, f"Coding did not co-fire on UI build: {selected}"


def test_dynamic_select_strategic_decision_fires_strategic_and_risk():
    """A strategic decision should self-nominate strategic_intelligence and risk_intelligence."""
    composer = CognitiveComposer()

    classification = {
        "discipline": "product_strategy",
        "task_type": "plan",
        "archetype": "advisor",
        "mode": "deliberative",
        "complexity": "complex",
        "description": "Should we pivot to a new market positioning? Compare tradeoffs.",
    }

    selected = composer._select_meta_skills_dynamic(classification)

    assert "strategic_intelligence" in selected, f"Strategic missing: {selected}"
    # Risk should fire on a tradeoff/pivot task
    assert "risk_intelligence" in selected, f"Risk missing on strategic decision: {selected}"


def test_dynamic_select_audit_fires_evaluation_and_gap():
    """An audit task should self-nominate evaluation and gap intelligences."""
    composer = CognitiveComposer()

    classification = {
        "discipline": "security",
        "task_type": "review",
        "archetype": "sentinel",
        "mode": "reflective",
        "complexity": "moderate",
        "description": "Audit the deployment pipeline for security gaps and accessibility coverage",
    }

    selected = composer._select_meta_skills_dynamic(classification)

    assert "evaluation_intelligence" in selected, f"Evaluation missing: {selected}"
    assert "gap_intelligence" in selected, f"Gap missing: {selected}"


def test_dynamic_select_always_includes_domain_specific():
    """domain_specific_intelligence is always included for context grounding."""
    composer = CognitiveComposer()

    selected = composer._select_meta_skills_dynamic(
        {"discipline": "ux", "task_type": "design", "archetype": "creator", "mode": "deliberative"}
    )

    assert "domain_specific_intelligence" in selected


def test_dynamic_select_respects_max_skills_cap():
    """Even when many meta-skills are relevant, the cap should hold."""
    composer = CognitiveComposer()

    selected = composer._select_meta_skills_dynamic(
        {
            "discipline": "architecture",
            "task_type": "implement",
            "archetype": "executor",
            "mode": "deliberative",
            "complexity": "complex",
            "description": "Build, test, deploy, document, verify, design, audit everything",
        },
        max_skills=4,
    )

    # max_skills caps the threshold-selected set; domain_specific is appended after
    # for context grounding (which can push total to max_skills + 1).
    assert len(selected) <= 5


def test_dynamic_select_threshold_filters():
    """A very high threshold should still produce domain_specific as the fallback."""
    composer = CognitiveComposer()

    selected = composer._select_meta_skills_dynamic(
        {"discipline": "architecture", "archetype": "executor", "mode": "reactive"},
        threshold=0.99,
    )

    # Domain_specific is always included as fallback
    assert "domain_specific_intelligence" in selected


def test_dynamic_select_with_empty_classification():
    """An empty classification should not crash; should return at least domain_specific."""
    composer = CognitiveComposer()

    selected = composer._select_meta_skills_dynamic({})

    assert isinstance(selected, list)
    assert "domain_specific_intelligence" in selected


# ---------------------------------------------------------------------------
# _rank_meta_skills_dynamic / _selected_with_scores — relevance score threading
# ---------------------------------------------------------------------------


def test_rank_dynamic_returns_scores_for_every_selected_slug():
    comp = CognitiveComposer()
    classification = {
        "discipline": "architecture",
        "task_type": "build",
        "archetype": "executor",
        "mode": "deliberative",
        "complexity": "moderate",
        "description": "build and refactor a code module with tests",
    }
    ranked = comp._rank_meta_skills_dynamic(classification)
    slugs_only = comp._select_meta_skills_dynamic(classification)

    assert [s for s, _ in ranked] == slugs_only  # same slugs, same order
    assert all(isinstance(sc, float) for _, sc in ranked)  # every slug carries a score
    # ranked in non-increasing score order except the appended domain_specific floor
    body = [sc for s, sc in ranked if s != "domain_specific_intelligence"]
    assert body == sorted(body, reverse=True)


def test_selected_with_scores_legacy_is_rank_dominant(monkeypatch):
    import core.engine.cognition.composer as composer_mod

    monkeypatch.setattr(composer_mod, "ENABLE_PROBLEM_DERIVED_SELECTION", False)
    comp = CognitiveComposer()
    classification = {"discipline": "architecture", "task_type": "build", "mode": "deliberative"}
    slugs, scores = comp._selected_with_scores(classification)

    assert set(scores) == set(slugs)
    # earlier slug strictly outscores later by a margin far larger than SIGNATURE_WEIGHT
    for earlier, later in zip(slugs, slugs[1:]):
        assert scores[earlier] - scores[later] >= 100.0
