from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from ace.intelligence.contracts.activation import OrganizationOverlayV1
from ace.intelligence.contracts.conformance import DomainPackConformanceReceiptV1
from ace.intelligence.contracts.diagnostics import PackCompatibilityStatus
from ace.intelligence.packs.activation import compile_overlay, prepare_domain_activation
from ace.intelligence.packs.compiler import (
    PackCompilationError,
    compile_pack_document,
    compile_pack_document_with_report,
    negotiate_pack_compatibility,
    validate_compiled_pack_set,
)
from ace.intelligence.schemas import schema_text
from ace.testing import conformance_receipt_json, run_domain_pack_conformance

pytestmark = pytest.mark.unit


def _encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _stable_pack(*, authority: str | None = None):
    modules = {
        "modules/ontology.json": {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "measurement",
                    "attributes": [{"attribute_id": "value", "value_type": "number", "required": True}],
                }
            ],
            "relation_types": [],
        },
        "modules/detection.json": {
            "contract": "ace.intelligence.detection/v1alpha1",
            "module_id": "detection",
            "numeric_delta_rules": [
                {
                    "detector_id": "value_change",
                    "entity_type_id": "measurement",
                    "attribute_id": "value",
                    "metric": "absolute_change",
                    "threshold": 5,
                    "direction": "any",
                    "shift_type": "value_changed",
                    "signal_type": "value_attention",
                }
            ],
        },
        "modules/synthesis.json": {
            "contract": "ace.intelligence.synthesis/v1alpha1",
            "module_id": "synthesis",
            "brief_templates": [
                {
                    "template_id": "measurement_brief",
                    "brief_type": "measurement_update",
                    "display_name": "Measurement update",
                    "objective": "Explain the material change.",
                    "required_sections": ["summary"],
                }
            ],
        },
        "modules/personas.json": {
            "contract": "ace.intelligence.personas/v1alpha1",
            "module_id": "personas",
            "personas": [
                {"persona_id": "analyst", "display_name": "Analyst", "description": "Reviews changes."}
            ],
            "signal_routing_rules": [
                {
                    "routing_rule_id": "measurement_route",
                    "signal_type": "value_attention",
                    "persona_ids": ["analyst"],
                    "minimum_confidence": 0.5,
                    "brief_template_id": "measurement_brief",
                }
            ],
        },
    }
    resources = {path: _encoded(payload) for path, payload in modules.items()}
    refs = (
        ("ontology", "ace.intelligence.ontology/v1alpha1", "ontology_resource", ()),
        ("detection", "ace.intelligence.detection/v1alpha1", "detection_resource", ("ontology",)),
        ("synthesis", "ace.intelligence.synthesis/v1alpha1", "synthesis_resource", ()),
        (
            "personas",
            "ace.intelligence.personas/v1alpha1",
            "personas_resource",
            ("detection", "synthesis"),
        ),
    )
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1",
        "metadata": {"pack_id": "neutral_measurement", "version": "1.0.0", "display_name": "Neutral Measurement"},
        "compatibility": {
            "compiler_minimum": "ace.intelligence.pack-compiler/v1alpha1",
            "compiler_maximum_exclusive": "ace.intelligence.pack-compiler/v2",
            "intelligence_minimum": "ace.intelligence.runtime/v1alpha1",
            "intelligence_maximum_exclusive": "ace.intelligence.runtime/v2",
        },
        "resources": [
            {
                "resource_id": resource_id,
                "path": path,
                "digest": _digest(resources[path]),
            }
            for path, (_, _, resource_id, _) in zip(resources, refs, strict=True)
        ],
        "modules": [
            {"module_id": module_id, "contract": contract, "resource_id": resource_id, "depends_on": depends_on}
            for module_id, contract, resource_id, depends_on in refs
        ],
        "authority_requests": (
            [] if authority is None else [{"request_id": "escalation", "authority": authority}]
        ),
    }
    return _encoded(manifest), resources


def _fixture(*, threshold_expected: bool = True, fixture_id: str = "neutral_measurement_golden") -> bytes:
    expected = [
        {
            "detector_id": "value_change",
            "entity_ref": "entity:measurement-one",
            "material": threshold_expected,
            **(
                {
                    "shift_type": "value_changed",
                    "signal_type": "value_attention",
                    "routing_rule_ids": ["measurement_route"],
                    "persona_ids": ["analyst"],
                    "template_ids": ["measurement_brief"],
                }
                if threshold_expected
                else {}
            ),
        }
    ]
    return _encoded(
        {
            "contract": "ace.intelligence.domain-pack-golden-fixture/v1",
            "fixture_id": fixture_id,
            "fixture_version": "1.0.0",
            "observations": [
                {
                    "case_id": "material_change",
                    "entity_type_id": "measurement",
                    "entity_ref": "entity:measurement-one",
                    "baseline_attributes_json": "{\"value\":10}",
                    "current_attributes_json": "{\"value\":20}",
                    "baseline_as_of": "2026-08-11T00:00:00Z",
                    "current_as_of": "2026-08-11T01:00:00Z",
                    "confidence": 0.9,
                    "expected": expected,
                }
            ],
        }
    )


