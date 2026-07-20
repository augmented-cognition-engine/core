import importlib

import pytest

from core.engine.cognition.models import MetaSkill
from core.engine.cognition.recipes.coding import get_meta_skill

DOMAIN_RECIPE_MODULES = [
    ("core.engine.cognition.recipes.creative", "creative_intelligence"),
    ("core.engine.cognition.recipes.research", "research_intelligence"),
    ("core.engine.cognition.recipes.coding", "coding_intelligence"),
    ("core.engine.cognition.recipes.evaluation", "evaluation_intelligence"),
    ("core.engine.cognition.recipes.strategic", "strategic_intelligence"),
    ("core.engine.cognition.recipes.communication", "communication_intelligence"),
    ("core.engine.cognition.recipes.systems", "systems_intelligence"),
    ("core.engine.cognition.recipes.data", "data_intelligence"),
]


@pytest.mark.parametrize("module_path,expected_slug", DOMAIN_RECIPE_MODULES)
def test_domain_recipe_returns_meta_skill(module_path, expected_slug):
    mod = importlib.import_module(module_path)
    skill = mod.get_meta_skill()
    assert isinstance(skill, MetaSkill)
    assert skill.slug == expected_slug


@pytest.mark.parametrize("module_path,expected_slug", DOMAIN_RECIPE_MODULES)
def test_domain_recipe_has_expected_phase_count(module_path, expected_slug):
    mod = importlib.import_module(module_path)
    skill = mod.get_meta_skill()
    # coding_intelligence carries a 7th phase (the graph-grounded `review`); the rest are the standard 6.
    expected_count = 7 if expected_slug == "coding_intelligence" else 6
    assert len(skill.recipe.phases) == expected_count, f"{expected_slug} needs {expected_count} phases"


@pytest.mark.parametrize("module_path,expected_slug", DOMAIN_RECIPE_MODULES)
def test_domain_recipe_phase_one_min_depth_one(module_path, expected_slug):
    mod = importlib.import_module(module_path)
    skill = mod.get_meta_skill()
    assert skill.recipe.phases[0].min_depth == 1


@pytest.mark.parametrize("module_path,expected_slug", DOMAIN_RECIPE_MODULES)
def test_domain_recipe_phase_functions(module_path, expected_slug):
    valid = {"frame", "prioritize", "choose", "validate", "review", "allocate", "critique"}
    mod = importlib.import_module(module_path)
    skill = mod.get_meta_skill()
    for phase in skill.recipe.phases:
        assert phase.cognitive_function in valid


@pytest.mark.parametrize("module_path,expected_slug", DOMAIN_RECIPE_MODULES)
def test_domain_recipe_all_phases_have_instruments(module_path, expected_slug):
    mod = importlib.import_module(module_path)
    skill = mod.get_meta_skill()
    for i, phase in enumerate(skill.recipe.phases):
        assert len(phase.instruments) >= 1, f"phase {i} has no instruments"
        for inst in phase.instruments:
            assert inst.fallback_slug, f"phase {i} instrument missing fallback_slug"


AGENTIC_RECIPE_MODULES = [
    ("core.engine.cognition.recipes.retrieval", "retrieval_intelligence"),
    ("core.engine.cognition.recipes.planning", "planning_intelligence"),
    # prioritization_intelligence is YAML-only (prioritization.yaml) — loaded via
    # discover_core_yaml_recipes() into _RECIPE_YAML, not as an importable .py module.
    ("core.engine.cognition.recipes.delegation", "delegation_intelligence"),
    ("core.engine.cognition.recipes.risk", "risk_intelligence"),
    ("core.engine.cognition.recipes.gap", "gap_intelligence"),
    ("core.engine.cognition.recipes.feedback", "feedback_intelligence"),
    ("core.engine.cognition.recipes.verification", "verification_intelligence"),
    ("core.engine.cognition.recipes.memory", "memory_intelligence"),
    ("core.engine.cognition.recipes.coordination", "coordination_intelligence"),
    ("core.engine.cognition.recipes.tool", "tool_intelligence"),
    ("core.engine.cognition.recipes.communication_agentic", "communication_agentic_intelligence"),
    ("core.engine.cognition.recipes.operational", "operational_intelligence"),
    ("core.engine.cognition.recipes.domain_specific", "domain_specific_intelligence"),
]


