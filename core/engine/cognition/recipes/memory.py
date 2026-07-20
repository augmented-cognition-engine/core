from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="memory_intelligence",
        name="Memory Intelligence",
        description="Structures memory operations with operation type framing, salience detection, keep/merge/discard decisions, and reconstruction completeness.",
        domain_intelligences=["memory", "knowledge_management"],
        activation_signals=[
            "remember",
            "recall",
            "persist",
            "capture",
            "store",
            "knowledge",
            "decision history",
            "prior",
            "context reconstruction",
            "consolidate",
            "episodic",
            "what did we decide",
            "across sessions",
            "compounding",
        ],
        archetype_affinity={
            "researcher": 0.85,
            "analyst": 0.8,
            "advisor": 0.7,
            "sentinel": 0.7,
            "executor": 0.65,
            "creator": 0.55,
        },
        mode_affinity={
            "reflective": 0.9,
            "deliberative": 0.8,
            "exploratory": 0.75,
            "procedural": 0.65,
            "conversational": 0.6,
            "reactive": 0.55,
        },
        composability={
            "complements": [
                "retrieval_intelligence",
                "feedback_intelligence",
                "gap_intelligence",
                "domain_specific_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="memory-operation-type", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="capture_vs_consolidate_vs_reconstruct",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="salience-detection", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="decision_over_correction_over_pattern_over_fact",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="keep-merge-discard", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="conflict_with_existing_knowledge_resolved",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="staleness-check", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="memory_valid_against_current_state",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="context-reconstruction-budget", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="40pct_decisions_30pct_knowledge_20pct_connections_10pct_episodic",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[
                        InstrumentSpec(slug="reconstruction-completeness", fallback_slug="adversarial-testing")
                    ],
                    min_depth=4,
                    output_schema="right_context_reconstructed_nothing_missing",
                    pattern="solo",
                ),
            ]
        ),
    )
