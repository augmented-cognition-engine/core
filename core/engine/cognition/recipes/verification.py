from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="verification_intelligence",
        name="Verification Intelligence",
        description="Structures verification with spec compliance framing, test strategy prioritization, verification approach selection, and regression detection.",
        domain_intelligences=["testing", "verification", "qa"],
        activation_signals=[
            "verify",
            "validate",
            "test",
            "check",
            "confirm",
            "spec compliance",
            "contract",
            "conformance",
            "regression",
            "integration test",
            "unit test",
            "e2e",
            "QA",
            "make sure",
            "prove it works",
        ],
        archetype_affinity={
            "sentinel": 0.95,
            "executor": 0.85,
            "analyst": 0.8,
            "advisor": 0.65,
            "researcher": 0.5,
            "creator": 0.45,
        },
        mode_affinity={
            "procedural": 0.9,
            "deliberative": 0.85,
            "reflective": 0.8,
            "reactive": 0.65,
            "conversational": 0.55,
            "exploratory": 0.5,
        },
        composability={
            "complements": [
                "evaluation_intelligence",
                "risk_intelligence",
                "coding_intelligence",
                "systems_intelligence",
                "gap_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="spec-compliance-framing", fallback_slug="constraint-theory")],
                    min_depth=1,
                    output_schema="what_correct_means_for_this_task",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="test-strategy", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="what_to_test_at_what_level",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="verification-approach", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="unit_vs_integration_vs_manual_vs_formal",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="assumption-validation", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="assumption_held_against_actual_state",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="coverage-budget", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="testing_effort_on_critical_paths_first",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="regression-detection", fallback_slug="fmea")],
                    min_depth=4,
                    output_schema="fixing_x_broke_y_blast_radius",
                    pattern="solo",
                ),
            ]
        ),
    )
