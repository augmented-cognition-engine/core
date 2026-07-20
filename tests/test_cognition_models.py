# tests/test_cognition_models.py
from core.engine.cognition.models import (
    CognitiveComposition,
    InstrumentSpec,
    MetaSkill,
    MetaSkillRecipe,
    RecipePhase,
    derive_depth,
)


def test_derive_depth_reactive():
    assert derive_depth("reactive", "moderate") == 1


def test_derive_depth_conversational():
    assert derive_depth("conversational", "complex") == 1


def test_derive_depth_procedural():
    assert derive_depth("procedural", "moderate") == 2


def test_derive_depth_deliberative_complex():
    assert derive_depth("deliberative", "complex") == 3


def test_derive_depth_deliberative_simple():
    assert derive_depth("deliberative", "simple") == 2


def test_derive_depth_reflective():
    assert derive_depth("reflective", "moderate") == 4


def test_derive_depth_exploratory():
    assert derive_depth("exploratory", "simple") == 4


def test_derive_depth_unknown_defaults_two():
    assert derive_depth("unknown_mode", "moderate") == 2


def test_instrument_spec_explicit_slug():
    spec = InstrumentSpec(slug="first-principles", fallback_slug="mece")
    assert spec.slug == "first-principles"
    assert spec.fallback_slug == "mece"


def test_instrument_spec_family_hint():
    spec = InstrumentSpec(family_hint="diagnostic", fallback_slug="first-principles")
    assert spec.slug is None
    assert spec.family_hint == "diagnostic"


def test_recipe_phase_fields():
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[InstrumentSpec(slug="first-principles", fallback_slug="mece")],
        min_depth=1,
        output_schema="problem_statement",
        pattern="solo",
    )
    assert phase.cognitive_function == "frame"
    assert phase.min_depth == 1
    assert len(phase.instruments) == 1


def test_meta_skill_recipe_phases():
    recipe = MetaSkillRecipe(
        phases=[
            RecipePhase(
                cognitive_function="frame",
                instruments=[InstrumentSpec(slug="first-principles", fallback_slug="mece")],
                min_depth=1,
                output_schema="framing",
                pattern="solo",
            ),
        ]
    )
    assert len(recipe.phases) == 1


def test_meta_skill_complete():
    skill = MetaSkill(
        slug="coding_intelligence",
        name="Coding Intelligence",
        description="Structures coding tasks with constraint-first reasoning.",
        domain_intelligences=["coding"],
        recipe=MetaSkillRecipe(phases=[]),
    )
    assert skill.slug == "coding_intelligence"


def test_cognitive_composition_fusion_mode_depth_one():
    comp = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    assert comp.fusion_mode is True
    assert comp.depth == 1


def test_cognitive_composition_multi_phase_depth_three():
    comp = CognitiveComposition(
        meta_skills=["research_intelligence"],
        depth=3,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=False,
    )
    assert comp.fusion_mode is False


def test_recipe_phase_signature_defaults_to_half():
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[InstrumentSpec(fallback_slug="first-principles")],
        min_depth=1,
        output_schema="x",
    )
    assert phase.signature == 0.5


def test_recipe_phase_signature_is_overridable():
    phase = RecipePhase(
        cognitive_function="critique",
        instruments=[InstrumentSpec(fallback_slug="adversarial-testing")],
        min_depth=4,
        output_schema="x",
        signature=0.9,
    )
    assert phase.signature == 0.9
