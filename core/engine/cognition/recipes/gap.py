from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="gap_intelligence",
        name="Gap/Blind Spot Intelligence",
        description="Structures gap analysis with coverage mapping, absence ranking, intentional vs accidental gap classification, and meta-gap analysis.",
        domain_intelligences=["gap_analysis", "audit"],
        activation_signals=[
            "gap",
            "missing",
            "blind spot",
            "what's not",
            "absence",
            "coverage",
            "untested",
            "hidden",
            "overlooked",
            "audit",
            "what are we missing",
            "uncovered",
            "incomplete",
        ],
        archetype_affinity={
            "sentinel": 0.9,
            "researcher": 0.85,
            "analyst": 0.85,
            "advisor": 0.7,
            "creator": 0.55,
            "executor": 0.5,
        },
        mode_affinity={
            "reflective": 0.95,
            "deliberative": 0.85,
            "exploratory": 0.85,
            "procedural": 0.6,
            "conversational": 0.5,
            "reactive": 0.5,
        },
        composability={
            "complements": [
                "evaluation_intelligence",
                "verification_intelligence",
                "research_intelligence",
                "retrieval_intelligence",
                "feedback_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="coverage-mapping", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="expected_territory_mapped",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="absence-ranking", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="highest_impact_missing_pieces",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="gap-vs-intentional", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="missing_by_accident_vs_design",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="completeness-testing", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="whole_thing_coheres_if_gap_filled",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="urgency-distribution", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="blocking_vs_nice_to_have_gaps",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="meta-gap-analysis", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="gaps_missed_in_gap_analysis",
                    pattern="solo",
                ),
            ]
        ),
    )