def _receipt():
    manifest, resources = _stable_pack()
    return run_domain_pack_conformance(
        manifest_document=manifest,
        resources=resources,
        fixture_document=_fixture(),
    )


def test_explicit_compatibility_negotiation_distinguishes_all_public_states():
    stable = negotiate_pack_compatibility(
        "ace.intelligence.domain-pack-manifest/v1",
        {
            "compiler_minimum": "ace.intelligence.pack-compiler/v1alpha1",
            "compiler_maximum_exclusive": "ace.intelligence.pack-compiler/v2",
            "intelligence_minimum": "ace.intelligence.runtime/v1alpha1",
            "intelligence_maximum_exclusive": "ace.intelligence.runtime/v2",
        },
    )
    prior = negotiate_pack_compatibility("ace.intelligence.domain-pack-manifest/v1alpha1", None)
    migration = negotiate_pack_compatibility("ace.intelligence.domain-pack-manifest/v1beta1", None)
    rejected = negotiate_pack_compatibility("ace.intelligence.domain-pack-manifest/v2", None)

    assert stable.status is PackCompatibilityStatus.SUPPORTED
    assert prior.status is PackCompatibilityStatus.DEPRECATED
    assert migration.status is PackCompatibilityStatus.MIGRATION_REQUIRED
    assert migration.diagnostics[0].code == "manifest_migration_required"
    assert rejected.status is PackCompatibilityStatus.REJECTED
    assert len({item.result_id for item in (stable, prior, migration, rejected)}) == 4

    narrower = negotiate_pack_compatibility(
        "ace.intelligence.domain-pack-manifest/v1",
        {
            "compiler_minimum": "ace.intelligence.pack-compiler/v1",
            "compiler_maximum_exclusive": "ace.intelligence.pack-compiler/v2",
            "intelligence_minimum": "ace.intelligence.runtime/v1",
            "intelligence_maximum_exclusive": "ace.intelligence.runtime/v2",
        },
    )
    assert narrower.status is PackCompatibilityStatus.SUPPORTED
    assert narrower.result_id != stable.result_id


def test_machine_readable_manifest_module_and_receipt_schemas_are_discoverable():
    index = json.loads(schema_text("domain-pack-contracts-v1.json"))
    manifest_schema = json.loads(schema_text(index["manifest_schema"]))
    receipt_schema = json.loads(schema_text(index["conformance"]["receipt_schema"]))

    assert index["host_contracts"] == {
        "compiler": "ace.intelligence.pack-compiler/v1",
        "runtime": "ace.intelligence.runtime/v1",
    }
    assert "ontology-v1alpha1" in index["module_schemas"]
    assert "source-mapping-v1alpha1" in index["module_schemas"]
    assert manifest_schema["properties"]["contract"]["const"] == "ace.intelligence.domain-pack-manifest/v1"
    assert receipt_schema["properties"]["receipt_digest"]["title"] == "Receipt Digest"


def test_receipt_is_byte_identical_across_two_fresh_directories(tmp_path):
    manifest, resources = _stable_pack()
    fixture = _fixture()
    receipts = []
    for name in ("first", "second"):
        root = tmp_path / name
        root.mkdir()
        (root / "manifest.json").write_bytes(manifest)
        (root / "fixture.json").write_bytes(fixture)
        receipts.append(
            run_domain_pack_conformance(
                manifest_document=(root / "manifest.json").read_bytes(),
                resources=resources,
                fixture_document=(root / "fixture.json").read_bytes(),
            )
        )

    assert receipts[0].passed is True
    assert receipts[0].receipt_id == receipts[1].receipt_id
    assert conformance_receipt_json(receipts[0]) == conformance_receipt_json(receipts[1])
    assert receipts[0].expected_digest == receipts[0].actual_digest
    compiled = compile_pack_document_with_report(manifest, resources)
    assert receipts[0].compilation_result_id == compiled.compilation.result_id
    assert receipts[0].compilation_result_digest == compiled.compilation.result_digest


def test_conformance_identity_cannot_be_reused_for_changed_expectations():
    first = _receipt()
    manifest, resources = _stable_pack()
    changed = run_domain_pack_conformance(
        manifest_document=manifest,
        resources=resources,
        fixture_document=_fixture(threshold_expected=False),
        prior_receipt=first,
    )

    assert changed.passed is False
    assert {item.code for item in changed.diagnostics} == {
        "divergent_conformance_identity",
        "golden_result_mismatch",
    }