@pytest.mark.parametrize("module_path,expected_slug", AGENTIC_RECIPE_MODULES)
def test_agentic_recipe_returns_meta_skill(module_path, expected_slug):
    mod = importlib.import_module(module_path)
    skill = mod.get_meta_skill()
    assert isinstance(skill, MetaSkill)
    assert skill.slug == expected_slug


@pytest.mark.parametrize("module_path,expected_slug", AGENTIC_RECIPE_MODULES)
def test_agentic_recipe_has_six_phases(module_path, expected_slug):
    mod = importlib.import_module(module_path)
    skill = mod.get_meta_skill()
    assert len(skill.recipe.phases) == 6


@pytest.mark.parametrize("module_path,expected_slug", AGENTIC_RECIPE_MODULES)
def test_agentic_recipe_phase_one_min_depth_one(module_path, expected_slug):
    mod = importlib.import_module(module_path)
    skill = mod.get_meta_skill()
    assert skill.recipe.phases[0].min_depth == 1


@pytest.mark.parametrize("module_path,expected_slug", AGENTIC_RECIPE_MODULES)
def test_agentic_recipe_all_phases_have_instruments(module_path, expected_slug):
    mod = importlib.import_module(module_path)
    skill = mod.get_meta_skill()
    for i, phase in enumerate(skill.recipe.phases):
        assert len(phase.instruments) >= 1
        for inst in phase.instruments:
            assert inst.fallback_slug


def test_coding_intelligence_frame_has_must_not():
    skill = get_meta_skill()
    frame = next(p for p in skill.recipe.phases if p.cognitive_function == "frame")
    assert len(frame.must_not) >= 2, "frame phase needs at least 2 must_not constraints"


def test_coding_intelligence_frame_has_must_verify():
    skill = get_meta_skill()
    frame = next(p for p in skill.recipe.phases if p.cognitive_function == "frame")
    assert len(frame.must_verify) >= 1, "frame phase needs at least 1 must_verify check"


def test_coding_intelligence_validate_has_must_not():
    skill = get_meta_skill()
    validate = next((p for p in skill.recipe.phases if p.cognitive_function == "validate"), None)
    assert validate is not None, "coding_intelligence must have a validate phase"
    assert len(validate.must_not) >= 1


def test_coding_intelligence_prioritize_has_must_not():
    skill = get_meta_skill()
    prioritize = next(p for p in skill.recipe.phases if p.cognitive_function == "prioritize")
    assert len(prioritize.must_not) >= 2


def test_coding_intelligence_choose_has_constraints():
    skill = get_meta_skill()
    choose = next(p for p in skill.recipe.phases if p.cognitive_function == "choose")
    assert len(choose.must_not) >= 1
    assert len(choose.must_verify) >= 1


def test_coding_signature_weights():
    phases = {p.cognitive_function: p for p in get_meta_skill().recipe.phases}
    assert phases["frame"].signature == 0.7
    assert phases["choose"].signature == 0.7
    assert phases["validate"].signature == 0.9
    assert phases["review"].signature == 0.9
    assert phases["critique"].signature == 0.9
    assert phases["prioritize"].signature == 0.5
    assert phases["allocate"].signature == 0.5


def test_coding_frame_is_graph_grounded():
    frame = next(p for p in get_meta_skill().recipe.phases if p.cognitive_function == "frame")
    assert "architectural_layer" in frame.output_schema
    assert "realized_capability" in frame.output_schema
    assert any("boundary" in m for m in frame.must_not)
    tool_slugs = {t.fallback_slug for t in frame.tools}
    assert "ace_module_coupling" in tool_slugs
    assert "ace_code_context" in tool_slugs


def test_coding_has_failclosed_graph_review_phase():
    phases = get_meta_skill().recipe.phases
    review = next((p for p in phases if p.cognitive_function == "review"), None)
    assert review is not None
    assert review.min_depth == 3
    assert review.signature == 0.9
    assert "graph_verdict" in review.output_schema
    assert any("cannot verify" in v for v in review.must_verify)  # fail closed
    tool_slugs = {t.fallback_slug for t in review.tools}
    assert {"ace_blast_radius", "ace_dependency_chain", "ace_pr_review"} <= tool_slugs
    # review sits after validate, before allocate
    order = [p.cognitive_function for p in phases]
    assert order.index("validate") < order.index("review") < order.index("allocate")
