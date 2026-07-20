from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase, ToolSpec


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="data_intelligence",
        name="Data Intelligence",
        description="Structures data tasks with anomaly framing, metric design, Bayesian updating, baseline comparison, and statistical confidence allocation.",
        domain_intelligences=["data", "data_modeling", "observability"],
        activation_signals=[
            "data",
            "metric",
            "analytics",
            "measure",
            "statistics",
            "dashboard",
            "observability",
            "anomaly",
            "pattern",
            "trend",
            "baseline",
            "signal",
            "calibration",
            "confidence",
            "A/B",
            "sample size",
            "posterior",
            "Bayesian",
            "schema",
            "table",
        ],
        archetype_affinity={
            "analyst": 0.95,
            "researcher": 0.8,
            "sentinel": 0.75,
            "advisor": 0.65,
            "executor": 0.5,
            "creator": 0.4,
        },
        mode_affinity={
            "reflective": 0.9,
            "deliberative": 0.85,
            "exploratory": 0.75,
            "procedural": 0.6,
            "reactive": 0.5,
            "conversational": 0.4,
        },
        composability={
            "complements": [
                "research_intelligence",
                "evaluation_intelligence",
                "systems_intelligence",
                "operational_intelligence",
                "gap_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="anomaly-framing", fallback_slug="first-principles")],
                    min_depth=1,
                    output_schema="unusual_patterns, unasked_questions",
                    tools=[ToolSpec(fallback_slug="ace_search")],
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="metric-design", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="metrics_that_answer_actual_question",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="bayesian-reasoning", fallback_slug="hypothesis-driven")],
                    min_depth=3,
                    output_schema="posterior_belief, prior_likelihood_evidence",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="comparison-baseline", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="compared_to_what, sample_size_sufficient",
                    tools=[ToolSpec(fallback_slug="ace_load")],
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="statistical-confidence", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="confidence_levels, uncertainty_ranges",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="three-mode-critique", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema=(
                        "per_dimension_scores {survivorship_bias, vanity_metrics, false_precision, "
                        "baseline_validity} — each 0-3 severity with a one-line behavioral anchor; findings"
                    ),
                    must_verify=[
                        "every dimension (survivorship_bias, vanity_metrics, false_precision, "
                        "baseline_validity) is scored 0-3 for severity with a one-line behavioral "
                        "justification grounded in the data",
                        "any dimension scoring 2 or above names the specific correction needed",
                    ],
                    pattern="pipeline",
                ),
            ]
        ),
    )
