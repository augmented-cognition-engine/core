from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase, ToolSpec


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="coding_intelligence",
        name="Coding Intelligence",
        description="Structures coding tasks with tradeoff-aware framing, constraint-first reasoning, design pattern selection, integration validation, and security-aware critique.",
        domain_intelligences=["coding", "architecture", "api_design", "business_logic", "code_conventions"],
        activation_signals=[
            "code",
            "implement",
            "build",
            "refactor",
            "function",
            "class",
            "module",
            "api",
            "endpoint",
            "service",
            "library",
            "package",
            "database",
            "schema",
            "query",
            "logic",
            "algorithm",
            "fix",
            "bug",
            "patch",
            "test",
            "deploy",
            "tech debt",
            "migration",
            "integration",
            "ship",
            "wire",
        ],
        archetype_affinity={
            "executor": 0.95,
            "creator": 0.8,
            "analyst": 0.7,
            "sentinel": 0.6,
            "advisor": 0.5,
            "researcher": 0.4,
        },
        mode_affinity={
            "deliberative": 0.85,
            "procedural": 0.8,
            "reactive": 0.7,
            "reflective": 0.65,
            "exploratory": 0.5,
            "conversational": 0.4,
        },
        composability={
            "complements": [
                "systems_intelligence",
                "evaluation_intelligence",
                "verification_intelligence",
                "creative_intelligence",
                "risk_intelligence",
            ],
            "conflicts": [],
        },
        recipe=MetaSkillRecipe(
            phases=[
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[
                        InstrumentSpec(slug="constraint-theory", fallback_slug="first-principles"),
                        InstrumentSpec(slug="core-tradeoffs", fallback_slug="constraint-theory"),
                    ],
                    min_depth=1,
                    signature=0.7,
                    output_schema=(
                        "real_constraints, active_tradeoffs, hot_path, public_api_surface, "
                        "architectural_layer, boundary_constraints, realized_capability"
                    ),
                    tools=[
                        ToolSpec(fallback_slug="ace_code_context"),
                        ToolSpec(fallback_slug="ace_module_coupling"),
                    ],
                    pattern="pipeline",
                    must_not=[
                        "propose any solution before all constraints are identified",
                        "assume the caller's interface is flexible when it is an existing public API",
                        "skip identifying what must NOT change in this codebase",
                        "violate the detected architectural layer boundary",
                    ],
                    must_verify=[
                        "the hot path is genuinely hot — check blast radius before claiming it",
                        "the public API surface is the minimum that satisfies the requirement",
                        "the architectural_layer is derived from the module graph, not assumed",
                    ],
                ),
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[InstrumentSpec(slug="approach-maxdiff", fallback_slug="mece")],
                    min_depth=1,
                    output_schema="best_approach, worst_approach, why",
                    pattern="solo",
                    signature=0.5,
                    must_not=[
                        "present approaches that violate any constraint identified in the frame phase",
                        "recommend the most complex approach without justifying why simpler ones fail",
                    ],
                    must_verify=[
                        "the worst approach has at least one specific failure mode demonstrated against the stated constraints",
                    ],
                ),
                RecipePhase(
                    cognitive_function="choose",
                    instruments=[
                        InstrumentSpec(slug="codebase-comparison", fallback_slug="pairwise-comparison"),
                        InstrumentSpec(slug="design-pattern-selection", fallback_slug="codebase-comparison"),
                    ],
                    min_depth=3,
                    output_schema="chosen_approach_given_consumers_and_history, pattern_fit_assessment",
                    tools=[
                        ToolSpec(fallback_slug="ace_module_coupling"),
                        ToolSpec(fallback_slug="ace_dependency_chain"),
                    ],
                    pattern="pipeline",
                    signature=0.7,
                    must_not=[
                        "choose an approach that hasn't been validated against existing codebase patterns",
                        "reverse a rejection from the prioritize phase without explicitly stating why the constraint no longer applies",
                    ],
                    must_verify=[
                        "the chosen approach is consistent with how similar problems were solved in this codebase",
                    ],
                ),
                RecipePhase(
                    cognitive_function="validate",
                    instruments=[InstrumentSpec(slug="integration-validation", fallback_slug="holistic-validation")],
                    min_depth=3,
                    output_schema="composability_with_existing_boundaries",
                    tools=[
                        ToolSpec(fallback_slug="ace_blast_radius"),
                        ToolSpec(fallback_slug="ace_diff_impact"),
                    ],
                    pattern="solo",
                    signature=0.9,
                    must_not=[
                        "validate only the happy path",
                        "ignore error handling and rollback scenarios",
                    ],
                    must_verify=[
                        "every caller of the affected code still works with the proposed change",
                        "the change does not break existing test contracts",
                    ],
                ),
                RecipePhase(
                    cognitive_function="review",
                    instruments=[
                        InstrumentSpec(slug="graph-grounded-review", fallback_slug="integration-validation"),
                    ],
                    min_depth=3,
                    signature=0.9,
                    output_schema=("unresolved_callers, hotspot_touched, moved_capabilities, graph_verdict"),
                    tools=[
                        ToolSpec(fallback_slug="ace_blast_radius"),
                        ToolSpec(fallback_slug="ace_dependency_chain"),
                        ToolSpec(fallback_slug="ace_pr_review"),
                    ],
                    pattern="pipeline",
                    must_not=[
                        "declare the change safe without checking caller edges in the graph",
                        "treat an empty or unscanned graph as a pass",
                    ],
                    must_verify=[
                        "every caller edge (imports / related_to) still resolves after the change",
                        "if the graph is empty or unscanned, graph_verdict is 'cannot verify' — never a silent pass",
                        "a touched hotspot (high change_frequency) is called out explicitly",
                    ],
                ),
                RecipePhase(
                    cognitive_function="allocate",
                    instruments=[InstrumentSpec(slug="complexity-budget", fallback_slug="allocation")],
                    min_depth=2,
                    output_schema="careful_architecture_vs_simple_impl_split",
                    pattern="solo",
                    signature=0.5,
                ),
                RecipePhase(
                    cognitive_function="critique",
                    instruments=[
                        InstrumentSpec(slug="three-mode-critique", fallback_slug="adversarial-testing"),
                        InstrumentSpec(slug="security-coding", fallback_slug="adversarial-testing"),
                    ],
                    min_depth=4,
                    output_schema=(
                        "per_dimension_scores {correctness, security, integration_safety, simplicity} "
                        "— each 0-3 with a one-line behavioral anchor; correctness_issues; "
                        "security_risks; alternative_approaches; polish_items"
                    ),
                    must_verify=[
                        "every dimension (correctness, security, integration_safety, simplicity) is "
                        "scored 0-3 with a one-line behavioral justification — cite the specific code, not a vibe",
                        "any dimension scoring below 2 names a concrete fix, not a general comment",
                    ],
                    tools=[ToolSpec(fallback_slug="ace_pr_review")],
                    pattern="pipeline",
                    signature=0.9,
                ),
            ]
        ),
    )
