from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from ace.intelligence.contracts.pack import (
    CompiledModuleV1,
    DomainPackManifestV1,
    PackMetadataV1,
    PackModuleRefV1,
    PackResourceV1,
)
from ace.intelligence.packs.compiler import PackCompilationError, compile_pack, compile_pack_document
from tests.intelligence.conftest import digest_bytes, encode_json

pytestmark = pytest.mark.unit


def test_market_and_threat_ontologies_use_identical_compiler(pack_factory, market_payload, threat_payload):
    market_manifest, market_resources = pack_factory(market_payload)
    threat_manifest, threat_resources = pack_factory(
        threat_payload,
        pack_id="threat_intelligence",
        display_name="Threat Intelligence",
    )

    market = compile_pack(market_manifest, market_resources)
    threat = compile_pack(threat_manifest, threat_resources)

    assert market.contract == threat.contract == "ace.intelligence.compiled-domain-pack/v1alpha1"
    assert market.modules[0].contract == threat.modules[0].contract == "ace.intelligence.ontology/v1alpha1"
    assert market.metadata.pack_id == "market_intelligence"
    assert threat.metadata.pack_id == "threat_intelligence"
    assert market.pack_digest != threat.pack_digest


def test_semantically_unordered_json_compiles_to_identical_ir(pack_factory, market_payload):
    reordered = deepcopy(market_payload)
    reordered["entity_types"] = list(reversed(reordered["entity_types"]))
    reordered["entity_types"][0]["attributes"] = list(reversed(reordered["entity_types"][0]["attributes"]))

    payload_a = {"contract": "ace.intelligence.ontology/v1alpha1", "module_id": "domain_ontology", **market_payload}
    payload_b = {"module_id": "domain_ontology", **reordered, "contract": "ace.intelligence.ontology/v1alpha1"}
    manifest_a, resources_a = pack_factory(market_payload, raw_bytes=encode_json(payload_a))
    manifest_b, resources_b = pack_factory(reordered, raw_bytes=encode_json(payload_b, pretty=True))

    compiled_a = compile_pack(manifest_a, resources_a)
    compiled_b = compile_pack(manifest_b, resources_b)

    assert compiled_a.model_dump_json() == compiled_b.model_dump_json()
    assert compiled_a.pack_digest == compiled_b.pack_digest


def test_material_change_changes_pack_digest(pack_factory, market_payload):
    changed = deepcopy(market_payload)
    changed["entity_types"][1]["attributes"].append({"attribute_id": "sku", "value_type": "string"})
    original_manifest, original_resources = pack_factory(market_payload)
    changed_manifest, changed_resources = pack_factory(changed)

    assert (
        compile_pack(original_manifest, original_resources).pack_digest
        != compile_pack(changed_manifest, changed_resources).pack_digest
    )


def test_unknown_module_contract_fails_closed(pack_factory, market_payload):
    manifest, resources = pack_factory(market_payload, contract="ace.intelligence.ontology/v2")

    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)

    diagnostic = exc_info.value.report.diagnostics[0]
    assert diagnostic.code == "unknown_module_contract"
    assert diagnostic.path == "modules.domain_ontology.contract"


def test_untrusted_manifest_uses_same_structured_diagnostic_surface(pack_factory, market_payload):
    manifest, resources = pack_factory(market_payload)
    payload = manifest.model_dump(mode="json")
    payload["executable"] = "python:module.callable"

    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack_document(encode_json(payload), resources)

    diagnostic = exc_info.value.report.diagnostics[0]
    assert diagnostic.code == "invalid_manifest"
    assert diagnostic.path == "manifest.executable"


def test_resource_set_and_digest_are_exact(pack_factory, market_payload):
    manifest, resources = pack_factory(market_payload)

    with pytest.raises(PackCompilationError, match="resource_set_mismatch"):
        compile_pack(manifest, {})

    tampered = dict(resources)
    tampered["modules/ontology.json"] += b" "
    with pytest.raises(PackCompilationError, match="digest_mismatch"):
        compile_pack(manifest, tampered)


