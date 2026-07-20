from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="evaluation_intelligence",
        name="Evaluation Intelligence",
        description="Structures evaluation tasks with multi-lens framing, criteria prioritization, pairwise quality comparison, and severity allocation.",
        domain_intelligences=["testing", "security", "accessibility", "code_review", "ai_ml"],
        activation_signals=[
            "evaluate",
            "review",
            "audit",
            "assess",
            "judge",
            "score",
            "quality",
            "critique",
            "test",
            "check",
            "verify quality",
            "accessibility",
            "security review",
            "code review",
            "is this good",
            "does this work",
            "lens",
            "criteria",
        ],
        archetype_affinity={
            "sentinel": 0.95,
            "analyst": 0.85,
            "advisor": 0.75,
            "executor": 0.6,
            "researcher": 0.5,
            "creator": 0.4,
        },
        mode_affinity={
            "reflective": 0.9,
            "deliberative": 0.85,
            "procedural": 0.7,
            "exploratory": 0.6,
            "conversational": 0.5,
            "reactive": 0.4,
        },
        composability={
            "complements": [
                "verification_intelligence",
                "gap_intelligence",
                "risk_intelligence",
                "coding_intelligence",
                "creative_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="multi-lens-framing", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="applicable_lenses: technical, craft, user_impact",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="criteria-maxdiff", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="top_quality_dimensions_for_this_context",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="quality-pairwise", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="quality_verdict_vs_high_bar",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="holistic-validation", fallback_slug="second-order-thinking")],
                    min_depth=3,
                    output_schema="individual_assessments_composed",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="severity-allocation", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="defect_vs_mediocrity_vs_taste_split",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="meta-evaluation", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="evaluation_rigor_self_check",
                    pattern="solo",
                ),
            ]
        ),
    )
