from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="domain_specific_intelligence",
        name="Domain-Specific Intelligence",
        description="Activates discipline and specialty knowledge with depth calibration, adjacent reasoning, tradeoff grounding, knowledge freshness validation, and expertise gap detection.",
        domain_intelligences=["discipline_knowledge", "specialty_knowledge"],
        activation_signals=[
            "domain knowledge",
            "specialty",
            "expertise",
            "adjacent discipline",
            "tradeoff knowledge",
            "fresh knowledge",
            "nascent vs expert",
            "what does this field say",
            "domain-grounded",
        ],
        archetype_affinity={
            "researcher": 0.85,
            "advisor": 0.8,
            "analyst": 0.8,
            "sentinel": 0.65,
            "creator": 0.6,
            "executor": 0.55,
        },
        mode_affinity={
            "deliberative": 0.85,
            "reflective": 0.8,
            "exploratory": 0.75,
            "conversational": 0.6,
            "procedural": 0.6,
            "reactive": 0.5,
        },
        composability={
            "complements": [
                "retrieval_intelligence",
                "memory_intelligence",
                "research_intelligence",
                "gap_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[
                        InstrumentSpec(slug="discipline-activation", fallback_slug="mece"),
                        InstrumentSpec(slug="core-tradeoffs", fallback_slug="discipline-activation"),
                    ],
                    min_depth=1,
                    output_schema="applicable_disciplines_specialties, active_tradeoffs",
                    pattern="pipeline",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="depth-calibration", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="nascent_vs_expert_approach_depth",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="adjacent-reasoning", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="adjacent_disciplines_for_low_confidence_primary",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[
                        InstrumentSpec(slug="knowledge-freshness", fallback_slug="holistic-validation"),
                        InstrumentSpec(slug="tradeoff-analysis", fallback_slug="knowledge-freshness"),
                    ],
                    min_depth=3,
                    output_schema="discipline_knowledge_current_verified, active_tradeoffs_addressed",
                    pattern="pipeline",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="specialty-budget", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="load_3_specialties_max_ranked",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="expertise-gap-detection", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="thin_domain_knowledge_flagged_for_research",
                    pattern="solo",
                ),
            ]
        ),
    )
