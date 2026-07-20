from core.engine.cognition.models import (
    CaptureSpec,
    ContextQuery,
    InstrumentSpec,
    MetaSkill,
    MetaSkillRecipe,
    RecipePhase,
    ToolSpec,
)


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="creative_intelligence",
        name="Creative/Design Intelligence",
        description="Structures creative and design tasks with aesthetic direction locking, value prioritization, and conjoint validation of design decisions.",
        domain_intelligences=["design", "creative", "ux"],
        # Design tasks are inherently deliberative — never run at depth 1 (reactive).
        # The pairwise-tournament (choose phase) requires depth 2+ to activate.
        min_execution_depth=2,
        activation_signals=[
            "design",
            "ux",
            "user experience",
            "creative",
            "aesthetic",
            "visual",
            "look and feel",
            "brand",
            "interface",
            "ui",
            "component",
            "layout",
            "typography",
            "color",
            "copy",
            "tone",
            "voice",
            "messaging",
            "creative brief",
            "design direction",
            "user journey",
            "interaction",
            "screen",
            "page",
            "canvas",
            "extension surface",
        ],
        archetype_affinity={
            "creator": 0.95,
            "advisor": 0.7,
            "analyst": 0.6,
            "researcher": 0.55,
            "executor": 0.4,
            "sentinel": 0.4,
        },
        mode_affinity={
            "deliberative": 0.9,
            "exploratory": 0.85,
            "reflective": 0.7,
            "conversational": 0.5,
            "procedural": 0.3,
            "reactive": 0.15,
        },
        composability={
            "complements": [
                "communication_intelligence",
                "evaluation_intelligence",
                "research_intelligence",
                "coding_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[InstrumentSpec(slug="context-inference", fallback_slug="first-principles")],
                    min_depth=1,
                    output_schema="domain, product_type, mode, anti_patterns",
                    tools=[ToolSpec(fallback_slug="refero_search_screens")],
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="maxdiff-values", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="top_3_design_values, bottom_3_design_values",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[InstrumentSpec(slug="pairwise-tournament", fallback_slug="pairwise-comparison")],
                    min_depth=2,
                    output_schema="locked_aesthetic_direction",
                    tools=[ToolSpec(fallback_slug="shadcn_registry_search")],
                    pattern="solo",
                    # Load prior ux decisions before running the pairwise tournament.
                    # This prevents redundant direction-locking and informs the LLM
                    # of what has already been decided for this product.
                    load_context=ContextQuery(
                        queries=[
                            "SELECT title, annotation, created_at FROM decision "
                            "WHERE product = <record>$product AND status = 'active' "
                            "AND discipline_hint = 'ux' ORDER BY created_at DESC LIMIT 5"
                        ],
                        inject_as="Prior UX Decisions",
                    ),
                    # After the pairwise tournament runs, persist locked_aesthetic_direction
                    # to the product graph so future sessions can load it.
                    capture_as=CaptureSpec(
                        type="decision",
                        discipline_hint="ux",
                        extract_fields=["locked_aesthetic_direction", "rationale", "alternatives"],
                    ),
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="conjoint-validation", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="bundle_validation_result, ship_decision",
                    tools=[ToolSpec(fallback_slug="figma_code_connect")],
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="investment-allocation", fallback_slug="allocation")],
                    min_depth=3,
                    output_schema="creative_energy_distribution",
                    pattern="solo",
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[InstrumentSpec(slug="three-mode-critique", fallback_slug="adversarial-testing")],
                    min_depth=4,
                    # Per-dimension design rubric: critique scores named perceptual
                    # dimensions with behavioral anchors instead of free-form notes,
                    # so design judgment is comparable and auditable across sessions.
                    output_schema=(
                        "per_dimension_scores {perceptual_hierarchy, rhythm, affordance, "
                        "typographic_tension, spatial_grammar} — each 0-3 with a one-line "
                        "behavioral anchor; diagnostic_issues; generative_alternatives; refinements"
                    ),
                    must_verify=[
                        "every design dimension (perceptual_hierarchy, rhythm, affordance, "
                        "typographic_tension, spatial_grammar) is scored 0-3 with a one-line "
                        "behavioral justification — name the perceptual effect, not a vibe",
                        "any dimension scoring below 2 names a concrete revision, not a general comment",
                    ],
                    pattern="pipeline",
                ),
            ]
        ),
    )
