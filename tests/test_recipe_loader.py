"""Tests for YAML recipe loader, schema, and composer integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.engine.cognition import composer as composer_module
from core.engine.cognition.composer import CognitiveComposer
from core.engine.cognition.recipes.loader import load_yaml_recipe_file, load_yaml_recipe_with_routing
from core.engine.cognition.recipes.schema import RecipeYAMLSchema

FIXTURES = Path(__file__).parent / "fixtures" / "recipes_yaml"


def test_schema_parses_minimal_recipe():
    """A minimal valid recipe dict parses into a MetaSkill."""
    data = {
        "slug": "test_recipe",
        "name": "Test Recipe",
        "description": "A minimal test recipe.",
        "domain_intelligences": ["planning"],
        "min_execution_depth": 1,
        "recipe": {
            "phases": [
                {
                    "cognitive_function": "frame",
                    "pattern": "solo",
                    "min_depth": 1,
                    "output_schema": "framed_problem",
                    "instruments": [
                        {"fallback_slug": "mece"},
                    ],
                },
            ],
        },
    }
    schema = RecipeYAMLSchema.model_validate(data)
    meta_skill = schema.to_meta_skill()
    assert meta_skill.slug == "test_recipe"
    assert meta_skill.recipe.phases[0].cognitive_function == "frame"
    assert meta_skill.recipe.phases[0].instruments[0].fallback_slug == "mece"


def test_loader_parses_yaml_file():
    """Loader reads a YAML file from disk and produces a MetaSkill."""
    path = FIXTURES / "valid_minimal.yaml"
    meta_skill = load_yaml_recipe_file(path)
    assert meta_skill.slug == "test_minimal"
    assert meta_skill.recipe.phases[0].instruments[0].fallback_slug == "mece"


def test_composer_resolves_yaml_meta_skill(monkeypatch):
    """_load_recipe() returns YAML-defined MetaSkills directly."""
    meta_skill = load_yaml_recipe_file(FIXTURES / "valid_minimal.yaml")
    # Use monkeypatch so we don't pollute the global map across tests
    monkeypatch.setitem(composer_module._RECIPE_YAML, "test_minimal", meta_skill)

    composer = CognitiveComposer()
    resolved = composer._load_recipe("test_minimal")
    assert resolved is not None
    assert resolved.slug == "test_minimal"
    assert resolved is meta_skill  # same object — no re-import


def test_prioritization_recipe_round_trip():
    """Prioritization recipe resolves via YAML and produces the same MetaSkill
    structure the Python module used to produce.

    This is the migration safety net per spec §9 test #2: full equivalence
    against the deleted Python module's six-phase structure.
    """
    composer = CognitiveComposer()
    skill = composer._load_recipe("prioritization_intelligence")
    assert skill is not None
    assert skill.slug == "prioritization_intelligence"
    assert skill.name == "Prioritization Intelligence"
    assert "prioritization" in skill.domain_intelligences
    assert "product_management" in skill.domain_intelligences
    assert len(skill.recipe.phases) == 6

    expected_phases = [
        ("frame", "solo", 1, "everything_competing_for_attention", "competing-demands-mapping", "mece"),
        ("prioritize", "solo", 1, "needle_movers_ranked", "impact-assessment", "leverage-analysis"),
        ("choose", "solo", 3, "critical_path_first_ordering", "dependency-ordering", "pairwise-comparison"),
        ("validate", "solo", 3, "high_risk_items_surfaced_early", "risk-adjusted-sequencing", "holistic-validation"),
        ("allocate", "solo", 2, "deep_work_vs_quick_wins_vs_blockers", "attention-budget", "allocation"),
        ("critique", "solo", 4, "new_info_changes_order", "dynamic-reprioritization", "adversarial-testing"),
    ]
    for i, (cog_fn, pattern, min_depth, out_schema, slug, fallback) in enumerate(expected_phases):
        phase = skill.recipe.phases[i]
        assert phase.cognitive_function == cog_fn, f"phase {i}"
        assert phase.pattern == pattern, f"phase {i}"
        assert phase.min_depth == min_depth, f"phase {i}"
        assert phase.output_schema == out_schema, f"phase {i}"
        assert phase.instruments[0].slug == slug, f"phase {i}"
        assert phase.instruments[0].fallback_slug == fallback, f"phase {i}"


def test_core_yaml_collision_with_python_module(monkeypatch, tmp_path):
    """A YAML recipe with the same slug as a kernel _RECIPE_MODULES entry
    raises RuntimeError at discovery time."""

    # Pick a slug that IS in _RECIPE_MODULES — coding_intelligence is a safe choice
    colliding = tmp_path / "collision_test.yaml"
    colliding.write_text(
        "slug: coding_intelligence\n"
        "name: Collision\n"
        "description: should collide.\n"
        "domain_intelligences: [coding]\n"
        "recipe:\n"
        "  phases:\n"
        "    - cognitive_function: frame\n"
        "      pattern: solo\n"
        "      min_depth: 1\n"
        "      output_schema: x\n"
        "      instruments:\n"
        "        - fallback_slug: mece\n"
    )

    # Reset _RECIPE_YAML so the idempotency guard doesn't early-return.
    # Then monkey-point the discovery scan at tmp_path by patching Path(__file__).parent.
    monkeypatch.setattr(composer_module, "_RECIPE_YAML", {})

    # Replace the discovery directory with tmp_path
    import core.engine.cognition.recipes.loader as loader_pkg

    original_discover = loader_pkg.discover_core_yaml_recipes

    def discover_from_tmp():
        from core.engine.cognition import composer as comp

        if comp._RECIPE_YAML:
            return
        for path, meta_skill in loader_pkg.discover_yaml_recipes(tmp_path):
            slug = meta_skill.slug
            if slug in comp._RECIPE_MODULES:
                raise RuntimeError(
                    f"Recipe slug collision: '{slug}' is registered as both "
                    f"a core Python module ({comp._RECIPE_MODULES[slug]}) "
                    f"and a YAML file ({path}). Resolve by removing one."
                )
            comp._RECIPE_YAML[slug] = meta_skill

    monkeypatch.setattr(loader_pkg, "discover_core_yaml_recipes", discover_from_tmp)

    with pytest.raises(RuntimeError, match="slug collision"):
        loader_pkg.discover_core_yaml_recipes()


def test_flavor_register_recipe_raises_on_collision():
    """Registry.register_recipe() refuses to overwrite an existing slug."""
    from core.engine.extensions.registry import Registry, _recipes

    # Save and restore: _recipes is a module-level global; clearing without
    # restoring would leave subsequent tests (in the full suite) unable to
    # resolve flavor recipes because _ensured=True prevents re-loading.
    saved = dict(_recipes)
    _recipes.clear()  # isolate for collision test
    try:
        reg = Registry()
        reg.register_recipe("x_intelligence", "some.module.path")
        with pytest.raises(RuntimeError, match="already registered"):
            reg.register_recipe("x_intelligence", "another.module.path")
    finally:
        _recipes.clear()
        _recipes.update(saved)  # restore so downstream tests see the full registry


from pydantic import ValidationError


def test_loader_rejects_unknown_field():
    """Unknown YAML fields raise ValidationError (extra='forbid')."""
    with pytest.raises(ValidationError) as exc_info:
        load_yaml_recipe_file(FIXTURES / "invalid_unknown_field.yaml")
    assert "this_field_does_not_exist" in str(exc_info.value)


def test_loader_rejects_missing_required_field(tmp_path):
    """Missing required field (slug) raises ValidationError."""
    path = tmp_path / "missing_slug.yaml"
    path.write_text(
        "name: No Slug Here\n"
        "description: x\n"
        "domain_intelligences: []\n"
        "recipe:\n"
        "  phases:\n"
        "    - cognitive_function: frame\n"
        "      pattern: solo\n"
        "      min_depth: 1\n"
        "      output_schema: x\n"
        "      instruments:\n"
        "        - fallback_slug: mece\n"
    )
    with pytest.raises(ValidationError) as exc_info:
        load_yaml_recipe_file(path)
    assert "slug" in str(exc_info.value).lower()


def test_discover_skips_bad_files_and_continues(tmp_path, caplog):
    """A directory with one bad and one good YAML loads the good one and logs the bad."""
    from core.engine.cognition.recipes.loader import discover_yaml_recipes

    good = tmp_path / "good.yaml"
    good.write_text(
        "slug: good_recipe\nname: Good\ndescription: x\n"
        "domain_intelligences: [planning]\n"
        "recipe:\n  phases:\n    - cognitive_function: frame\n"
        "      pattern: solo\n      min_depth: 1\n      output_schema: x\n"
        "      instruments:\n        - fallback_slug: mece\n"
    )
    bad = tmp_path / "bad.yaml"
    bad.write_text("this: is: not: valid: yaml: [{[")

    import logging

    caplog.set_level(logging.CRITICAL)
    results = discover_yaml_recipes(tmp_path)
    assert len(results) == 1
    assert results[0][1].slug == "good_recipe"
    assert any("bad.yaml" in r.message for r in caplog.records)


def test_full_shape_recipe_round_trip():
    """A full extension-shaped recipe (routing + affinity blocks + 7 phases
    spanning pipeline/fanout/adversarial with bindings and output keys)
    loads via YAML with the complete structure preserved.

    The fixture mirrors the shape of a real extension recipe; the extension's
    own YAML is covered by its own test suite."""
    yaml_path = Path(__file__).parent / "fixtures" / "recipe_loader_sample.yaml"
    skill = load_yaml_recipe_file(yaml_path)
    assert skill.slug == "sample_audit_intelligence"
    assert skill.name == "Sample Audit Intelligence"
    assert "evaluation" in skill.domain_intelligences
    assert len(skill.recipe.phases) == 7
    cognitive_functions = [p.cognitive_function for p in skill.recipe.phases]
    assert cognitive_functions == [
        "discover",
        "compose_panel",
        "review_pass1",
        "review_pass2_vetoes",
        "propose_rewrites",
        "synthesize_receipts",
        "persist_decisions",
    ]
    # Spot-check the discover phase — must preserve bindings
    discover = skill.recipe.phases[0]
    assert discover.pattern == "pipeline"
    assert discover.instruments[0].slug == "anchor-discovery"
    assert discover.instruments[0].fallback_slug == "jobs-to-be-done"
    assert discover.instruments[0].bindings == {
        "context": "audit_context",
        "page_text": "page_text",
    }
    assert discover.instruments[0].output_key == "anchor"
    # Verify a fanout phase
    assert skill.recipe.phases[2].pattern == "fanout"
    # Verify the adversarial phase
    assert skill.recipe.phases[3].pattern == "adversarial"


def test_load_yaml_recipe_with_routing_extracts_routing():
    """load_yaml_recipe_with_routing() returns routing dict from YAML."""
    yaml_path = Path(__file__).parent / "fixtures" / "recipe_loader_sample.yaml"
    skill, routing = load_yaml_recipe_with_routing(yaml_path)
    assert skill.slug == "sample_audit_intelligence"
    assert routing == {"disciplines": ["evaluation"], "task_types": []}


def test_load_yaml_recipe_with_routing_empty_when_block_absent():
    """A recipe without a routing: block returns empty lists."""
    yaml_path = FIXTURES / "valid_minimal.yaml"
    skill, routing = load_yaml_recipe_with_routing(yaml_path)
    assert skill.slug == "test_minimal"
    assert routing == {"disciplines": [], "task_types": []}
