from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="risk_intelligence",
        name="Risk Intelligence",
        description="Structures risk assessment with FMEA failure mode identification, reversibility assessment, mitigation strategy comparison, and blast radius review.",
        domain_intelligences=["risk", "security"],
        activation_signals=[
            "risk",
            "failure",
            "breakage",
            "what could go wrong",
            "blast radius",
            "reversible",
            "irreversible",
            "mitigation",
            "contingency",
            "fallback",
            "danger",
            "security",
            "vulnerability",
            "FMEA",
            "worst case",
            "checkpoint",
            "assumption",
        ],
        archetype_affinity={
            "sentinel": 0.95,
            "advisor": 0.85,
            "analyst": 0.8,
            "executor": 0.65,
            "researcher": 0.55,
            "creator": 0.5,
        },
        mode_affinity={
            "deliberative": 0.9,
            "reflective": 0.85,
            "procedural": 0.7,
            "reactive": 0.7,
            "exploratory": 0.6,
            "conversational": 0.55,
        },
        composability={
            "complements": [
                "evaluation_intelligence",
                "verification_intelligence",
                "systems_intelligence",
                "strategic_intelligence",
                "planning_intelligence",
                "coding_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="fmea", fallback_slug="first-principles")],
                    min_depth=1,
                    output_schema="failure_modes_identified",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="reversibility-assessment", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="can_be_undone, blast_radius",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="mitigation-pairwise", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="prevention_vs_detection_vs_recovery_strategy",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="assumption-identification", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="assumptions_tested_before_building_on_them",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="checkpoint-placement", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="validate_before_proceeding_checkpoints",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="blast-radius-review", fallback_slug="fmea")],
                    min_depth=4,
                    output_schema="worst_case_severity, who_is_affected",
                    pattern="solo",
                ),
            ]
        ),
    )