def test_v1alpha1_fixture_remains_conformant_in_the_supported_prior_window():
    manifest, resources = _stable_pack()
    payload = json.loads(manifest)
    payload["contract"] = "ace.intelligence.domain-pack-manifest/v1alpha1"
    payload["compatibility"] = {
        "compiler_contract": "ace.intelligence.pack-compiler/v1alpha1",
        "intelligence_contract": "ace.intelligence.runtime/v1alpha1",
    }

    receipt = run_domain_pack_conformance(
        manifest_document=_encoded(payload),
        resources=resources,
        fixture_document=_fixture(),
    )

    assert receipt.passed is True
    assert receipt.compatibility_status is PackCompatibilityStatus.DEPRECATED
    assert receipt.manifest_contract == "ace.intelligence.domain-pack-manifest/v1alpha1"


def test_stable_activation_requires_exact_current_passing_receipt():
    manifest, resources = _stable_pack()
    pack = compile_pack_document(manifest, resources)
    receipt = _receipt()
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="empty",
            version="1.0.0",
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
        ),
    )
    assert pack.contract == "ace.intelligence.compiled-domain-pack/v1"
    assert pack.compiler_contract == "ace.intelligence.pack-compiler/v1"
    common = {
        "product_id": "product:stable-pack",
        "activation_key": "neutral_measurement",
        "pack": pack,
        "overlay": overlay,
        "compilation_receipt_ref": receipt.compilation_result_id,
    }

    activated = prepare_domain_activation(**common, conformance_receipts=(receipt,))
    assert activated.conformance_receipt_refs == (receipt.receipt_id,)
    with pytest.raises(ValueError, match="compilation evidence does not match"):
        prepare_domain_activation(
            **{**common, "compilation_receipt_ref": "pack_compilation:" + "0" * 32},
            conformance_receipts=(receipt,),
        )
    with pytest.raises(ValueError, match="requires passing exact"):
        prepare_domain_activation(**common)

    failed = run_domain_pack_conformance(
        manifest_document=manifest,
        resources=resources,
        fixture_document=_fixture(threshold_expected=False),
    )
    with pytest.raises(ValueError, match="refuses failed"):
        prepare_domain_activation(**common, conformance_receipts=(failed,))

    stale = DomainPackConformanceReceiptV1(
        **receipt.model_dump(
            mode="python",
            exclude={"compiler_contract", "receipt_id", "receipt_digest"},
        ),
        compiler_contract="ace.intelligence.pack-compiler/v1alpha1",
    )
    with pytest.raises(ValueError, match="stale or incompatible"):
        prepare_domain_activation(**common, conformance_receipts=(stale,))

    foreign = receipt.model_copy(update={"pack_id": "another_pack", "receipt_id": None, "receipt_digest": None})
    with pytest.raises(ValueError, match="failed exact revalidation|does not bind"):
        prepare_domain_activation(**common, conformance_receipts=(foreign,))


def test_stable_compiler_refuses_ranges_imperative_content_authority_and_drift():
    manifest, resources = _stable_pack()
    payload = json.loads(manifest)
    payload["compatibility"]["compiler_minimum"] = "ace.intelligence.pack-compiler/v2"
    with pytest.raises(PackCompilationError) as unsupported:
        compile_pack_document(_encoded(payload), resources)
    assert unsupported.value.report.diagnostics[0].code == "unsupported_compiler_range"

    imperative = deepcopy(resources)
    module = json.loads(imperative["modules/ontology.json"])
    module["script"] = "do_not_run()"
    imperative["modules/ontology.json"] = _encoded(module)
    payload = json.loads(manifest)
    payload["resources"][0]["digest"] = _digest(imperative["modules/ontology.json"])
    with pytest.raises(PackCompilationError) as unsafe:
        compile_pack_document(_encoded(payload), imperative)
    assert unsafe.value.report.diagnostics[0].code == "invalid_module"

    escalated_manifest, escalated_resources = _stable_pack(authority="external_action")
    with pytest.raises(PackCompilationError) as escalation:
        compile_pack_document(escalated_manifest, escalated_resources)
    assert escalation.value.report.diagnostics[0].code == "authority_escalation"

    capability_payload = json.loads(manifest)
    capability_payload["capability_requirements"] = [
        {
            "requirement_id": "network",
            "capability": "network_access",
            "contract": "ace.connector.network/v1alpha1",
        }
    ]
    with pytest.raises(PackCompilationError) as capability:
        compile_pack_document(_encoded(capability_payload), resources)
    assert capability.value.report.diagnostics[0].code == "capability_escalation"

    with pytest.raises(PackCompilationError) as drift:
        compile_pack_document(manifest, {**resources, "modules/ontology.json": b"{}"})
    assert drift.value.report.diagnostics[0].code == "digest_mismatch"
    assert drift.value.report.contract == "ace.intelligence.pack-compilation-report/v1"


