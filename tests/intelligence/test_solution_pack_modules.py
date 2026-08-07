from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ace.intelligence.contracts.activation import ActivationState, OrganizationOverlayV1
from ace.intelligence.contracts.pack import CompiledModuleV1, DomainPackManifestV1
from ace.intelligence.contracts.resources import (
    CanonicalJsonValueV1Alpha1,
    IntelligenceResourceMode,
    SignalV1Alpha1,
)
from ace.intelligence.packs.activation import (
    compile_overlay,
    prepare_activation_revision,
    prepare_domain_activation,
)
from ace.intelligence.packs.compiler import PackCompilationError, compile_pack
from ace.intelligence.packs.runtime import (
    bind_prepared_activation,
    resolve_brief_synthesis_policy,
)
from tests.intelligence.conftest import digest_bytes, encode_json

pytestmark = pytest.mark.unit


def _payloads() -> dict[str, dict]:
    return {
        "ontology": {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "subject",
                    "attributes": [{"attribute_id": "measure", "value_type": "number"}],
                }
            ],
            "relation_types": [],
        },
        "detection": {
            "contract": "ace.intelligence.detection/v1alpha1",
            "module_id": "detection",
            "numeric_delta_rules": [
                {
                    "detector_id": "measure_change",
                    "entity_type_id": "subject",
                    "attribute_id": "measure",
                    "metric": "percent_change",
                    "threshold": 5.0,
                    "direction": "any",
                    "shift_type": "measure_change",
                    "signal_type": "measure_attention",
                }
            ],
        },
        "synthesis": {
            "contract": "ace.intelligence.synthesis/v1alpha1",
            "module_id": "synthesis",
            "brief_templates": [
                {
                    "template_id": "measure_brief",
                    "brief_type": "measurement_orientation",
                    "display_name": "Measurement Brief",
                    "objective": "Explain a material measurement change and the bounded evidence.",
                    "required_sections": ["what_changed", "recommendation", "limitations"],
                    "recommendation_required": True,
                }
            ],
        },
        "personas": {
            "contract": "ace.intelligence.personas/v1alpha1",
            "module_id": "personas",
            "personas": [
                {
                    "persona_id": "domain_analyst",
                    "display_name": "Domain Analyst",
                    "description": "Reviews material changes and their evidence.",
                }
            ],
            "signal_routing_rules": [
                {
                    "routing_rule_id": "route_measure_attention",
                    "signal_type": "measure_attention",
                    "persona_ids": ["domain_analyst"],
                    "minimum_confidence": 0.7,
                    "brief_template_id": "measure_brief",
                }
            ],
        },
    }


def _pack(payloads: dict[str, dict]) -> tuple[DomainPackManifestV1, dict[str, bytes]]:
    dependencies = {
        "ontology": [],
        "detection": ["ontology"],
        "synthesis": [],
        "personas": ["detection", "synthesis"],
    }
    resources: dict[str, bytes] = {}
    manifest_resources = []
    modules = []
    for module_id, payload in payloads.items():
        path = f"modules/{module_id}.json"
        resource = encode_json(payload)
        resources[path] = resource
        manifest_resources.append(
            {
                "resource_id": f"{module_id}_resource",
                "path": path,
                "digest": digest_bytes(resource),
            }
        )
        modules.append(
            {
                "module_id": module_id,
                "contract": payload["contract"],
                "resource_id": f"{module_id}_resource",
                "depends_on": dependencies[module_id],
            }
        )
    manifest = DomainPackManifestV1(
        metadata={
            "pack_id": "generic_solution",
            "version": "0.1.0",
            "display_name": "Generic Solution",
        },
        resources=manifest_resources,
        modules=modules,
    )
    return manifest, resources


def _binding_for(compiled, *, product_id: str):
    overlay = compile_overlay(
        compiled,
        OrganizationOverlayV1(
            overlay_id="routing_test",
            version="0.1.0",
            pack_id=compiled.metadata.pack_id,
            pack_version=compiled.metadata.version,
            pack_digest=compiled.pack_digest,
        ),
    )
    spec = prepare_domain_activation(
        product_id=product_id,
        activation_key="generic_solution",
        pack=compiled,
        overlay=overlay,
        compilation_receipt_ref="receipt:prepared-compilation",
        conformance_receipt_refs=("receipt:prepared-conformance",),
    )
    revision = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:test-author",
        approval_receipt_ref="receipt:prepared-approval",
        occurred_at=datetime(2026, 8, 4, tzinfo=UTC),
    )
    return bind_prepared_activation(pack=compiled, revision=revision)


