from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="operational_intelligence",
        name="Operational Intelligence",
        description="Structures operational tasks with workflow modeling, process bottleneck identification, handoff completeness validation, and process debt detection.",
        domain_intelligences=["deployment", "devops", "configuration"],
        activation_signals=[
            "deploy",
            "ship",
            "release",
            "ops",
            "devops",
            "pipeline",
            "CI",
            "CD",
            "infrastructure",
            "workflow",
            "process",
            "runbook",
            "on-call",
            "incident",
            "automation",
            "cadence",
            "rollout",
        ],
        archetype_affinity={
            "executor": 0.85,
            "sentinel": 0.8,
            "analyst": 0.7,
            "advisor": 0.7,
            "creator": 0.55,
            "researcher": 0.5,
        },
        mode_affinity={
            "procedural": 0.9,
            "deliberative": 0.75,
            "reflective": 0.7,
            "reactive": 0.65,
            "conversational": 0.5,
            "exploratory": 0.5,
        },
        composability={
            "complements": [
                "systems_intelligence",
                "coding_intelligence",
                "risk_intelligence",
                "verification_intelligence",
                "tool_intelligence",
                "coordination_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="workflow-modeling", fallback_slug="systems-dynamics")],
                    min_depth=1,
                    output_schema="process_steps_gates",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="process-bottleneck", fallback_slug="bottleneck-analysis")],
                    min_depth=1,
                    output_schema="where_work_gets_stuck_handoff_gaps",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="workflow-optimization", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="parallelize_reorder_eliminate_steps",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="handoff-completeness", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="next_step_has_everything_it_needs",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="cadence-awareness", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="sprint_vs_daily_vs_adhoc_rhythm",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="process-debt", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="process_helping_vs_ceremony",
                    pattern="solo",
                ),
            ]
        ),
    )
