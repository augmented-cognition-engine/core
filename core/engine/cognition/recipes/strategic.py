from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="strategic_intelligence",
        name="Strategic Intelligence",
        description="Structures strategic decisions with product-strategy fit analysis, market positioning, leverage analysis, pairwise path comparison, and optionality assessment.",
        domain_intelligences=["strategy", "product", "planning"],
        activation_signals=[
            "strategy",
            "decision",
            "pivot",
            "direction",
            "roadmap",
            "market",
            "positioning",
            "competitive",
            "business",
            "vision",
            "tradeoff",
            "should we",
            "choose between",
            "path forward",
            "optionality",
            "leverage",
            "second-order",
            "what bet",
            "moat",
        ],
        archetype_affinity={
            "advisor": 0.95,
            "analyst": 0.85,
            "researcher": 0.7,
            "creator": 0.65,
            "sentinel": 0.6,
            "executor": 0.5,
        },
        mode_affinity={
            "deliberative": 0.95,
            "reflective": 0.85,
            "exploratory": 0.7,
            "conversational": 0.6,
            "procedural": 0.4,
            "reactive": 0.3,
        },
        composability={
            "complements": [
                "risk_intelligence",
                "gap_intelligence",
                "planning_intelligence",
                "prioritization_intelligence",
                "research_intelligence",
                "communication_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[
                        InstrumentSpec(slug="problem-space-modeling", fallback_slug="first-principles"),
                        InstrumentSpec(slug="product-strategy-fit", fallback_slug="problem-space-modeling"),
                    ],
                    min_depth=1,
                    output_schema="actual_decision, constraints, non_negotiables, strategy_fit_verdict",
                    pattern="pipeline",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[
                        InstrumentSpec(slug="leverage-analysis", fallback_slug="mece"),
                        InstrumentSpec(slug="prioritization-sequencing", fallback_slug="leverage-analysis"),
                    ],
                    min_depth=1,
                    output_schema="high_leverage_efforts_ranked, ice_scores, dependency_order",
                    pattern="pipeline",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[
                        InstrumentSpec(slug="strategy-pairwise", fallback_slug="pairwise-comparison"),
                        InstrumentSpec(slug="market-positioning", fallback_slug="strategy-pairwise"),
                    ],
                    min_depth=3,
                    output_schema="chosen_path_given_stage_buyer_constraints, positioning_impact",
                    pattern="pipeline",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="second-order-thinking", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="second_third_order_consequences",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[
                        InstrumentSpec(slug="optionality-assessment", fallback_slug="allocation"),
                        InstrumentSpec(slug="product-risk-assessment", fallback_slug="optionality-assessment"),
                    ],
                    min_depth=2,
                    output_schema="decisions_that_preserve_vs_close_options, risk_register",
                    pattern="pipeline",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="negative-space-reasoning", fallback_slug="inversion")],
                    min_depth=4,
                    output_schema="what_not_to_do, missing_from_plan",
                    pattern="solo",
                ),
            ]
        ),
    )