def test_persona_and_synthesis_modules_compile_without_executable_templates() -> None:
    manifest, resources = _pack(_payloads())

    compiled = compile_pack(manifest, resources)

    assert [item.contract for item in compiled.modules] == [
        "ace.intelligence.detection/v1alpha1",
        "ace.intelligence.ontology/v1alpha1",
        "ace.intelligence.personas/v1alpha1",
        "ace.intelligence.synthesis/v1alpha1",
    ]
    assert all("execute" not in item.canonical_payload for item in compiled.modules)


def test_legacy_synthesis_runtime_uses_legacy_sorted_effective_order() -> None:
    manifest, resources = _pack(_payloads())
    compiled = compile_pack(manifest, resources)
    policy = resolve_brief_synthesis_policy(
        _binding_for(compiled, product_id="product:legacy-synthesis"),
        template_id="measure_brief",
        persona_ids=("domain_analyst",),
    )

    assert policy.template.required_sections == (
        "limitations",
        "recommendation",
        "what_changed",
    )


def test_legacy_nonlexicographic_synthesis_identity_is_byte_for_byte_stable() -> None:
    def compile_sections(required_sections: list[str]):
        payload = {
            "contract": "ace.intelligence.synthesis/v1alpha1",
            "module_id": "market_synthesis",
            "brief_templates": [
                {
                    "template_id": "competitive_price_move_brief",
                    "brief_type": "competitive_intelligence",
                    "display_name": "Competitive Price Move Brief",
                    "objective": (
                        "Explain a material competitor price change, its evidence, "
                        "uncertainty, and the decision it may affect."
                    ),
                    "required_sections": required_sections,
                    "recommendation_required": True,
                    "claim_policy": "citation_or_explicit_inference",
                }
            ],
        }
        resource = encode_json(payload)
        manifest = DomainPackManifestV1(
            metadata={
                "pack_id": "legacy_synthesis_identity",
                "version": "0.1.0",
                "display_name": "Legacy Synthesis Identity",
            },
            resources=(
                {
                    "resource_id": "market_synthesis",
                    "path": "modules/synthesis.json",
                    "digest": digest_bytes(resource),
                },
            ),
            modules=(
                {
                    "module_id": "market_synthesis",
                    "contract": "ace.intelligence.synthesis/v1alpha1",
                    "resource_id": "market_synthesis",
                },
            ),
        )
        return compile_pack(manifest, {"modules/synthesis.json": resource})

    declared = [
        "what_changed",
        "why_it_matters",
        "recommendation",
        "limitations",
    ]
    compiled = compile_sections(declared)
    reordered = compile_sections(list(reversed(declared)))
    duplicated = compile_sections([*declared, "what_changed", "limitations"])
    module = compiled.modules[0]
    canonical = json.loads(module.canonical_payload)

    assert canonical["brief_templates"][0]["required_sections"] == [
        "limitations",
        "recommendation",
        "what_changed",
        "why_it_matters",
    ]
    assert module.module_digest == ("sha256:99ccea5e5fe93cd2ad22c20e9a36d30ce61506f8f998bc30da1a0432947495c0")
    assert compiled.compiled_pack_id == "pack_ir:a61b41ffb771a06bfbbada096d09df6d"
    assert compiled.pack_digest == ("sha256:a61b41ffb771a06bfbbada096d09df6d7a6ebb470ccd6d00ccdfd22e8dbd21bb")
    assert reordered == compiled
    assert duplicated == compiled


def test_ordered_synthesis_v1alpha2_compiles_revalidates_and_resolves_in_declared_order() -> None:
    payloads = _payloads()
    payloads["synthesis"]["contract"] = "ace.intelligence.synthesis/v1alpha2"
    declared = ("what_changed", "recommendation", "limitations")
    manifest, resources = _pack(payloads)

    compiled = compile_pack(manifest, resources)
    module = next(item for item in compiled.modules if item.module_id == "synthesis")
    revalidated = CompiledModuleV1.model_validate(module.model_dump(mode="python"))
    policy = resolve_brief_synthesis_policy(
        _binding_for(compiled, product_id="product:ordered-synthesis"),
        template_id="measure_brief",
        persona_ids=("domain_analyst",),
    )

    assert module.contract == "ace.intelligence.synthesis/v1alpha2"
    assert revalidated == module
    assert policy.template.required_sections == declared

    reordered_payloads = _payloads()
    reordered_payloads["synthesis"]["contract"] = "ace.intelligence.synthesis/v1alpha2"
    reordered_payloads["synthesis"]["brief_templates"][0]["required_sections"] = list(reversed(declared))
    reordered_manifest, reordered_resources = _pack(reordered_payloads)
    reordered_pack = compile_pack(reordered_manifest, reordered_resources)
    reordered_module = next(item for item in reordered_pack.modules if item.module_id == "synthesis")

    assert reordered_module.module_digest != module.module_digest
    assert reordered_pack.pack_digest != compiled.pack_digest


