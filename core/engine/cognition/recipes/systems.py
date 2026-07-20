from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="systems_intelligence",
        name="Systems Intelligence",
        description="Structures systems design with scaling architecture knowledge, capacity planning, cost-aware resource allocation, and incident-response-informed critique.",
        domain_intelligences=[
            "architecture",
            "performance",
            "integration",
            "dependency_management",
            "scale",
            "deployment",
            "observability",
        ],
        activation_signals=[
            "architecture",
            "system",
            "scale",
            "performance",
            "throughput",
            "latency",
            "capacity",
            "infrastructure",
            "integration",
            "dependency",
            "distributed",
            "deploy",
            "observability",
            "monitoring",
            "cascade",
            "bottleneck",
            "feedback loop",
            "1x 10x 100x",
            "topology",
            "boundary",
        ],
        archetype_affinity={
            "analyst": 0.9,
            "advisor": 0.85,
            "sentinel": 0.8,
            "creator": 0.75,
            "executor": 0.65,
            "researcher": 0.6,
        },
        mode_affinity={
            "deliberative": 0.95,
            "reflective": 0.85,
            "exploratory": 0.7,
            "procedural": 0.6,
            "conversational": 0.5,
            "reactive": 0.4,
        },
        composability={
            "complements": [
                "coding_intelligence",
                "risk_intelligence",
                "operational_intelligence",
                "evaluation_intelligence",
                "data_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[
                        InstrumentSpec(slug="systems-dynamics", fallback_slug="first-principles"),
                        InstrumentSpec(slug="scaling-architecture", fallback_slug="systems-dynamics"),
                    ],
                    min_depth=1,
                    output_schema="feedback_loops, scaling_zones, reinforcing, balancing",
                    pattern="pipeline",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[
                        InstrumentSpec(slug="capacity-planning", fallback_slug="bottleneck-analysis"),
                    ],
                    min_depth=1,
                    output_schema="constraint_location, capacity_headroom, downstream_effect_of_moving_it",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="architecture-pairwise", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="chosen_option_at_1x_10x_100x_failure",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[
                        InstrumentSpec(slug="scaling-projection", fallback_slug="second-order-thinking"),
                        InstrumentSpec(slug="migration-evolution", fallback_slug="scaling-projection"),
                    ],
                    min_depth=3,
                    output_schema="scaling_breaks_at_x, migration_compatibility",
                    pattern="pipeline",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[
                        InstrumentSpec(slug="cost-engineering", fallback_slug="failure-budget"),
                    ],
                    min_depth=2,
                    output_schema="cost_per_unit, redundancy_vs_simplicity_per_component",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[
                        InstrumentSpec(slug="failure-cascade", fallback_slug="fmea"),
                        InstrumentSpec(slug="incident-response", fallback_slug="failure-cascade"),
                    ],
                    min_depth=4,
                    output_schema="cascade_chains, single_points_of_failure, incident_detection_gaps",
                    pattern="pipeline",
                ),
            ]
        ),
    )
