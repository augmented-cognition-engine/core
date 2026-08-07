from __future__ import annotations

from copy import deepcopy

import pytest

from ace.intelligence.contracts.detection import DetectionModuleV1
from ace.intelligence.contracts.pack import (
    DomainPackManifestV1,
    PackMetadataV1,
    PackModuleRefV1,
    PackResourceV1,
)
from ace.intelligence.packs.compiler import PackCompilationError, compile_pack
from tests.intelligence.conftest import digest_bytes, encode_json

pytestmark = pytest.mark.unit


def _pack(
    detection_payload: dict,
    *,
    depends_on: tuple[str, ...] = ("domain_ontology",),
) -> tuple[DomainPackManifestV1, dict[str, bytes]]:
    ontology_payload = {
        "contract": "ace.intelligence.ontology/v1alpha1",
        "module_id": "domain_ontology",
        "entity_types": [
            {
                "entity_type_id": "subject",
                "attributes": [
                    {"attribute_id": "name", "value_type": "string", "required": True},
                    {"attribute_id": "measure", "value_type": "number"},
                ],
            }
        ],
        "relation_types": [],
    }
    ontology_bytes = encode_json(ontology_payload)
    detection_bytes = encode_json(detection_payload)
    resources = {
        "modules/ontology.json": ontology_bytes,
        "modules/detection.json": detection_bytes,
    }
    manifest = DomainPackManifestV1(
        metadata=PackMetadataV1(
            pack_id="generic_numeric_delta",
            version="0.1.0",
            display_name="Generic Numeric Delta",
        ),
        resources=(
            PackResourceV1(
                resource_id="ontology_resource",
                path="modules/ontology.json",
                digest=digest_bytes(ontology_bytes),
            ),
            PackResourceV1(
                resource_id="detection_resource",
                path="modules/detection.json",
                digest=digest_bytes(detection_bytes),
            ),
        ),
        modules=(
            PackModuleRefV1(
                module_id="domain_ontology",
                contract="ace.intelligence.ontology/v1alpha1",
                resource_id="ontology_resource",
            ),
            PackModuleRefV1(
                module_id="domain_detection",
                contract="ace.intelligence.detection/v1alpha1",
                resource_id="detection_resource",
                depends_on=depends_on,
            ),
        ),
    )
    return manifest, resources


@pytest.fixture
def detection_payload() -> dict:
    return {
        "contract": "ace.intelligence.detection/v1alpha1",
        "module_id": "domain_detection",
        "numeric_delta_rules": [
            {
                "detector_id": "material_measure_change",
                "entity_type_id": "subject",
                "attribute_id": "measure",
                "metric": "percent_change",
                "threshold": 0.1,
                "direction": "any",
                "shift_type": "material_measure_change",
                "signal_type": "measure_attention",
            }
        ],
    }


def test_detection_module_compiles_as_inert_pack_configuration(detection_payload):
    manifest, resources = _pack(detection_payload)

    compiled = compile_pack(manifest, resources)

    module = next(item for item in compiled.modules if item.module_id == "domain_detection")
    detection = DetectionModuleV1.model_validate_json(module.canonical_payload)
    assert detection.numeric_delta_rules[0].metric == "percent_change"
    assert detection.numeric_delta_rules[0].threshold == 0.1
    assert "price_move" not in module.canonical_payload


def test_detection_rules_are_canonicalized_by_identifier(detection_payload):
    second = deepcopy(detection_payload["numeric_delta_rules"][0])
    second["detector_id"] = "absolute_measure_change"
    second["metric"] = "absolute_change"
    second["threshold"] = 5
    first_payload = deepcopy(detection_payload)
    first_payload["numeric_delta_rules"].append(second)
    second_payload = deepcopy(first_payload)
    second_payload["numeric_delta_rules"].reverse()

    first_manifest, first_resources = _pack(first_payload)
    second_manifest, second_resources = _pack(second_payload)

    first = compile_pack(first_manifest, first_resources)
    second_compiled = compile_pack(second_manifest, second_resources)
    assert first.model_dump_json() == second_compiled.model_dump_json()
    assert first.pack_digest == second_compiled.pack_digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("threshold", "0.1"),
        ("threshold", True),
        ("direction", "sideways"),
        ("baseline", "latest_available"),
    ],
)
def test_detection_configuration_fails_closed(detection_payload, field, value):
    invalid = deepcopy(detection_payload)
    invalid["numeric_delta_rules"][0][field] = value
    manifest, resources = _pack(invalid)

    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)

    diagnostic = exc_info.value.report.diagnostics[0]
    assert diagnostic.code == "invalid_module"
    assert f"numeric_delta_rules.0.{field}" in diagnostic.path


def test_detector_must_reference_visible_numeric_ontology_attribute(detection_payload):
    unknown_attribute = deepcopy(detection_payload)
    unknown_attribute["numeric_delta_rules"][0]["attribute_id"] = "missing"
    manifest, resources = _pack(unknown_attribute)
    with pytest.raises(PackCompilationError, match="references unknown attribute"):
        compile_pack(manifest, resources)

    nonnumeric = deepcopy(detection_payload)
    nonnumeric["numeric_delta_rules"][0]["attribute_id"] = "name"
    manifest, resources = _pack(nonnumeric)
    with pytest.raises(PackCompilationError, match="requires an integer or number attribute"):
        compile_pack(manifest, resources)

    manifest, resources = _pack(detection_payload, depends_on=())
    with pytest.raises(PackCompilationError, match="outside its module dependencies"):
        compile_pack(manifest, resources)


def test_detector_comparison_context_must_reference_the_same_visible_entity(detection_payload):
    missing_context = deepcopy(detection_payload)
    missing_context["numeric_delta_rules"][0]["context_attribute_ids"] = ["currency"]
    manifest, resources = _pack(missing_context)

    with pytest.raises(PackCompilationError, match="unknown comparison context"):
        compile_pack(manifest, resources)

    duplicate_watch = deepcopy(detection_payload)
    duplicate_watch["numeric_delta_rules"][0]["context_attribute_ids"] = ["measure"]
    manifest, resources = _pack(duplicate_watch)
    with pytest.raises(PackCompilationError, match="watched attribute"):
        compile_pack(manifest, resources)
