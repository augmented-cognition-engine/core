from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="delegation_intelligence",
        name="Delegation Intelligence",
        description="Structures delegation decisions with capability matching, spec quality assessment, routing pairwise comparison, and output review.",
        domain_intelligences=["delegation", "orchestration"],
        activation_signals=[
            "delegate",
            "assign",
            "route",
            "dispatch",
            "hand off",
            "who should",
            "which agent",
            "subagent",
            "divide work",
            "parallel agents",
            "split this up",
            "spawn",
            "fork",
        ],
        archetype_affinity={
            "executor": 0.85,
            "advisor": 0.85,
            "analyst": 0.7,
            "sentinel": 0.6,
            "creator": 0.55,
            "researcher": 0.45,
        },
        mode_affinity={
            "deliberative": 0.85,
            "procedural": 0.85,
            "reflective": 0.7,
            "conversational": 0.6,
            "exploratory": 0.5,
            "reactive": 0.55,
        },
        composability={
            "complements": [
                "coordination_intelligence",
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
                    instruments=[InstrumentSpec(slug="capability-matching", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="skills_needed, haiku_vs_sonnet_vs_opus",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="spec-quality", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="what_delegate_needs_to_know_to_succeed",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="routing-pairwise", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="agent_a_vs_b_vs_do_it_myself_cost_quality_speed",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="output-review", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="delegated_output_matches_intent",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="cost-aware-routing", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="batch_vs_realtime_routing",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="three-mode-critique", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="delegation_worthwhile, better_spec_next_time",
                    pattern="pipeline",
                ),
            ]
        ),
    )
