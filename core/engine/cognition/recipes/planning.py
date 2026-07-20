from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="planning_intelligence",
        name="Planning Intelligence",
        description="Structures planning tasks with dependency mapping, risk-first ordering, parallelization assessment, and scope negotiation.",
        domain_intelligences=["planning", "project_management"],
        activation_signals=[
            "plan",
            "sequence",
            "roadmap",
            "milestone",
            "sprint",
            "dependency",
            "schedule",
            "ordering",
            "when",
            "deliverable",
            "scope",
            "breakdown",
            "phases",
            "what comes first",
            "critical path",
            "parallelize",
        ],
        archetype_affinity={
            "executor": 0.85,
            "advisor": 0.85,
            "analyst": 0.75,
            "sentinel": 0.7,
            "creator": 0.6,
            "researcher": 0.5,
        },
        mode_affinity={
            "deliberative": 0.9,
            "procedural": 0.85,
            "reflective": 0.75,
            "exploratory": 0.55,
            "conversational": 0.5,
            "reactive": 0.4,
        },
        composability={
            "complements": [
                "risk_intelligence",
                "coordination_intelligence",
                "prioritization_intelligence",
                "strategic_intelligence",
                "delegation_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="dependency-mapping", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="dependency_graph, what_unblocks_other_work",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[
                        InstrumentSpec(slug="risk-first-ordering", fallback_slug="fmea"),
                        InstrumentSpec(slug="prioritization-sequencing", fallback_slug="risk-first-ordering"),
                    ],
                    min_depth=1,
                    output_schema="risky_assumptions_ordered_first, ice_scores, dependency_dag",
                    pattern="pipeline",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[
                        InstrumentSpec(slug="parallelization-assessment", fallback_slug="pairwise-comparison")
                    ],
                    min_depth=3,
                    output_schema="concurrent_vs_sequential_tasks",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="plan-coherence", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="steps_produce_stated_goal",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="effort-distribution", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="careful_vs_quick_execution_per_task",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="scope-negotiation", fallback_slug="inversion")],
                    min_depth=4,
                    output_schema="deferrable_cuttable_items",
                    pattern="solo",
                ),
            ]
        ),
    )
