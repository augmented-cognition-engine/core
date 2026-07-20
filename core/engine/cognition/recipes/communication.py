from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="communication_intelligence",
        name="Communication Intelligence",
        description="Structures communication tasks with audience modeling, message prioritization, framing selection, and granularity calibration.",
        domain_intelligences=["communication", "documentation"],
        activation_signals=[
            "communicate",
            "explain",
            "articulate",
            "write",
            "document",
            "present",
            "brief",
            "message",
            "narrative",
            "story",
            "copy",
            "audience",
            "framing",
            "simplify",
            "clarity",
            "voice",
            "tone",
            "say it",
            "land the message",
        ],
        archetype_affinity={
            "advisor": 0.85,
            "creator": 0.85,
            "researcher": 0.7,
            "analyst": 0.7,
            "executor": 0.6,
            "sentinel": 0.5,
        },
        mode_affinity={
            "deliberative": 0.85,
            "reflective": 0.8,
            "conversational": 0.7,
            "exploratory": 0.65,
            "procedural": 0.5,
            "reactive": 0.4,
        },
        composability={
            "complements": [
                "creative_intelligence",
                "research_intelligence",
                "evaluation_intelligence",
                "communication_agentic_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="audience-modeling", fallback_slug="first-principles")],
                    min_depth=1,
                    output_schema="audience_profile, what_they_care_about, prior_knowledge",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="message-maxdiff", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="top_messages_for_this_audience",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="framing-selection", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="frame_that_moves_the_decision",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="channel-matching", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="right_format_tool_granularity",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="granularity-calibration", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="detail_budget_per_audience_segment",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="three-mode-critique", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="clarity_issues, alternative_framings, polish",
                    pattern="pipeline",
                ),
            ]
        ),
    )
