from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="tool_intelligence",
        name="Tool Intelligence",
        description="Structures tool selection with inventory assessment, task-tool matching, tool chain composition, limitation awareness, and fallback strategy.",
        domain_intelligences=["tool_use", "execution"],
        activation_signals=[
            "tool",
            "which tool",
            "how to",
            "command",
            "API call",
            "integration",
            "MCP",
            "capability",
            "library choice",
            "plumbing",
            "wire up",
            "what's available",
            "tool chain",
        ],
        archetype_affinity={
            "executor": 0.85,
            "advisor": 0.7,
            "analyst": 0.7,
            "creator": 0.6,
            "sentinel": 0.6,
            "researcher": 0.5,
        },
        mode_affinity={
            "procedural": 0.9,
            "deliberative": 0.7,
            "reactive": 0.7,
            "conversational": 0.6,
            "reflective": 0.55,
            "exploratory": 0.55,
        },
        composability={
            "complements": [
                "delegation_intelligence",
                "coordination_intelligence",
                "coding_intelligence",
                "operational_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="tool-inventory-assessment", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="available_tools_for_this_task",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="task-tool-matching", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="best_tool_per_subtask",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="tool-chain-composition", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="search_extract_execute_verify_order",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="limitation-awareness", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="what_tool_cannot_do_where_it_fails",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="tool-cost-budget", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="api_calls_worth_it_budget",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="fallback-strategy", fallback_slug="fmea")],
                    min_depth=4,
                    output_schema="plan_b_if_preferred_tool_fails",
                    pattern="solo",
                ),
            ]
        ),
    )