@pytest.mark.parametrize("path", ["/absolute.json", "../escape.json", "modules\\ontology.json", "C:drive.json"])
def test_resource_paths_cannot_escape(path):
    with pytest.raises(ValidationError):
        PackResourceV1(resource_id="ontology", path=path, digest="sha256:" + "0" * 64)


def test_unknown_fields_and_unresolved_relations_fail(pack_factory, market_payload):
    unknown = deepcopy(market_payload)
    unknown["execute"] = "import os"
    manifest, resources = pack_factory(unknown)
    with pytest.raises(PackCompilationError) as unknown_error:
        compile_pack(manifest, resources)
    assert unknown_error.value.report.diagnostics[0].code == "invalid_module"

    unresolved = deepcopy(market_payload)
    unresolved["relation_types"][0]["target_entity_types"] = ["missing_type"]
    manifest, resources = pack_factory(unresolved)
    with pytest.raises(PackCompilationError, match="outside its module dependencies"):
        compile_pack(manifest, resources)


def test_declarative_booleans_and_dependency_collections_are_strict(pack_factory, market_payload):
    coerced = deepcopy(market_payload)
    coerced["entity_types"][0]["attributes"][0]["required"] = "yes"
    manifest, resources = pack_factory(coerced)
    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)
    assert exc_info.value.report.diagnostics[0].code == "invalid_module"

    with pytest.raises(ValidationError, match="must contain strings"):
        PackModuleRefV1(
            module_id="ontology",
            contract="ace.intelligence.ontology/v1alpha1",
            resource_id="ontology_resource",
            depends_on=("valid", 3),
        )


def test_duplicate_json_keys_are_rejected(pack_factory, market_payload):
    raw = (
        b'{"contract":"ace.intelligence.ontology/v1alpha1","module_id":"domain_ontology",'
        b'"module_id":"other","entity_types":[{"entity_type_id":"entity","attributes":[]}],'
        b'"relation_types":[]}'
    )
    manifest, resources = pack_factory(market_payload, raw_bytes=raw)

    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)

    assert exc_info.value.report.diagnostics[0].code == "invalid_json"


def test_module_dependency_cycles_are_rejected(market_payload):
    first = encode_json({"contract": "ace.intelligence.ontology/v1alpha1", "module_id": "first", **market_payload})
    second = encode_json(
        {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "second",
            "entity_types": [{"entity_type_id": "other", "attributes": []}],
            "relation_types": [],
        }
    )
    manifest = DomainPackManifestV1(
        metadata={"pack_id": "cycle_test", "version": "0.1.0", "display_name": "Cycle Test"},
        resources=(
            PackResourceV1(resource_id="first_resource", path="modules/first.json", digest=digest_bytes(first)),
            PackResourceV1(resource_id="second_resource", path="modules/second.json", digest=digest_bytes(second)),
        ),
        modules=(
            PackModuleRefV1(
                module_id="first",
                contract="ace.intelligence.ontology/v1alpha1",
                resource_id="first_resource",
                depends_on=("second",),
            ),
            PackModuleRefV1(
                module_id="second",
                contract="ace.intelligence.ontology/v1alpha1",
                resource_id="second_resource",
                depends_on=("first",),
            ),
        ),
    )

    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, {"modules/first.json": first, "modules/second.json": second})

    assert exc_info.value.report.diagnostics[0].code == "module_cycle"