def test_pack_set_is_deterministic_and_refuses_identifier_collisions():
    first_manifest, first_resources = _stable_pack()
    first = compile_pack_document(first_manifest, first_resources)
    payload = json.loads(first_manifest)
    payload["metadata"]["pack_id"] = "second_measurement"
    second = compile_pack_document(_encoded(payload), first_resources)

    assert [item.metadata.pack_id for item in validate_compiled_pack_set([second, first])] == [
        "neutral_measurement",
        "second_measurement",
    ]
    with pytest.raises(PackCompilationError) as collision:
        validate_compiled_pack_set([first, first])
    assert collision.value.report.diagnostics[0].code == "pack_identifier_collision"


def test_declared_compatibility_range_is_pack_identity_material():
    manifest, resources = _stable_pack()
    broad = compile_pack_document(manifest, resources)
    payload = json.loads(manifest)
    payload["compatibility"]["compiler_minimum"] = "ace.intelligence.pack-compiler/v1"
    payload["compatibility"]["intelligence_minimum"] = "ace.intelligence.runtime/v1"
    narrow = compile_pack_document(_encoded(payload), resources)

    assert broad.compiled_pack_id != narrow.compiled_pack_id
    assert broad.pack_digest != narrow.pack_digest


def test_requested_capabilities_and_bounded_source_authority_remain_inspectable():
    manifest, resources = _stable_pack()
    payload = json.loads(manifest)
    payload["capability_requirements"] = [
        {
            "requirement_id": "public_snapshot",
            "capability": "source_snapshot",
            "contract": "ace.source.snapshot/v1alpha1",
        }
    ]
    payload["authority_requests"] = [{"request_id": "read_source", "authority": "source_read"}]

    pack = compile_pack_document(_encoded(payload), resources)

    assert pack.capability_requirements[0].capability == "source_snapshot"
    assert pack.authority_requests[0].authority == "source_read"


def test_stable_source_mapping_refuses_embedded_network_location():
    ontology = _encoded(
        {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "subject",
                    "attributes": [{"attribute_id": "name", "value_type": "string", "required": True}],
                }
            ],
            "relation_types": [],
        }
    )
    mapping = _encoded(
        {
            "contract": "ace.intelligence.source-mapping/v1alpha1",
            "module_id": "source_mapping",
            "mappings": [
                {
                    "mapping_id": "subject_mapping",
                    "source_definition_ref": "https://example.invalid/source",
                    "source_type_ref": "record.subject",
                    "capability_requirement_id": "snapshot",
                    "authority_request_id": "read_source",
                    "allowed_uri_schemes": ["https"],
                    "subject_binding_id": "subject_binding",
                    "entity_type_id": "subject",
                    "attribute_mappings": [{"attribute_id": "name", "source_pointer": "/name"}],
                    "static_confidence": 1.0,
                }
            ],
        }
    )
    resources = {"modules/ontology.json": ontology, "modules/source-mapping.json": mapping}
    manifest = _encoded(
        {
            "contract": "ace.intelligence.domain-pack-manifest/v1",
            "metadata": {"pack_id": "network_refusal", "version": "1.0.0", "display_name": "Network refusal"},
            "compatibility": {
                "compiler_minimum": "ace.intelligence.pack-compiler/v1alpha1",
                "compiler_maximum_exclusive": "ace.intelligence.pack-compiler/v2",
                "intelligence_minimum": "ace.intelligence.runtime/v1alpha1",
                "intelligence_maximum_exclusive": "ace.intelligence.runtime/v2",
            },
            "resources": [
                {"resource_id": "ontology_resource", "path": "modules/ontology.json", "digest": _digest(ontology)},
                {
                    "resource_id": "mapping_resource",
                    "path": "modules/source-mapping.json",
                    "digest": _digest(mapping),
                },
            ],
            "modules": [
                {
                    "module_id": "ontology",
                    "contract": "ace.intelligence.ontology/v1alpha1",
                    "resource_id": "ontology_resource",
                },
                {
                    "module_id": "source_mapping",
                    "contract": "ace.intelligence.source-mapping/v1alpha1",
                    "resource_id": "mapping_resource",
                    "depends_on": ["ontology"],
                },
            ],
            "capability_requirements": [
                {"requirement_id": "snapshot", "capability": "source_snapshot", "contract": "ace.source.snapshot/v1alpha1"}
            ],
            "authority_requests": [{"request_id": "read_source", "authority": "source_read"}],
        }
    )

    with pytest.raises(PackCompilationError) as forbidden:
        compile_pack_document(manifest, resources)
    assert forbidden.value.report.diagnostics[0].code == "network_location_forbidden"
