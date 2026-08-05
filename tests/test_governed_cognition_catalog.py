"""E1-A acceptance tests for the canonical governed-cognition read seam."""

from __future__ import annotations

import os
from dataclasses import asdict, replace

import pytest
from pydantic import ValidationError

from core.engine.cognition import composer as composer_module
from core.engine.cognition.catalog import CognitionCatalog, build_default_catalog
from core.engine.cognition.composer import CognitiveComposer
from core.engine.cognition.contracts import (
    RECIPE_BODY_VERSION,
    CognitionIdentityV1,
    CognitionOwnerV1,
    CognitionRevisionV1,
    CognitionScopeV1,
    CognitionSourceV1,
    CognitionType,
    OwnerKind,
    ScopeKind,
)
from core.engine.cognition.legacy_adapters import adapt_all_recipes, meta_skill_from_body
from core.engine.cognition.store import CognitionIdentityConflict


def _owner(namespace: str = "core:test") -> CognitionOwnerV1:
    return CognitionOwnerV1(kind=OwnerKind.CORE, namespace=namespace, provenance="test:1")


def _source(digest: str = "a" * 64) -> CognitionSourceV1:
    return CognitionSourceV1(source_kind="test", locator="test:recipe", content_hash=digest)


def test_stable_identity_is_separate_from_material_revision() -> None:
    identity = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=_owner(),
        stable_key="example_recipe",
    )
    first = CognitionRevisionV1(
        identity=identity,
        body_schema_version=RECIPE_BODY_VERSION,
        body={"name": "first"},
        sources=(_source(),),
        approval_receipt_id="review:test:first",
    )
    second = CognitionRevisionV1(
        identity=identity,
        body_schema_version=RECIPE_BODY_VERSION,
        body={"name": "second"},
        sources=(_source(),),
        approval_receipt_id="review:test:second",
    )
    assert first.identity.cognition_id == second.identity.cognition_id
    assert first.revision_id != second.revision_id
    assert first.material_hash != second.material_hash


def test_identity_changes_when_owner_namespace_changes() -> None:
    core = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=_owner("core:ace"),
        stable_key="same_slug",
    )
    extension = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=CognitionOwnerV1(
            kind=OwnerKind.EXTENSION,
            namespace="extension:example",
            provenance="example:1.0.0",
        ),
        stable_key="same_slug",
    )
    assert core.cognition_id != extension.cognition_id


def test_scope_never_treats_missing_product_as_global() -> None:
    with pytest.raises(ValidationError, match="missing required identifiers"):
        CognitionScopeV1(kind=ScopeKind.PRODUCT)
    with pytest.raises(ValidationError, match="unrelated identifiers"):
        CognitionScopeV1(kind=ScopeKind.CORE_DEFAULT, product_id="product:foreign")


def test_all_current_recipes_cross_one_deterministic_catalog_boundary() -> None:
    first = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    second = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    expected = 22 if os.environ.get("ACE_DISABLE_EXTENSIONS") == "1" else 23
    assert len(first.recipe_slugs()) == expected
    assert first.manifest() == second.manifest()
    assert len(first.store.identities()) == expected
    assert len(first.store.revisions()) == expected
    assert len(first.store.heads()) == expected


def test_runtime_views_round_trip_exact_recipe_bodies() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    for slug in catalog.recipe_slugs():
        runtime = catalog.recipe(slug)
        revision = catalog.recipe_revision(slug)
        assert runtime is not None
        assert revision is not None
        assert revision.body == asdict(runtime)
        assert meta_skill_from_body(revision.body) == runtime


@pytest.mark.skipif(os.environ.get("ACE_DISABLE_EXTENSIONS") == "1", reason="extension-free catalog")
def test_extension_python_instruments_and_framework_fallbacks_are_typed() -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    revision = catalog.recipe_revision("product_decision_intelligence")
    assert revision is not None
    dependencies = {
        (item.cognition_type.value, item.stable_key, item.owner_namespace) for item in revision.dependencies
    }
    assert ("instrument", "product-framing", "extension:product") in dependencies
    assert any(kind == "framework" for kind, _, _ in dependencies)


def test_composer_loads_only_from_injected_catalog(monkeypatch) -> None:
    catalog = build_default_catalog(core_yaml=composer_module._RECIPE_YAML)
    monkeypatch.setattr(composer_module, "_RECIPE_MODULES", {"coding_intelligence": "does.not.exist"})
    monkeypatch.setattr(composer_module, "_RECIPE_YAML", {})
    composer = CognitiveComposer(catalog=catalog)
    recipe = composer._load_recipe("coding_intelligence")
    assert recipe is not None
    assert recipe.slug == "coding_intelligence"


def test_duplicate_runtime_alias_fails_closed() -> None:
    recipes = adapt_all_recipes(core_yaml=composer_module._RECIPE_YAML)
    duplicate = replace(recipes[0])
    with pytest.raises(CognitionIdentityConflict, match="cognition_identity_conflict"):
        CognitionCatalog((recipes[0], duplicate))
