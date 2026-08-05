"""E1-G current/N-1/future/trust extension cognition conformance."""

from __future__ import annotations

import copy

import pytest

from core.engine.cognition.catalog import build_default_catalog
from core.engine.extensions import registry


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    from core.engine.cognition import instrument_registry

    monkeypatch.setattr(registry, "_recipes", {})
    monkeypatch.setattr(registry, "_recipe_metadata", {})
    monkeypatch.setattr(registry, "_recipe_disciplines", {})
    monkeypatch.setattr(registry, "_recipe_task_types", {})
    monkeypatch.setattr(registry, "_unsupported_registrations", [])
    monkeypatch.setattr(registry, "_ensure_extensions_loaded", lambda: None)
    monkeypatch.setattr(instrument_registry, "_ensure_extensions_loaded", lambda: None)


def _recipe():
    value = build_default_catalog().recipe("coding_intelligence")
    assert value is not None
    return copy.deepcopy(value)


def test_current_reference_negotiates_before_any_registration() -> None:
    from extensions.reference.extension import ProductExtension

    calls: list[str] = []

    class LegacyCoreRegistry:
        def __getattr__(self, name):
            calls.append(name)
            raise AttributeError(name)

    with pytest.raises(RuntimeError, match="requires_pre_registration_negotiation"):
        ProductExtension().register(LegacyCoreRegistry())
    assert calls == ["negotiate_cognition_contract"]


def test_current_contract_negotiation_is_scoped_typed_and_fail_closed() -> None:
    reg = registry.Registry(extension_id="independent", extension_version="2.0.0")
    receipt = reg.negotiate_cognition_contract(
        extension_contract_version=registry.CURRENT_COGNITION_CONTRACT,
        accepted_core_contract_versions=[registry.CURRENT_COGNITION_CONTRACT],
    )
    assert receipt.extension_id == "independent"
    assert receipt.compatibility == "current"
    assert reg.negotiate_cognition_contract(
        extension_contract_version=registry.CURRENT_COGNITION_CONTRACT,
        accepted_core_contract_versions=(registry.CURRENT_COGNITION_CONTRACT,),
    ).accepted_core_contract_versions == (registry.CURRENT_COGNITION_CONTRACT,)
    with pytest.raises(RuntimeError, match="unsupported_cognition_contract_version"):
        reg.negotiate_cognition_contract(
            extension_contract_version="ace.cognition.revision/v99",
            accepted_core_contract_versions=[registry.CURRENT_COGNITION_CONTRACT],
        )
    with pytest.raises(RuntimeError, match="incompatible_core_cognition_contract"):
        reg.negotiate_cognition_contract(
            extension_contract_version=registry.CURRENT_COGNITION_CONTRACT,
            accepted_core_contract_versions=["ace.cognition.revision/v0"],
        )


def test_current_registration_exposes_callable_free_digest_manifest() -> None:
    reg = registry.Registry(extension_id="independent", extension_version="2.0.0")
    reg.negotiate_cognition_contract(
        extension_contract_version=registry.CURRENT_COGNITION_CONTRACT,
        accepted_core_contract_versions=[registry.CURRENT_COGNITION_CONTRACT],
    )
    reg.register_recipe(
        "independent_recipe",
        _recipe(),
        cognition_contract_version=registry.CURRENT_COGNITION_CONTRACT,
        accepted_core_contract_versions=[registry.CURRENT_COGNITION_CONTRACT],
        disciplines=["independent-domain"],
        resource_manifest={"instructions/guide.md": "a" * 64},
        required_authorities=["read-product"],
        side_effects=[],
    )
    manifest = registry.registered_recipe_manifests()["independent_recipe"]
    assert manifest["compatibility"] == "current"
    assert manifest["package_digest"]
    assert manifest["resource_manifest"] == [{"resource": "instructions/guide.md", "sha256": "a" * 64}]
    assert "recipe" not in manifest
    assert all(not callable(value) for value in manifest.values())


def test_current_registration_requires_matching_pre_registration_negotiation() -> None:
    reg = registry.Registry(extension_id="independent", extension_version="2.0.0")
    with pytest.raises(RuntimeError, match="requires_pre_registration_negotiation"):
        reg.register_recipe(
            "independent_recipe",
            _recipe(),
            cognition_contract_version=registry.CURRENT_COGNITION_CONTRACT,
            accepted_core_contract_versions=[registry.CURRENT_COGNITION_CONTRACT],
        )
    assert registry.registered_recipe_sources() == {}


