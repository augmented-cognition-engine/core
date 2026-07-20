from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="research_intelligence",
        name="Research Intelligence",
        description="Structures research tasks with hypothesis-driven framing, evidence hierarchy, source comparison, and synthesis coherence validation.",
        domain_intelligences=["research", "analysis"],
        activation_signals=[
            "research",
            "investigate",
            "hypothesis",
            "evidence",
            "source",
            "study",
            "learn",
            "discover",
            "understand",
            "find out",
            "explore",
            "survey",
            "prior art",
            "benchmark",
            "comparison",
            "literature",
            "what does the field say",
        ],
        archetype_affinity={
            "researcher": 0.95,
            "analyst": 0.85,
            "advisor": 0.7,
            "creator": 0.6,
            "sentinel": 0.5,
            "executor": 0.4,
        },
        mode_affinity={
            "exploratory": 0.95,
            "deliberative": 0.85,
            "reflective": 0.7,
            "conversational": 0.5,
            "procedural": 0.4,
            "reactive": 0.3,
        },
        composability={
            "complements": [
                "evaluation_intelligence",
                "gap_intelligence",
                "communication_intelligence",
                "memory_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="hypothesis-driven", fallback_slug="first-principles")],
                    min_depth=1,
                    output_schema="hypothesis, falsification_criteria",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="evidence-hierarchy", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="source_types_ranked_by_confidence_impact",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="structured-comparison", fallback_slug="pairwise-comparison")],
                    min_depth=3,
                    output_schema="applicable_evidence, conflicting_evidence_resolved",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="synthesis-coherence", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="synthesis_holds, codebase_consistency_check",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="confidence-allocation", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="confidence_budget_per_finding",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="three-mode-critique", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    output_schema="diagnostic_gaps, generative_angles, synthesis_refinements",
                    pattern="pipeline",
                ),
            ]
        ),
    )
