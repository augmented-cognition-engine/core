from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="feedback_intelligence",
        name="Feedback Intelligence",
        description="Structures feedback processing with progress assessment, signal triage, approach invalidation check, and sunk-cost resistance.",
        domain_intelligences=["feedback", "calibration"],
        activation_signals=[
            "feedback",
            "signal",
            "response",
            "did this work",
            "on track",
            "pivot",
            "iterate",
            "learning",
            "calibration",
            "course correct",
            "retro",
            "postmortem",
            "lessons learned",
            "invalidated",
            "sunk cost",
        ],
        archetype_affinity={
            "advisor": 0.85,
            "sentinel": 0.85,
            "analyst": 0.8,
            "researcher": 0.7,
            "executor": 0.6,
            "creator": 0.55,
        },
        mode_affinity={
            "reflective": 0.95,
            "deliberative": 0.8,
            "exploratory": 0.65,
            "conversational": 0.65,
            "procedural": 0.6,
            "reactive": 0.55,
        },
        composability={
            "complements": [
                "evaluation_intelligence",
                "gap_intelligence",
                "memory_intelligence",
                "verification_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="progress-assessment", fallback_slug="first-principles")],
                    min_depth=1,
                    output_schema="on_track, success_failure_signals",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="signal-triage", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="signals_worth_attention_vs_noise",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="approach-invalidation", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="current_path_viable_or_pivot",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="incremental-checkpoint", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="assumption_tested_before_building_on_it",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="sunk-cost-resistance", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="continuing_because_right_not_because_started",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="self-calibration", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="confidence_level_calibrated",
                    pattern="solo",
                ),
            ]
        ),
    )
