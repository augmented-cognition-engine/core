"""product_decision_intelligence — the open extension's recipe.

Five phases with product-reasoning identity (not generic decision-making
process labels):

  1. Frame      — what are we actually deciding? (product-framing instrument)
  2. Reality    — what does this displace in the existing product/roadmap?
  3. Voices     — engage a PM + Skeptic + User-Advocate team in parallel
                  (multi-voice-engage wraps execute_engagement)
  4. Tradeoffs  — what's gained, lost, killed if we commit
  5. Recommend  — bounded recommendation: do X, abandon if Y or Z (kill criteria)

The identity lives in Reality (displacement / opportunity cost), Voices (a real
team in a phase, not just framing labels), and Recommend's kill criteria.
"""

from core.engine.cognition.models import InstrumentSpec, MetaSkill, MetaSkillRecipe, RecipePhase


def get_meta_skill() -> MetaSkill:
    return MetaSkill(
        slug="product_decision_intelligence",
        name="Product Decision Intelligence",
        description=(
            "Reasons through a product decision with the partner-team thesis baked in: "
            "frame the decision, check it against product reality, engage a multi-voice "
            "team, name the tradeoffs, and recommend with explicit kill criteria."
        ),
        domain_intelligences=["product", "product_strategy"],
        recipe=MetaSkillRecipe(
            phases=[
                # 1. Frame — what are we actually deciding?
                RecipePhase(
                    cognitive_function="frame",
                    instruments=[
                        InstrumentSpec(slug="product-framing", fallback_slug="first-principles"),
                    ],
                    min_depth=1,
                    output_schema="decision, success_measure, scope_boundary",
                    pattern="solo",
                ),
                # 2. Reality — what does this displace? what's the opportunity cost?
                RecipePhase(
                    cognitive_function="assess",
                    instruments=[
                        InstrumentSpec(slug="constraint-mapping", fallback_slug="mece"),
                    ],
                    min_depth=1,
                    output_schema="what_breaks, what_enables, what_it_costs_in_roadmap",
                    pattern="solo",
                ),
                # 3. Voices — multi-archetype team in parallel (PM, Skeptic, User-Advocate).
                # This is the partnership thesis in a recipe phase. The instrument
                # wraps execute_engagement; see extensions/reference/instruments/multi_voice_engage.py.
                RecipePhase(
                    cognitive_function="engage",
                    instruments=[
                        InstrumentSpec(slug="multi-voice-engage", fallback_slug="first-principles"),
                    ],
                    min_depth=2,
                    output_schema="pm_take, skeptic_take, ux_advocate_take, merged_output",
                    pattern="parallel",
                ),
                # 4. Tradeoffs — gained / lost / killed.
                RecipePhase(
                    cognitive_function="prioritize",
                    instruments=[
                        InstrumentSpec(slug="pairwise-comparison", fallback_slug="mece"),
                    ],
                    min_depth=2,
                    output_schema="gained, lost, killed",
                    pattern="solo",
                ),
                # 5. Recommend with kill criteria — bounded commitment.
                RecipePhase(
                    cognitive_function="recommend",
                    instruments=[
                        InstrumentSpec(slug="holistic-validation", fallback_slug="first-principles"),
                    ],
                    min_depth=3,
                    output_schema="recommendation, kill_criteria",
                    pattern="solo",
                ),
            ]
        ),
        min_execution_depth=2,
    )
