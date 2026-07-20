from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="communication_agentic_intelligence",
        name="Communication (Agentic) Intelligence",
        description="Structures agent-to-agent and agent-to-PM communication with handoff structuring, context passing, channel selection, and feedback loop design.",
        domain_intelligences=["agent_communication", "handoff"],
        activation_signals=[
            "handoff",
            "agent communication",
            "spin",
            "shared memory",
            "status",
            "briefing payload",
            "subagent",
            "AI-to-AI",
            "PM communication",
            "what does the next agent need",
            "expectation framing",
        ],
        archetype_affinity={
            "executor": 0.8,
            "advisor": 0.75,
            "sentinel": 0.65,
            "analyst": 0.6,
            "creator": 0.55,
            "researcher": 0.45,
        },
        mode_affinity={
            "procedural": 0.85,
            "conversational": 0.75,
            "deliberative": 0.75,
            "reflective": 0.65,
            "exploratory": 0.5,
            "reactive": 0.55,
        },
        composability={
            "complements": [
                "communication_intelligence",
                "delegation_intelligence",
                "coordination_intelligence",
                "tool_intelligence",
                "memory_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="handoff-structuring", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="what_next_agent_needs_to_know",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="context-passing", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="essential_context_vs_noise",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="communication-channel", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="spin_handoff_vs_shared_memory_vs_direct_message",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="expectation-framing", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="receiving_agent_knows_what_is_expected",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="status-granularity", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="pm_gets_summary_peer_agent_gets_details",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="feedback-loop-design", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="receiving_agent_can_ask_for_clarification",
                    pattern="solo",
                ),
            ]
        ),
    )