def test_synthesis_contracts_are_closed_world_and_cannot_be_cross_wired() -> None:
    payloads = _payloads()
    payloads["synthesis"]["contract"] = "ace.intelligence.synthesis/v1alpha2"
    manifest, resources = _pack(payloads)
    module = next(item for item in compile_pack(manifest, resources).modules if item.module_id == "synthesis")

    with pytest.raises(ValidationError):
        CompiledModuleV1.model_validate(
            {**module.model_dump(mode="python"), "contract": "ace.intelligence.synthesis/v1alpha1"}
        )

    payloads["synthesis"]["contract"] = "ace.intelligence.synthesis/v1alpha3"
    manifest, resources = _pack(payloads)
    with pytest.raises(PackCompilationError, match="unknown_module_contract"):
        compile_pack(manifest, resources)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("personas", "signal_routing_rules", 0, "signal_type"), "unknown_signal", "signal type outside"),
        (
            ("personas", "signal_routing_rules", 0, "brief_template_id"),
            "unknown_template",
            "Brief template outside",
        ),
        (("personas", "signal_routing_rules", 0, "persona_ids"), ["unknown_persona"], "unknown personas"),
    ],
)
def test_routing_references_fail_closed(path, value, message) -> None:
    payloads = deepcopy(_payloads())
    cursor = payloads
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value
    manifest, resources = _pack(payloads)

    with pytest.raises(PackCompilationError, match=message):
        compile_pack(manifest, resources)


def test_persona_confidence_and_synthesis_booleans_are_strict() -> None:
    payloads = _payloads()
    payloads["personas"]["signal_routing_rules"][0]["minimum_confidence"] = 1
    manifest, resources = _pack(payloads)
    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)
    assert exc_info.value.report.diagnostics[0].code == "invalid_module"

    payloads = _payloads()
    payloads["synthesis"]["brief_templates"][0]["recommendation_required"] = "yes"
    manifest, resources = _pack(payloads)
    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)
    assert exc_info.value.report.diagnostics[0].code == "invalid_module"


@pytest.mark.skip(reason="ace.intelligence.routing is deferred to a later packet (not yet ported)")
def test_signal_routing_is_an_explicit_optional_policy_step() -> None:
    from ace.intelligence.routing import eligible_signal_routes

    manifest, resources = _pack(_payloads())
    compiled = compile_pack(manifest, resources)
    product_id = "product:routing-test"
    binding = _binding_for(compiled, product_id=product_id)
    signal = SignalV1Alpha1(
        product_id=product_id,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=binding.reference,
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
        signal_type_ref="measure_attention",
        title="Material change requires attention",
        summary="A generic detector established a material change.",
        details=CanonicalJsonValueV1Alpha1(value_json="{}"),
        detected_at=datetime(2026, 8, 5, tzinfo=UTC),
        confidence=0.8,
    )

    routes = eligible_signal_routes(signal=signal, binding=binding)

    assert len(routes) == 1
    assert routes[0].activation_revision == binding.reference
    assert routes[0].persona_ids == ("domain_analyst",)
    assert routes[0].brief_template_id == "measure_brief"


@pytest.mark.skip(reason="ace.intelligence.routing is deferred to a later packet (not yet ported)")
def test_signal_cannot_be_routed_through_a_foreign_pack_binding() -> None:
    from ace.intelligence.routing import eligible_signal_routes

    manifest, resources = _pack(_payloads())
    original = compile_pack(manifest, resources)
    foreign_payloads = deepcopy(_payloads())
    foreign_payloads["personas"]["signal_routing_rules"][0]["persona_ids"] = ["domain_analyst"]
    foreign_payloads["personas"]["signal_routing_rules"][0]["minimum_confidence"] = 0.1
    foreign_manifest, foreign_resources = _pack(foreign_payloads)
    foreign = compile_pack(foreign_manifest, foreign_resources)
    product_id = "product:routing-test"
    original_binding = _binding_for(original, product_id=product_id)
    foreign_binding = _binding_for(foreign, product_id=product_id)
    signal = SignalV1Alpha1(
        product_id=product_id,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=original_binding.reference,
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
        signal_type_ref="measure_attention",
        title="Material change requires attention",
        summary="A generic detector established a material change.",
        details=CanonicalJsonValueV1Alpha1(value_json="{}"),
        detected_at=datetime(2026, 8, 5, tzinfo=UTC),
        confidence=0.8,
    )

    with pytest.raises(ValueError, match="exact bound activation"):
        eligible_signal_routes(signal=signal, binding=foreign_binding)
