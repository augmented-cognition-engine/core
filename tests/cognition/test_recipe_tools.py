# tests/cognition/test_recipe_tools.py
"""The three builder branches declare their purpose-built tools per phase.

Grounds the advisory tool-binding mechanism in real recipes: coding/data/design
phases carry the frontier-scan toolkits, and the design tools exist in the catalog.
"""

from core.engine.cognition.recipes import coding, creative, data
from core.engine.cognition.tool_catalog import TOOL_CATALOG


def _phase(skill, fn):
    return next(p for p in skill.recipe.phases if p.cognitive_function == fn)


def _slugs(phase):
    return [t.slug or t.fallback_slug for t in phase.tools]


# --- coding_intelligence -----------------------------------------------------


def test_coding_frame_binds_structural_orientation():
    s = coding.get_meta_skill()
    assert "ace_code_context" in _slugs(_phase(s, "frame"))


def test_coding_validate_binds_blast_radius():
    s = coding.get_meta_skill()
    validate = _slugs(_phase(s, "validate"))
    assert "ace_blast_radius" in validate
    assert "ace_diff_impact" in validate


def test_coding_critique_binds_pr_review():
    s = coding.get_meta_skill()
    assert "ace_pr_review" in _slugs(_phase(s, "critique"))


# --- data_intelligence -------------------------------------------------------


def test_data_frame_binds_search():
    s = data.get_meta_skill()
    assert "ace_search" in _slugs(_phase(s, "frame"))


def test_data_validate_binds_load():
    s = data.get_meta_skill()
    assert "ace_load" in _slugs(_phase(s, "validate"))


# --- creative_intelligence (design) ------------------------------------------


def test_creative_frame_binds_refero_research():
    s = creative.get_meta_skill()
    assert "refero_search_screens" in _slugs(_phase(s, "frame"))


def test_creative_validate_binds_figma_code_connect():
    s = creative.get_meta_skill()
    assert "figma_code_connect" in _slugs(_phase(s, "validate"))


# --- catalog -----------------------------------------------------------------


def test_design_tools_present_in_catalog():
    for slug in ("refero_search_screens", "shadcn_registry_search", "figma_code_connect"):
        assert slug in TOOL_CATALOG, f"{slug} missing from TOOL_CATALOG"


# --- design critique rubric ---------------------------------------------------


def test_creative_critique_uses_per_dimension_rubric():
    """Design critique must score named perceptual dimensions (not free-form vibes)."""
    crit = _phase(creative.get_meta_skill(), "critique")
    schema = crit.output_schema
    for dim in (
        "perceptual_hierarchy",
        "rhythm",
        "affordance",
        "typographic_tension",
        "spatial_grammar",
    ):
        assert dim in schema, f"{dim} missing from critique output_schema"


def test_creative_critique_enforces_behavioral_anchors():
    """The rubric must demand 0-3 scoring with behavioral justification, not opinion."""
    crit = _phase(creative.get_meta_skill(), "critique")
    joined = " ".join(crit.must_verify)
    assert "0-3" in joined
    assert "behavioral" in joined.lower()


def test_coding_critique_uses_per_dimension_rubric():
    crit = _phase(coding.get_meta_skill(), "critique")
    for dim in ("correctness", "security", "integration_safety", "simplicity"):
        assert dim in crit.output_schema, f"{dim} missing from coding critique schema"
    joined = " ".join(crit.must_verify)
    assert "0-3" in joined and "behavioral" in joined.lower()


def test_data_critique_uses_per_dimension_rubric():
    crit = _phase(data.get_meta_skill(), "critique")
    for dim in ("survivorship_bias", "vanity_metrics", "false_precision", "baseline_validity"):
        assert dim in crit.output_schema, f"{dim} missing from data critique schema"
    joined = " ".join(crit.must_verify)
    assert "0-3" in joined and "behavioral" in joined.lower()
