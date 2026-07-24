"""Tests for the open ProductExtension — ACE's canonical extension example."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_extensions


@pytest.mark.unit
def test_product_package_imports():
    """The reference extension package must be importable."""
    import extensions.reference  # noqa: F401


@pytest.mark.unit
def test_product_extension_class_exists_and_has_metadata():
    """ProductExtension exposes name + version per the Extension contract."""
    from extensions.reference import ProductExtension

    f = ProductExtension()
    assert f.name == "product"
    assert isinstance(f.version, str) and len(f.version) > 0


@pytest.mark.unit
def test_reference_projector_is_generic_deterministic_bounded_content():
    from extensions.reference.invocation import OUTCOME_CONTRACT, project_product_check

    output = "Recommendation: run the reversible pricing test first."
    first = project_product_check(output, {"state": "complete"})
    second = project_product_check(output, {"state": "complete"})

    assert first == second
    assert first.contract_version == OUTCOME_CONTRACT
    assert first.data == {
        "recommendation_content": output,
        "execution_state": "complete",
        "projection": "bounded_content_container",
    }
    assert first.artifact_refs == []
    assert first.artifact_provenance == []


@pytest.mark.asyncio
async def test_reference_action_passes_provider_free_conformance_without_marketing():
    from core.engine.extensions import (
        ExtensionActorContext,
        ExtensionInvocationEnvelope,
        run_task_action_conformance,
    )
    from core.engine.extensions.invocation import RegisteredTaskAction
    from extensions.reference import ProductExtension
    from extensions.reference.invocation import (
        OUTCOME_CONTRACT,
        prepare_product_check,
        project_product_check,
    )

    action = RegisteredTaskAction(
        extension_id=ProductExtension.name,
        extension_version=ProductExtension.version,
        action="product-check",
        prepare=prepare_product_check,
        project_outcome=project_product_check,
        output_contract=OUTCOME_CONTRACT,
        description="Evaluate a bounded generic question through Core's durable task runtime.",
        lifecycle_operations=["submit", "retrieve", "history", "retry", "cancel"],
        cancellation_supported=True,
        resolver_capabilities=["declared-reference-identities"],
    )
    result = await run_task_action_conformance(
        action,
        ExtensionInvocationEnvelope(
            extension_id="product",
            extension_version=ProductExtension.version,
            action="product-check",
            workspace_id="workspace:reference",
            question="Which reversible test should run first?",
            references=[
                {
                    "namespace": "example",
                    "kind": "record",
                    "id": "record:one",
                    "version": "1",
                }
            ],
        ),
        ExtensionActorContext(
            product_id="product:reference",
            workspace_id="workspace:reference",
            user_id="user:reference",
        ),
    )

    assert result["passed"] is True
    source = (Path(__file__).parents[2] / "extensions" / "reference" / "invocation.py").read_text()
    assert "marketing" not in source.lower()


@pytest.mark.unit
def test_product_extension_register_wires_recipe_instruments_tool():
    """register(reg) must register the recipe (with product discipline routing),
    both instruments, the ace_product_pulse tool, and the heartbeat sentinel."""
    from extensions.reference import ProductExtension

    captured = {
        "task_actions": [],
        "instruments": [],
        "recipes": [],
        "tools": [],
        "sentinels": [],
    }

    class _FakeRegistry:
        def register_task_action(self, action, prepare, **kwargs):
            captured["task_actions"].append((action, prepare, kwargs))

        def register_instrument(self, slug, module_path):
            captured["instruments"].append((slug, module_path))

        def register_recipe(self, name, recipe, *, disciplines=None, task_types=None):
            captured["recipes"].append((name, recipe, disciplines or []))

        def register_tool(self, fn, *, title=None):
            captured["tools"].append((getattr(fn, "__name__", "?"), title))

        def register_sentinel(self, name, *, cron, description, fn, trigger=None):
            captured["sentinels"].append((name, cron))

    ProductExtension().register(_FakeRegistry())

    # Durable domain action — one bounded reference-aware example.
    assert len(captured["task_actions"]) == 1
    action, prepare, options = captured["task_actions"][0]
    assert action == "product-check"
    assert callable(prepare)
    assert options["cancellation_supported"] is True
    assert "history" in options["lifecycle_operations"]

    # Instruments — exactly the two bespoke ones
    slugs = {s for s, _ in captured["instruments"]}
    assert "product-framing" in slugs
    assert "multi-voice-engage" in slugs

    # Recipe — registered with the product discipline route
    assert captured["recipes"], "No recipe registered"
    name, recipe, disciplines = captured["recipes"][0]
    assert name == "product_decision_intelligence"
    assert "extensions.reference.recipe" in recipe
    assert "product" in disciplines

    # Tool — ace_product_pulse with a human-readable title
    assert captured["tools"], "No tool registered"
    fn_name, title = captured["tools"][0]
    assert fn_name == "ace_product_pulse"
    assert title  # non-empty

    # Sentinel — heartbeat engine registered with the correct cron
    assert captured["sentinels"], "No sentinel registered"
    sentinel_name, sentinel_cron = captured["sentinels"][0]
    assert sentinel_name == "product_heartbeat"
    assert sentinel_cron == "0 6 * * *"


@pytest.mark.integration
def test_product_extension_discoverable_via_entry_point():
    """After pip install -e ., load_extensions() must discover ProductExtension."""
    from core.engine.extensions.loader import load_extensions

    loaded = load_extensions()
    # load_extensions() returns sorted list of name strings
    assert "product" in loaded, f"product extension not discovered; found: {loaded}"


@pytest.mark.integration
def test_composer_routes_product_discipline_to_recipe():
    """With the extension loaded, classification.discipline == 'product' resolves
    to product_decision_intelligence via the extension registry."""
    from core.engine.extensions.registry import registered_recipe_disciplines

    assert registered_recipe_disciplines().get("product") == "product_decision_intelligence"