def test_cross_module_relations_require_explicit_dependency():
    entities = encode_json(
        {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "entities",
            "entity_types": [{"entity_type_id": "competitor", "attributes": []}],
            "relation_types": [],
        }
    )
    products = encode_json(
        {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "products",
            "entity_types": [{"entity_type_id": "product", "attributes": []}],
            "relation_types": [
                {
                    "relation_type_id": "makes",
                    "source_entity_types": ["competitor"],
                    "target_entity_types": ["product"],
                }
            ],
        }
    )

    def manifest(depends_on=()):
        return DomainPackManifestV1(
            metadata={"pack_id": "module_linking", "version": "0.1.0", "display_name": "Module Linking"},
            resources=(
                PackResourceV1(
                    resource_id="entities_resource", path="modules/entities.json", digest=digest_bytes(entities)
                ),
                PackResourceV1(
                    resource_id="products_resource", path="modules/products.json", digest=digest_bytes(products)
                ),
            ),
            modules=(
                PackModuleRefV1(
                    module_id="entities",
                    contract="ace.intelligence.ontology/v1alpha1",
                    resource_id="entities_resource",
                ),
                PackModuleRefV1(
                    module_id="products",
                    contract="ace.intelligence.ontology/v1alpha1",
                    resource_id="products_resource",
                    depends_on=depends_on,
                ),
            ),
        )

    resources = {"modules/entities.json": entities, "modules/products.json": products}
    assert compile_pack(manifest(("entities",)), resources).metadata.pack_id == "module_linking"
    with pytest.raises(PackCompilationError, match="outside its module dependencies"):
        compile_pack(manifest(), resources)

    duplicate = encode_json(
        {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "products",
            "entity_types": [{"entity_type_id": "competitor", "attributes": []}],
            "relation_types": [],
        }
    )
    duplicate_manifest = manifest(("entities",)).model_copy(
        update={
            "resources": (
                PackResourceV1(
                    resource_id="entities_resource", path="modules/entities.json", digest=digest_bytes(entities)
                ),
                PackResourceV1(
                    resource_id="products_resource", path="modules/products.json", digest=digest_bytes(duplicate)
                ),
            )
        }
    )
    with pytest.raises(PackCompilationError, match="declared by multiple modules"):
        compile_pack(
            duplicate_manifest,
            {"modules/entities.json": entities, "modules/products.json": duplicate},
        )


def test_compiled_module_cannot_pair_payload_with_forged_digest(pack_factory, market_payload):
    manifest, resources = pack_factory(market_payload)
    module = compile_pack(manifest, resources).modules[0]
    material = module.model_dump(exclude={"module_digest"})

    with pytest.raises(ValidationError, match="digest does not match"):
        CompiledModuleV1(**material, module_digest="sha256:" + "0" * 64)
    with pytest.raises(ValidationError):
        CompiledModuleV1(
            module_id="domain_ontology",
            contract="ace.intelligence.ontology/v1alpha1",
            canonical_payload="{}",
            module_digest="sha256:" + "0" * 64,
        )


def test_deeply_nested_json_fails_with_structured_diagnostic(pack_factory, market_payload):
    raw = b"[" * 1_100 + b"0" + b"]" * 1_100
    manifest, resources = pack_factory(market_payload, raw_bytes=raw)

    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)

    assert exc_info.value.report.diagnostics[0].code in {"invalid_json", "invalid_module"}


def test_pack_versions_use_strict_semver():
    with pytest.raises(ValidationError):
        PackMetadataV1(pack_id="market", version="01.0.0", display_name="Market")
    with pytest.raises(ValidationError):
        PackMetadataV1(pack_id="market", version="1.0.0-.", display_name="Market")

    valid = PackMetadataV1(pack_id="market", version="1.0.0-alpha.1+build.5", display_name="Market")
    assert valid.version == "1.0.0-alpha.1+build.5"


def test_python_shaped_payload_is_never_executed(pack_factory, market_payload, tmp_path):
    marker = tmp_path / "should-not-exist"
    malicious = deepcopy(market_payload)
    malicious["python"] = f"__import__('pathlib').Path({str(marker)!r}).touch()"
    manifest, resources = pack_factory(malicious)

    with pytest.raises(PackCompilationError):
        compile_pack(manifest, resources)

    assert not marker.exists()
