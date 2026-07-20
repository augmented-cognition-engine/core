from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="retrieval_intelligence",
        name="Retrieval/Context Intelligence",
        description="Structures retrieval tasks with relevance scoping, source ranking, context selection, gap detection, and freshness assessment.",
        domain_intelligences=["retrieval", "context", "search"],
        activation_signals=[
            "search",
            "find",
            "retrieve",
            "lookup",
            "query",
            "recall",
            "context",
            "relevant",
            "source",
            "history",
            "prior",
            "docs",
            "reference",
            "what do we know",
            "where is",
            "look up",
        ],
        archetype_affinity={
            "researcher": 0.9,
            "analyst": 0.8,
            "executor": 0.7,
            "advisor": 0.65,
            "creator": 0.55,
            "sentinel": 0.5,
        },
        mode_affinity={
            "exploratory": 0.85,
            "deliberative": 0.7,
            "conversational": 0.7,
            "procedural": 0.65,
            "reflective": 0.65,
            "reactive": 0.6,
        },
        composability={
            "complements": [
                "research_intelligence",
                "memory_intelligence",
                "gap_intelligence",
                "domain_specific_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="relevance-scoping", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="relevant_information_types, irrelevant_to_exclude",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="source-ranking", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="source_priority: internal_docs > code > history > general",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="context-selection", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="specific_files_sections_chosen",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="gap-detection", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="sufficient_to_proceed, what_is_still_missing",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="context-budget", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="token_budget: 40pct_code, 30pct_intel, 20pct_history, 10pct_meta",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="freshness-assessment", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="stale_context_flagged, conflicting_state_detected",
                    pattern="solo",
                ),
            ]
        ),
    )