def test_n_minus_one_signature_is_adapted_with_explicit_compatibility() -> None:
    registry.Registry(extension_id="legacy", extension_version="1.9.0").register_recipe(
        "legacy_recipe",
        _recipe(),
        disciplines=["legacy-domain"],
    )
    source = registry.registered_recipe_sources()["legacy_recipe"]
    assert source.cognition_contract_version == registry.LEGACY_COGNITION_REGISTRATION
    assert source.compatibility == "n_minus_1_legacy_adapter"
    assert source.accepted_core_contract_versions == (registry.CURRENT_COGNITION_CONTRACT,)


def test_future_incompatible_and_untrusted_code_fail_before_registration() -> None:
    reg = registry.Registry(extension_id="future", extension_version="99.0.0")
    with pytest.raises(RuntimeError, match="unsupported_cognition_contract_version"):
        reg.register_recipe(
            "future_recipe",
            _recipe(),
            cognition_contract_version="ace.cognition.revision/v99",
        )
    with pytest.raises(RuntimeError, match="untrusted_in_process"):
        reg.register_recipe(
            "untrusted_recipe",
            _recipe(),
            trusted_in_process=False,
        )
    assert registry.registered_recipe_sources() == {}


@pytest.mark.parametrize(
    "manifest",
    [
        {"../secret": "a" * 64},
        {"/absolute": "a" * 64},
        {r"C:\\absolute\\secret": "a" * 64},
        {"C:/absolute/secret": "a" * 64},
        {"instructions//guide.md": "a" * 64},
        {"guide.md": "not-a-digest"},
    ],
)
def test_invalid_or_traversing_resource_manifest_is_rejected(manifest) -> None:
    with pytest.raises(ValueError, match="invalid_cognition_resource_manifest"):
        registry.Registry(extension_id="bad", extension_version="1.0.0").register_recipe(
            "bad_recipe",
            _recipe(),
            resource_manifest=manifest,
        )


def test_resource_and_declaration_counts_are_bounded() -> None:
    reg = registry.Registry(extension_id="bounded", extension_version="1.0.0")
    with pytest.raises(ValueError, match="invalid_cognition_resource_manifest"):
        reg.register_recipe(
            "too_many_resources",
            _recipe(),
            resource_manifest={f"resources/{index}.md": "a" * 64 for index in range(65)},
        )
    with pytest.raises(ValueError, match="invalid_cognition_required_authorities"):
        reg.register_recipe(
            "too_many_authorities",
            _recipe(),
            required_authorities=[f"authority-{index}" for index in range(65)],
        )
    with pytest.raises(ValueError, match="invalid_cognition_side_effects"):
        reg.register_recipe(
            "duplicate_amplification",
            _recipe(),
            side_effects=["network"] * 65,
        )
    assert registry.registered_recipe_sources() == {}


def test_unconsumed_surfaces_report_unsupported_instead_of_success() -> None:
    reg = registry.Registry(extension_id="extension", extension_version="1.0.0")
    reg.register_committee("committee", lambda: None)
    reg.register_personas([type("Persona", (), {"slug": "critic"})()])
    reg.register_frameworks([type("Framework", (), {"slug": "lens"})()])
    reg.register_schema("schema/extension.surql")
    diagnostics = registry.registered_unsupported_cognition()
    assert {(item.capability, item.stable_key) for item in diagnostics} == {
        ("committee", "committee"),
        ("persona", "critic"),
        ("framework", "lens"),
        ("schema", "schema/extension.surql"),
    }
    assert registry.registered_committees() == {}
    assert registry.registered_personas() == []
    assert registry.registered_frameworks() == []
    assert registry.registered_schema_paths() == []


def test_recipe_count_bound_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(registry, "MAX_COGNITION_RECIPES", 1)
    reg = registry.Registry(extension_id="bounded", extension_version="1.0.0")
    recipe = _recipe()
    reg.register_recipe("first", recipe)
    with pytest.raises(RuntimeError, match="limited to 1"):
        reg.register_recipe("second", copy.deepcopy(recipe))
