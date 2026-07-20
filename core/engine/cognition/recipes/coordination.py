from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="coordination_intelligence",
        name="Coordination Intelligence",
        description="Structures multi-agent coordination with work splitting, ownership design, conflict anticipation, merge point identification, and deadlock detection.",
        domain_intelligences=["coordination", "orchestration"],
        activation_signals=[
            "coordinate",
            "parallel agents",
            "multi-agent",
            "team",
            "sync",
            "merge",
            "conflict",
            "handoff",
            "work splitting",
            "deadlock",
            "race condition",
            "who owns what",
            "ownership boundaries",
        ],
        archetype_affinity={
            "executor": 0.85,
            "advisor": 0.8,
            "sentinel": 0.75,
            "analyst": 0.7,
            "creator": 0.5,
            "researcher": 0.4,
        },
        mode_affinity={
            "procedural": 0.9,
            "deliberative": 0.85,
            "reflective": 0.7,
            "conversational": 0.55,
            "exploratory": 0.5,
            "reactive": 0.5,
        },
        composability={
            "complements": [
                "delegation_intelligence",
                "planning_intelligence",
                "communication_agentic_intelligence",
                "tool_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="work-splitting", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="decomposition_across_agents",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="ownership-design", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="who_owns_what_clear_boundaries",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="conflict-anticipation", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="collision_points_prevention_strategy",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[
                        InstrumentSpec(slug="merge-point-identification", fallback_slug="holistic-validation")
                    ],
                    min_depth=3,
                    output_schema="parallel_streams_convergence_points",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="agent-load-balancing", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="work_distributed_fairly_no_overload",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="deadlock-detection", fallback_slug="fmea")],
                    min_depth=4,
                    output_schema="circular_dependencies_agents_waiting_on_each_other",
                    pattern="solo",
                ),
            ]
        ),
    )
