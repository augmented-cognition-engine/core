from __future__ import annotations

import hashlib
import inspect
import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

import ace.intelligence.source_mapping as source_mapping_module
from ace.core import CanonicalSourceSnapshotV1Alpha1, SourceAcquisitionMode, canonical_json
from ace.intelligence import (
    ActivationState,
    AuthorityBindingV1,
    CapabilityBindingV1,
    IntelligenceResourceMode,
    LineageRelation,
    LineageResourceKind,
    LiveSourceMappingError,
    OrganizationOverlayV1,
    PreparedSourceMappingError,
    ResolvedSubjectBindingV1Alpha1,
    interpret_live_source_mapping,
    interpret_prepared_source_mapping,
)
from ace.intelligence.contracts.pack import CompiledModuleV1, DomainPackManifestV1
from ace.intelligence.packs.activation import compile_overlay, prepare_activation_revision, prepare_domain_activation
from ace.intelligence.packs.compiler import PackCompilationError, compile_pack
from ace.intelligence.packs.runtime import PreparedActivationBinding, bind_prepared_activation
from ace.testing import exercise_prepared_source_mapping
from tests.intelligence.conftest import digest_bytes, encode_json

pytestmark = pytest.mark.unit

OBSERVED_AT = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)
INGESTED_AT = datetime(2026, 8, 5, 10, 5, tzinfo=UTC)


def _fixture_documents(kind: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if kind == "numeric":
        ontology = {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "reading",
                    "attributes": [
                        {"attribute_id": "code", "value_type": "string", "required": True},
                        {"attribute_id": "value", "value_type": "number", "required": True},
                    ],
                }
            ],
            "relation_types": [],
        }
        mapping = {
            "contract": "ace.intelligence.source-mapping/v1alpha1",
            "module_id": "source_mapping",
            "mappings": [
                {
                    "mapping_id": "reading_snapshot",
                    "source_definition_ref": "source_definition:numeric",
                    "source_type_ref": "source:reading/v1",
                    "capability_requirement_id": "snapshot_capture",
                    "authority_request_id": "source_access",
                    "allowed_uri_schemes": ["memory", "https"],
                    "subject_binding_id": "primary_subject",
                    "entity_type_id": "reading",
                    "attribute_mappings": [
                        {
                            "attribute_id": "value",
                            "source_pointer": "/reading/value",
                            "transform": "decimal_text_to_number",
                            "min_length": 1,
                            "max_length": 24,
                        },
                        {
                            "attribute_id": "code",
                            "source_pointer": "/subject/code",
                            "transform": "copy",
                            "min_length": 2,
                            "max_length": 8,
                            "character_set": "ascii_upper",
                        },
                    ],
                    "static_confidence": 0.875,
                }
            ],
        }
        source = {"subject": {"code": "AX"}, "reading": {"value": "104.250"}}
        return ontology, mapping, source
    if kind == "categorical":
        ontology = {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "classification",
                    "attributes": [
                        {"attribute_id": "enabled", "value_type": "boolean", "required": True},
                        {"attribute_id": "label", "value_type": "string", "required": True},
                        {"attribute_id": "tags", "value_type": "string", "many": True},
                    ],
                }
            ],
            "relation_types": [],
        }
        mapping = {
            "contract": "ace.intelligence.source-mapping/v1alpha1",
            "module_id": "source_mapping",
            "mappings": [
                {
                    "mapping_id": "classification_snapshot",
                    "source_definition_ref": "source_definition:categorical",
                    "source_type_ref": "source:classification/v2",
                    "capability_requirement_id": "snapshot_capture",
                    "authority_request_id": "source_access",
                    "allowed_uri_schemes": ["https"],
                    "subject_binding_id": "primary_subject",
                    "entity_type_id": "classification",
                    "attribute_mappings": [
                        {
                            "attribute_id": "tags",
                            "source_pointer": "/records/0/tags",
                            "min_length": 2,
                            "max_length": 8,
                            "character_set": "ascii_upper",
                        },
                        {"attribute_id": "enabled", "source_pointer": "/records/0/flags/enabled"},
                        {
                            "attribute_id": "label",
                            "source_pointer": "/records/0/category/label",
                            "min_length": 2,
                            "max_length": 12,
                            "character_set": "ascii_upper",
                        },
                    ],
                    "static_confidence": 0.75,
                }
            ],
        }
        source = {
            "records": [
                {
                    "category": {"label": "READY"},
                    "flags": {"enabled": True},
                    "tags": ["ALPHA", "BETA"],
                }
            ]
        }
        return ontology, mapping, source
    raise AssertionError(f"unknown fixture: {kind}")


def _manifest_and_resources(
    ontology: dict[str, Any],
    mapping: dict[str, Any],
    *,
    mapping_dependencies: tuple[str, ...] = ("ontology",),
) -> tuple[DomainPackManifestV1, dict[str, bytes]]:
    ontology_bytes = encode_json(ontology)
    mapping_bytes = encode_json(mapping)
    resources = {
        "modules/ontology.json": ontology_bytes,
        "modules/source-mapping.json": mapping_bytes,
    }
    manifest = DomainPackManifestV1(
        metadata={
            "pack_id": "source_mapping_fixture",
            "version": "0.1.0",
            "display_name": "Source Mapping Fixture",
        },
        resources=(
            {
                "resource_id": "ontology_resource",
                "path": "modules/ontology.json",
                "digest": digest_bytes(ontology_bytes),
            },
            {
                "resource_id": "source_mapping_resource",
                "path": "modules/source-mapping.json",
                "digest": digest_bytes(mapping_bytes),
            },
        ),
        modules=(
            {
                "module_id": "ontology",
                "contract": "ace.intelligence.ontology/v1alpha1",
                "resource_id": "ontology_resource",
            },
            {
                "module_id": "source_mapping",
                "contract": "ace.intelligence.source-mapping/v1alpha1",
                "resource_id": "source_mapping_resource",
                "depends_on": mapping_dependencies,
            },
        ),
        capability_requirements=(
            {
                "requirement_id": "snapshot_capture",
                "capability": "source_snapshot",
                "contract": "ace.source.snapshot/v1alpha1",
            },
        ),
        authority_requests=({"request_id": "source_access", "authority": "source_read"},),
    )
    return manifest, resources


def _compiled(kind: str = "numeric", **manifest_options):
    ontology, mapping, _ = _fixture_documents(kind)
    manifest, resources = _manifest_and_resources(ontology, mapping, **manifest_options)
    return compile_pack(manifest, resources)


def _binding(compiled, *, product_id: str = "product:source-mapping-test") -> PreparedActivationBinding:
    overlay = compile_overlay(
        compiled,
        OrganizationOverlayV1(
            overlay_id="source_mapping_fixture",
            version="0.1.0",
            pack_id=compiled.metadata.pack_id,
            pack_version=compiled.metadata.version,
            pack_digest=compiled.pack_digest,
        ),
    )
    specification = prepare_domain_activation(
        product_id=product_id,
        activation_key="source_mapping_fixture",
        pack=compiled,
        overlay=overlay,
        compilation_receipt_ref="receipt:source-mapping-compilation",
        conformance_receipt_refs=("receipt:source-mapping-conformance",),
        capability_bindings=(
            CapabilityBindingV1(
                requirement_id="snapshot_capture",
                capability="source_snapshot",
                contract="ace.source.snapshot/v1alpha1",
                implementation_id="fixture_capture",
                implementation_version="0.1.0",
                artifact_digest="sha256:" + "a" * 64,
            ),
        ),
        authority_bindings=(
            AuthorityBindingV1(
                request_id="source_access",
                authority="source_read",
                grant_ref="grant:prepared-fixture",
            ),
        ),
    )
    revision = prepare_activation_revision(
        spec=specification,
        state=ActivationState.ACTIVE,
        actor_ref="principal:fixture-author",
        approval_receipt_ref="receipt:prepared-approval",
        occurred_at=datetime(2026, 8, 4, tzinfo=UTC),
    )
    return bind_prepared_activation(pack=compiled, revision=revision)


def _snapshot(
    kind: str,
    *,
    payload: Any | None = None,
    source_definition_ref: str | None = None,
    source_type_ref: str | None = None,
    source_uri: str = "https://example.invalid/snapshots/1",
    acquisition_mode: SourceAcquisitionMode = SourceAcquisitionMode.PREPARED_FIXTURE,
) -> CanonicalSourceSnapshotV1Alpha1:
    _, mapping, fixture_payload = _fixture_documents(kind)
    payload = fixture_payload if payload is None else payload
    payload_json = canonical_json(payload)
    return CanonicalSourceSnapshotV1Alpha1(
        source_definition_ref=source_definition_ref or f"source_definition:{kind}",
        source_type_ref=source_type_ref or mapping["mappings"][0]["source_type_ref"],
        source_uri=source_uri,
        captured_payload_json=payload_json,
        captured_payload_digest="sha256:" + hashlib.sha256(payload_json.encode()).hexdigest(),
        source_published_at=OBSERVED_AT - timedelta(hours=1),
        event_effective_at=OBSERVED_AT - timedelta(minutes=30),
        observed_at=OBSERVED_AT,
        ingested_at=INGESTED_AT,
        locator="record:1",
        acquisition_mode=acquisition_mode,
        acquisition_receipt_ref="receipt:fixture-acquisition",
        acquisition_receipt_digest="sha256:" + "b" * 64,
    )


def _subject(binding: PreparedActivationBinding, kind: str) -> ResolvedSubjectBindingV1Alpha1:
    entity_type = "reading" if kind == "numeric" else "classification"
    return ResolvedSubjectBindingV1Alpha1(
        product_id=binding.revision.spec.product_id,
        activation_revision=binding.reference,
        subject_binding_id="primary_subject",
        entity_type_id=entity_type,
        entity_ref=f"entity:{entity_type}-1",
    )


def _interpret(kind: str):
    compiled = _compiled(kind)
    binding = _binding(compiled)
    mapping_id = "reading_snapshot" if kind == "numeric" else "classification_snapshot"
    result = interpret_prepared_source_mapping(
        binding=binding,
        mapping_id=mapping_id,
        source_snapshot=_snapshot(kind),
        subject_binding=_subject(binding, kind),
    )
    return compiled, binding, result


def test_numeric_and_categorical_fixtures_use_one_branch_free_public_interpreter() -> None:
    signature = set(inspect.signature(interpret_prepared_source_mapping).parameters)
    assert signature == {"binding", "mapping_id", "source_snapshot", "subject_binding"}


def test_mapping_uses_semantic_state_time_and_keeps_actual_availability() -> None:
    compiled = _compiled("numeric")
    binding = _binding(compiled)
    subject = _subject(binding, "numeric")
    snapshot = _snapshot("numeric")

    def rematerialize(**updates):
        material = snapshot.model_dump(
            mode="python",
            exclude={"source_snapshot_ref", "source_snapshot_digest"},
        )
        material.update(updates)
        return CanonicalSourceSnapshotV1Alpha1.model_validate(material)

    event = interpret_prepared_source_mapping(
        binding=binding,
        mapping_id="reading_snapshot",
        source_snapshot=snapshot,
        subject_binding=subject,
    )
    publication = interpret_prepared_source_mapping(
        binding=binding,
        mapping_id="reading_snapshot",
        source_snapshot=rematerialize(event_effective_at=None),
        subject_binding=subject,
    )
    observation = interpret_prepared_source_mapping(
        binding=binding,
        mapping_id="reading_snapshot",
        source_snapshot=rematerialize(event_effective_at=None, source_published_at=None),
        subject_binding=subject,
    )

    assert event.observation.as_of == event.entity_snapshot.as_of == snapshot.event_effective_at
    assert publication.observation.as_of == publication.entity_snapshot.as_of == snapshot.source_published_at
    assert observation.observation.as_of == observation.entity_snapshot.as_of == snapshot.observed_at
    for mapped in (event, publication, observation):
        assert mapped.observation.ingested_at == INGESTED_AT
        assert mapped.entity_snapshot.projected_at == INGESTED_AT
        assert mapped.entity_snapshot.lineage[0].resource_as_of == mapped.observation.as_of
        assert mapped.entity_snapshot.lineage[0].resource_available_at == INGESTED_AT

    _, _, numeric = _interpret("numeric")
    _, _, categorical = _interpret("categorical")

    assert numeric.observation.payload.parsed_value() == {"code": "AX", "value": 104.25}
    assert numeric.entity_snapshot.attributes == numeric.observation.payload
    assert categorical.observation.payload.parsed_value() == {
        "enabled": True,
        "label": "READY",
        "tags": ["ALPHA", "BETA"],
    }
    assert categorical.entity_snapshot.attributes == categorical.observation.payload
    for result in (numeric, categorical):
        assert result.mode is IntelligenceResourceMode.PREPARED
        assert result.observation.mode is IntelligenceResourceMode.PREPARED
        assert result.entity_snapshot.mode is IntelligenceResourceMode.PREPARED
        assert len(result.entity_snapshot.lineage) == 1
        lineage = result.entity_snapshot.lineage[0]
        assert lineage.resource_id == result.observation.resource_id
        assert lineage.resource_digest == result.observation.resource_digest
        assert result.live_authority is result.live_acquisition is False

    compiled = _compiled("numeric")
    binding = _binding(compiled)
    conformance = exercise_prepared_source_mapping(
        binding=binding,
        mapping_id="reading_snapshot",
        source_snapshot=_snapshot("numeric"),
        subject_binding=_subject(binding, "numeric"),
    )
    assert conformance.attributes_json == '{"code":"AX","value":104.25}'
    assert conformance.result_mode is IntelligenceResourceMode.PREPARED
    assert conformance.observation_mode is IntelligenceResourceMode.PREPARED
    assert conformance.entity_snapshot_mode is IntelligenceResourceMode.PREPARED
    assert conformance.live_authority is conformance.live_acquisition is False
    assert conformance.lineage_kind is LineageResourceKind.OBSERVATION
    assert conformance.lineage_relation is LineageRelation.DERIVED_FROM
    assert conformance.lineage_resource_id == conformance.observation_id
    assert conformance.lineage_resource_digest == conformance.observation_digest
    assert conformance.lineage_resource_as_of == OBSERVED_AT - timedelta(minutes=30)
    assert conformance.lineage_resource_available_at == INGESTED_AT


def test_semantic_reordering_is_identity_stable_and_material_changes_are_not() -> None:
    ontology, mapping, _ = _fixture_documents("numeric")
    first_manifest, first_resources = _manifest_and_resources(ontology, mapping)
    reordered = deepcopy(mapping)
    reordered["mappings"][0]["attribute_mappings"].reverse()
    reordered["mappings"][0]["allowed_uri_schemes"].reverse()
    second_manifest, second_resources = _manifest_and_resources(
        {
            "relation_types": [],
            "entity_types": list(reversed(ontology["entity_types"])),
            **{
                "module_id": ontology["module_id"],
                "contract": ontology["contract"],
            },
        },
        reordered,
    )
    first = compile_pack(first_manifest, first_resources)
    second = compile_pack(second_manifest, second_resources)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.pack_digest == second.pack_digest

    changed = deepcopy(mapping)
    changed["mappings"][0]["static_confidence"] = 0.5
    changed_manifest, changed_resources = _manifest_and_resources(ontology, changed)
    assert compile_pack(changed_manifest, changed_resources).pack_digest != first.pack_digest

    positive_zero = deepcopy(mapping)
    positive_zero["mappings"][0]["static_confidence"] = 0.0
    negative_zero = deepcopy(positive_zero)
    negative_zero["mappings"][0]["static_confidence"] = -0.0
    positive_manifest, positive_resources = _manifest_and_resources(ontology, positive_zero)
    negative_manifest, negative_resources = _manifest_and_resources(ontology, negative_zero)
    assert (
        compile_pack(positive_manifest, positive_resources).model_dump_json()
        == compile_pack(
            negative_manifest,
            negative_resources,
        ).model_dump_json()
    )


def test_direct_compiled_ir_rejects_non_normalized_mapping_order_and_signed_zero() -> None:
    compiled = _compiled("numeric")
    source_mapping = next(
        item for item in compiled.modules if item.contract == "ace.intelligence.source-mapping/v1alpha1"
    )
    base_payload = source_mapping.model_dump(
        mode="python",
        exclude={"canonical_payload", "module_digest"},
    )

    for mutate in (
        lambda value: value["mappings"][0]["attribute_mappings"].reverse(),
        lambda value: value["mappings"][0].update(static_confidence=-0.0),
    ):
        material = json.loads(source_mapping.canonical_payload)
        mutate(material)
        non_normalized = canonical_json(material)
        with pytest.raises(ValidationError, match="typed canonical normalization"):
            CompiledModuleV1(
                **base_payload,
                canonical_payload=non_normalized,
                module_digest="sha256:" + hashlib.sha256(non_normalized.encode()).hexdigest(),
            )


def test_two_equivalent_rules_emit_distinct_durable_exact_mapping_provenance() -> None:
    ontology, mapping, _ = _fixture_documents("numeric")
    alternate = deepcopy(mapping["mappings"][0])
    alternate["mapping_id"] = "reading_snapshot_alternate"
    mapping["mappings"].append(alternate)
    manifest, resources = _manifest_and_resources(ontology, mapping)
    compiled = compile_pack(manifest, resources)
    binding = _binding(compiled)
    source_snapshot = _snapshot("numeric")
    subject = _subject(binding, "numeric")

    first = interpret_prepared_source_mapping(
        binding=binding,
        mapping_id="reading_snapshot",
        source_snapshot=source_snapshot,
        subject_binding=subject,
    )
    second = interpret_prepared_source_mapping(
        binding=binding,
        mapping_id="reading_snapshot_alternate",
        source_snapshot=source_snapshot,
        subject_binding=subject,
    )

    assert first.observation.payload == second.observation.payload
    assert first.entity_snapshot.attributes == second.entity_snapshot.attributes
    assert first.observation.source_mapping is not None
    assert second.observation.source_mapping is not None
    assert first.observation.source_mapping.activation_revision == binding.reference
    assert first.observation.source_mapping.compiled_pack_id == compiled.compiled_pack_id
    assert first.observation.source_mapping.module_id == "source_mapping"
    assert first.observation.source_mapping.module_digest == second.observation.source_mapping.module_digest
    assert first.observation.source_mapping.mapping_id == "reading_snapshot"
    assert second.observation.source_mapping.mapping_id == "reading_snapshot_alternate"
    assert first.observation.source_mapping.mapping_digest != second.observation.source_mapping.mapping_digest
    assert first.observation.resource_id != second.observation.resource_id
    assert first.entity_snapshot.resource_id != second.entity_snapshot.resource_id


def test_inert_pointer_tokens_that_resemble_code_remain_data() -> None:
    ontology, mapping, _ = _fixture_documents("numeric")
    code_mapping = next(item for item in mapping["mappings"][0]["attribute_mappings"] if item["attribute_id"] == "code")
    code_mapping["source_pointer"] = "/python:version"
    manifest, resources = _manifest_and_resources(ontology, mapping)
    compiled = compile_pack(manifest, resources)
    binding = _binding(compiled)
    result = interpret_prepared_source_mapping(
        binding=binding,
        mapping_id="reading_snapshot",
        source_snapshot=_snapshot(
            "numeric",
            payload={"python:version": "AX", "reading": {"value": "104.250"}},
        ),
        subject_binding=_subject(binding, "numeric"),
    )

    assert result.observation.payload.parsed_value()["code"] == "AX"


def test_exact_prepared_outputs_are_pinned() -> None:
    _, _, numeric = _interpret("numeric")
    _, _, categorical = _interpret("categorical")

    assert (
        numeric.observation.resource_id,
        numeric.observation.resource_digest,
        numeric.entity_snapshot.resource_id,
        numeric.entity_snapshot.resource_digest,
    ) == (
        "observation:1a12528799c8192eef0f450608da203b",
        "sha256:1a12528799c8192eef0f450608da203b228c5dc220a19c267aaa14fe75efc035",
        "entity_snapshot:935bb7668ce0cce0655877877793db66",
        "sha256:935bb7668ce0cce0655877877793db663ee7aa3e7c3b6dcfc58264fed40f197e",
    )
    assert (
        categorical.observation.resource_id,
        categorical.observation.resource_digest,
        categorical.entity_snapshot.resource_id,
        categorical.entity_snapshot.resource_digest,
    ) == (
        "observation:db365d16a6ed9a399d36f90a96a67621",
        "sha256:db365d16a6ed9a399d36f90a96a676213f0aa37677f6b31be48324787addafe1",
        "entity_snapshot:377c44ca271b576f3768768b47a23446",
        "sha256:377c44ca271b576f3768768b47a234468b22288eb7e56da9c762f5923487bb84",
    )


@pytest.mark.parametrize(
    ("mutate", "code", "path_fragment"),
    [
        (
            lambda value: value["mappings"][0]["attribute_mappings"][0].update(source_pointer="$.reading.value"),
            "invalid_module",
            "source_pointer",
        ),
        (
            lambda value: value["mappings"][0]["attribute_mappings"][0].update(source_pointer="/reading/~2"),
            "invalid_module",
            "source_pointer",
        ),
        (
            lambda value: value["mappings"][0]["attribute_mappings"][0].update(transform="evaluate"),
            "invalid_module",
            "transform",
        ),
        (
            lambda value: value["mappings"][0]["attribute_mappings"][0].update(attribute_id="unknown"),
            "unknown_target_attribute",
            "attribute_mappings.unknown.attribute_id",
        ),
        (
            lambda value: value["mappings"][0].update(capability_requirement_id="unknown"),
            "unknown_capability_requirement",
            "capability_requirement_id",
        ),
        (
            lambda value: value["mappings"][0].update(authority_request_id="unknown"),
            "unknown_authority_request",
            "authority_request_id",
        ),
        (
            lambda value: value["mappings"][0]["attribute_mappings"].pop(),
            "missing_required_outputs",
            "attribute_mappings",
        ),
        (
            lambda value: value["mappings"][0].update(product_id="/unsafe"),
            "protected_mapping_field",
            "product_id",
        ),
        (
            lambda value: value["mappings"][0].update(callback="python:module.callable"),
            "unsafe_executable_field",
            "callback",
        ),
    ],
)
def test_invalid_selectors_operators_targets_references_and_unsafe_shapes_have_paths(
    mutate,
    code,
    path_fragment,
) -> None:
    ontology, mapping, _ = _fixture_documents("numeric")
    mutate(mapping)
    manifest, resources = _manifest_and_resources(ontology, mapping)

    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)

    diagnostic = exc_info.value.report.diagnostics[0]
    assert diagnostic.code == code
    assert path_fragment in diagnostic.path


def test_duplicate_outputs_extra_fields_nonfinite_values_and_missing_dependency_fail_closed() -> None:
    ontology, mapping, _ = _fixture_documents("numeric")
    duplicate = deepcopy(mapping)
    duplicate["mappings"][0]["attribute_mappings"].append(deepcopy(duplicate["mappings"][0]["attribute_mappings"][0]))
    manifest, resources = _manifest_and_resources(ontology, duplicate)
    with pytest.raises(PackCompilationError, match="attribute_mappings"):
        compile_pack(manifest, resources)

    extra = deepcopy(mapping)
    extra["mappings"][0]["attribute_mappings"][0]["unknown"] = True
    manifest, resources = _manifest_and_resources(ontology, extra)
    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)
    assert "unknown" in exc_info.value.report.diagnostics[0].path

    manifest, resources = _manifest_and_resources(ontology, mapping)
    path = "modules/source-mapping.json"
    raw = encode_json(mapping).replace(b'"static_confidence":0.875', b'"static_confidence":NaN')
    resources[path] = raw
    resource = next(item for item in manifest.resources if item.path == path)
    manifest = manifest.model_copy(
        update={
            "resources": tuple(
                item.model_copy(update={"digest": digest_bytes(raw)}) if item == resource else item
                for item in manifest.resources
            )
        }
    )
    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)
    assert exc_info.value.report.diagnostics[0].code == "invalid_json"

    manifest, resources = _manifest_and_resources(ontology, mapping, mapping_dependencies=())
    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)
    assert exc_info.value.report.diagnostics[0].code == "missing_ontology_dependency"
    assert exc_info.value.report.diagnostics[0].path == "modules.source_mapping.depends_on"


def test_deep_and_lone_surrogate_mapping_documents_use_bounded_compiler_errors() -> None:
    ontology, mapping, _ = _fixture_documents("numeric")
    manifest, resources = _manifest_and_resources(ontology, mapping)
    mapping_path = "modules/source-mapping.json"
    mapping_resource = next(item for item in manifest.resources if item.path == mapping_path)

    for raw in (
        b"[" * 1_100 + b"0" + b"]" * 1_100,
        encode_json(mapping).replace(b'"/reading/value"', b'"/reading\\ud800value"'),
    ):
        supplied = {**resources, mapping_path: raw}
        changed_manifest = manifest.model_copy(
            update={
                "resources": tuple(
                    item.model_copy(update={"digest": digest_bytes(raw)}) if item == mapping_resource else item
                    for item in manifest.resources
                )
            }
        )
        with pytest.raises(PackCompilationError) as exc_info:
            compile_pack(changed_manifest, supplied)
        assert exc_info.value.report.diagnostics[0].code in {
            "invalid_json",
            "invalid_unicode_scalar",
            "mapping_too_deep",
        }


def test_transform_output_and_bounded_string_constraints_are_compiler_checked() -> None:
    ontology, mapping, _ = _fixture_documents("numeric")
    incompatible = deepcopy(mapping)
    incompatible["mappings"][0]["attribute_mappings"][0]["attribute_id"] = "code"
    incompatible["mappings"][0]["attribute_mappings"].pop()
    manifest, resources = _manifest_and_resources(ontology, incompatible)
    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)
    assert exc_info.value.report.diagnostics[0].code in {
        "incompatible_transform_output",
        "missing_required_outputs",
    }

    categorical_ontology, categorical_mapping, _ = _fixture_documents("categorical")
    wrong_constraint = deepcopy(categorical_mapping)
    enabled = next(
        item for item in wrong_constraint["mappings"][0]["attribute_mappings"] if item["attribute_id"] == "enabled"
    )
    enabled["min_length"] = 1
    manifest, resources = _manifest_and_resources(categorical_ontology, wrong_constraint)
    with pytest.raises(PackCompilationError) as exc_info:
        compile_pack(manifest, resources)
    assert exc_info.value.report.diagnostics[0].code == "incompatible_string_constraints"

    bad_bounds = deepcopy(mapping)
    bad_bounds["mappings"][0]["attribute_mappings"][0].update(min_length=10, max_length=2)
    manifest, resources = _manifest_and_resources(ontology, bad_bounds)
    with pytest.raises(PackCompilationError, match="min_length"):
        compile_pack(manifest, resources)


def test_core_source_snapshot_is_canonical_content_addressed_and_time_bounded() -> None:
    snapshot = _snapshot("numeric")
    reordered = _snapshot("numeric", payload={"reading": {"value": "104.250"}, "subject": {"code": "AX"}})
    assert snapshot.captured_payload_json == reordered.captured_payload_json
    assert snapshot.source_snapshot_ref == reordered.source_snapshot_ref
    assert snapshot.as_of == snapshot.ingested_at

    with pytest.raises(ValidationError, match="captured_payload_digest"):
        CanonicalSourceSnapshotV1Alpha1(
            **{
                **snapshot.model_dump(mode="python", exclude={"source_snapshot_ref", "source_snapshot_digest"}),
                "captured_payload_digest": "sha256:" + "0" * 64,
            }
        )
    with pytest.raises(ValidationError, match="ingested_at"):
        CanonicalSourceSnapshotV1Alpha1(
            **{
                **snapshot.model_dump(mode="python", exclude={"source_snapshot_ref", "source_snapshot_digest"}),
                "ingested_at": snapshot.observed_at - timedelta(seconds=1),
            }
        )
    with pytest.raises(ValidationError, match="source_snapshot_ref"):
        CanonicalSourceSnapshotV1Alpha1(
            **{**snapshot.model_dump(mode="python"), "source_snapshot_ref": "source_snapshot:" + "0" * 32}
        )


def test_rfc6901_root_empty_key_escapes_and_array_index_rules() -> None:
    ontology = {
        "contract": "ace.intelligence.ontology/v1alpha1",
        "module_id": "ontology",
        "entity_types": [
            {
                "entity_type_id": "reading",
                "attributes": [{"attribute_id": "value", "value_type": "string", "required": True}],
            }
        ],
        "relation_types": [],
    }

    def interpret_pointer(pointer: str, payload: Any):
        mapping = {
            "contract": "ace.intelligence.source-mapping/v1alpha1",
            "module_id": "source_mapping",
            "mappings": [
                {
                    "mapping_id": "reading_snapshot",
                    "source_definition_ref": "source_definition:numeric",
                    "source_type_ref": "source:reading/v1",
                    "capability_requirement_id": "snapshot_capture",
                    "authority_request_id": "source_access",
                    "allowed_uri_schemes": ["https"],
                    "subject_binding_id": "primary_subject",
                    "entity_type_id": "reading",
                    "attribute_mappings": [{"attribute_id": "value", "source_pointer": pointer}],
                    "static_confidence": 0.875,
                }
            ],
        }
        manifest, resources = _manifest_and_resources(ontology, mapping)
        binding = _binding(compile_pack(manifest, resources))
        return interpret_prepared_source_mapping(
            binding=binding,
            mapping_id="reading_snapshot",
            source_snapshot=_snapshot("numeric", payload=payload),
            subject_binding=_subject(binding, "numeric"),
        )

    assert interpret_pointer("", "ROOT").observation.payload.parsed_value() == {"value": "ROOT"}
    assert interpret_pointer("/", {"": "EMPTY"}).observation.payload.parsed_value() == {"value": "EMPTY"}
    assert interpret_pointer("/a~0b/c~1d", {"a~b": {"c/d": "ESCAPED"}}).observation.payload.parsed_value() == {
        "value": "ESCAPED"
    }
    with pytest.raises(PreparedSourceMappingError, match="non-canonical array index"):
        interpret_pointer("/items/01", {"items": ["ZERO", "ONE"]})


def test_source_snapshot_numeric_tokens_cannot_collapse_distinct_decimal_lexemes() -> None:
    snapshot = _snapshot("numeric")
    base = snapshot.model_dump(
        mode="python",
        exclude={"source_snapshot_ref", "source_snapshot_digest"},
    )
    for token in ("9007199254740992.0", "9007199254740993.0"):
        payload_json = f'{{"value":{token}}}'
        with pytest.raises(ValidationError, match="non-integer JSON numeric tokens"):
            CanonicalSourceSnapshotV1Alpha1(
                **{
                    **base,
                    "captured_payload_json": payload_json,
                    "captured_payload_digest": "sha256:" + hashlib.sha256(payload_json.encode()).hexdigest(),
                }
            )

    first = _snapshot("numeric", payload={"value": 9_007_199_254_740_992})
    second = _snapshot("numeric", payload={"value": 9_007_199_254_740_993})
    assert first.captured_payload_digest != second.captured_payload_digest
    assert first.source_snapshot_ref != second.source_snapshot_ref


def test_source_snapshot_rejects_lone_surrogates_and_invalid_uri_octets() -> None:
    snapshot = _snapshot("numeric")
    base = snapshot.model_dump(
        mode="python",
        exclude={"source_snapshot_ref", "source_snapshot_digest"},
    )
    surrogate_payload = '{"token":"\\ud800"}'
    with pytest.raises(ValidationError, match="Unicode scalar"):
        CanonicalSourceSnapshotV1Alpha1(
            **{
                **base,
                "captured_payload_json": surrogate_payload,
                "captured_payload_digest": "sha256:" + hashlib.sha256(surrogate_payload.encode()).hexdigest(),
            }
        )

    for uri in (
        "https://example.invalid/%",
        "https://example.invalid/%2",
        "https://example.invalid/%GG",
        "https://example.invalid/raw\x7fdel",
    ):
        with pytest.raises(ValidationError, match="source_uri"):
            CanonicalSourceSnapshotV1Alpha1(**{**base, "source_uri": uri})


def test_runtime_rejects_wrong_scope_source_type_uri_subject_pointer_decimal_and_strings() -> None:
    compiled = _compiled("numeric")
    binding = _binding(compiled)
    subject = _subject(binding, "numeric")
    common = {
        "binding": binding,
        "mapping_id": "reading_snapshot",
        "source_snapshot": _snapshot("numeric"),
        "subject_binding": subject,
    }

    foreign_binding = _binding(compiled, product_id="product:foreign-scope")
    with pytest.raises(PreparedSourceMappingError):
        interpret_prepared_source_mapping(**{**common, "binding": foreign_binding})

    wrong_reference = replace(
        binding,
        reference=binding.reference.model_copy(update={"revision": binding.reference.revision + 1}),
    )
    with pytest.raises(PreparedSourceMappingError):
        interpret_prepared_source_mapping(**{**common, "binding": wrong_reference})

    wrong_source = common["source_snapshot"].model_copy(update={"source_snapshot_ref": "source_snapshot:" + "0" * 32})
    with pytest.raises(PreparedSourceMappingError):
        interpret_prepared_source_mapping(**{**common, "source_snapshot": wrong_source})

    failures = (
        _snapshot("numeric", source_definition_ref="source_definition:foreign"),
        _snapshot("numeric", source_type_ref="source:other/v1"),
        _snapshot("numeric", source_uri="file:/snapshot.json"),
        _snapshot("numeric", payload={"subject": {"code": "AX"}, "reading": {}}),
        _snapshot("numeric", payload={"subject": {"code": "AX"}, "reading": {"value": "NaN"}}),
        _snapshot(
            "numeric",
            payload={"subject": {"code": "AX"}, "reading": {"value": "9007199254740993"}},
        ),
        _snapshot("numeric", payload={"subject": {"code": "lower"}, "reading": {"value": "1.0"}}),
    )
    for source_snapshot in failures:
        with pytest.raises(PreparedSourceMappingError):
            interpret_prepared_source_mapping(**{**common, "source_snapshot": source_snapshot})

    wrong_subjects = (
        subject.model_copy(update={"product_id": "product:foreign-scope"}),
        subject.model_copy(update={"activation_revision": foreign_binding.reference}),
        subject.model_copy(update={"subject_binding_id": "other_subject"}),
        subject.model_copy(update={"entity_type_id": "classification"}),
    )
    for wrong_subject in wrong_subjects:
        with pytest.raises(PreparedSourceMappingError):
            interpret_prepared_source_mapping(**{**common, "subject_binding": wrong_subject})


def test_oversized_normalized_output_uses_the_public_fail_closed_error() -> None:
    ontology, mapping, _ = _fixture_documents("numeric")
    code_mapping = next(item for item in mapping["mappings"][0]["attribute_mappings"] if item["attribute_id"] == "code")
    code_mapping.pop("max_length")
    manifest, resources = _manifest_and_resources(ontology, mapping)
    compiled = compile_pack(manifest, resources)
    binding = _binding(compiled)

    with pytest.raises(PreparedSourceMappingError) as exc_info:
        interpret_prepared_source_mapping(
            binding=binding,
            mapping_id="reading_snapshot",
            source_snapshot=_snapshot(
                "numeric",
                payload={"subject": {"code": "A" * 33_000}, "reading": {"value": "1.0"}},
            ),
            subject_binding=_subject(binding, "numeric"),
        )

    assert exc_info.value.__cause__ is None


def test_aggregate_output_budget_stops_before_repeated_later_selectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attribute_ids = [f"value_{index:03d}" for index in range(256)]
    ontology = {
        "contract": "ace.intelligence.ontology/v1alpha1",
        "module_id": "ontology",
        "entity_types": [
            {
                "entity_type_id": "reading",
                "attributes": [
                    {"attribute_id": attribute_id, "value_type": "string", "required": True}
                    for attribute_id in attribute_ids
                ],
            }
        ],
        "relation_types": [],
    }
    mapping = {
        "contract": "ace.intelligence.source-mapping/v1alpha1",
        "module_id": "source_mapping",
        "mappings": [
            {
                "mapping_id": "reading_snapshot",
                "source_definition_ref": "source_definition:numeric",
                "source_type_ref": "source:reading/v1",
                "capability_requirement_id": "snapshot_capture",
                "authority_request_id": "source_access",
                "allowed_uri_schemes": ["https"],
                "subject_binding_id": "primary_subject",
                "entity_type_id": "reading",
                "attribute_mappings": [
                    {"attribute_id": attribute_id, "source_pointer": "/shared"} for attribute_id in attribute_ids
                ],
                "static_confidence": 0.875,
            }
        ],
    }
    manifest, resources = _manifest_and_resources(ontology, mapping)
    binding = _binding(compile_pack(manifest, resources))
    pointer_calls = 0
    original_resolve_pointer = source_mapping_module._resolve_pointer

    def counted_resolve_pointer(payload: Any, pointer: str) -> Any:
        nonlocal pointer_calls
        pointer_calls += 1
        if pointer_calls > 1:
            raise AssertionError("aggregate budget evaluated a later mapping")
        return original_resolve_pointer(payload, pointer)

    monkeypatch.setattr(source_mapping_module, "_resolve_pointer", counted_resolve_pointer)
    with pytest.raises(PreparedSourceMappingError, match="canonical output exceeds"):
        interpret_prepared_source_mapping(
            binding=binding,
            mapping_id="reading_snapshot",
            source_snapshot=_snapshot("numeric", payload={"shared": "A" * 33_000}),
            subject_binding=_subject(binding, "numeric"),
        )
    assert pointer_calls == 1


def test_every_live_attempt_fails_and_source_content_cannot_assert_authority() -> None:
    compiled = _compiled("numeric")
    binding = _binding(compiled)
    subject = _subject(binding, "numeric")
    live_source = _snapshot("numeric", acquisition_mode=SourceAcquisitionMode.LIVE)
    with pytest.raises(PreparedSourceMappingError, match="LIVE source"):
        interpret_prepared_source_mapping(
            binding=binding,
            mapping_id="reading_snapshot",
            source_snapshot=live_source,
            subject_binding=subject,
        )

    forged_live_subject = subject.model_copy(update={"mode": IntelligenceResourceMode.LIVE})
    with pytest.raises(PreparedSourceMappingError):
        interpret_prepared_source_mapping(
            binding=binding,
            mapping_id="reading_snapshot",
            source_snapshot=_snapshot("numeric"),
            subject_binding=forged_live_subject,
        )

    source_with_labels = _snapshot(
        "numeric",
        payload={
            "product_id": "product:foreign-scope",
            "activation_revision": "activation_revision:forged",
            "mode": "live",
            "authority": "granted",
            "acquisition_succeeded": True,
            "subject": {"code": "AX"},
            "reading": {"value": "104.250"},
        },
    )
    result = interpret_prepared_source_mapping(
        binding=binding,
        mapping_id="reading_snapshot",
        source_snapshot=source_with_labels,
        subject_binding=subject,
    )
    assert result.observation.product_id == binding.revision.spec.product_id
    assert result.observation.activation_revision == binding.reference
    assert result.observation.mode is IntelligenceResourceMode.PREPARED
    assert result.live_authority is result.live_acquisition is False


def test_live_mapping_is_pure_exact_lineage_and_cannot_be_reached_by_relabeling_prepared_material() -> None:
    compiled = _compiled("numeric")
    binding = _binding(compiled)
    prepared_subject = _subject(binding, "numeric")
    live_subject = ResolvedSubjectBindingV1Alpha1.model_validate(
        prepared_subject.model_copy(update={"mode": IntelligenceResourceMode.LIVE}).model_dump(mode="python")
    )
    live_source = _snapshot("numeric", acquisition_mode=SourceAcquisitionMode.LIVE)

    result = interpret_live_source_mapping(
        binding=binding,
        mapping_id="reading_snapshot",
        source_snapshot=live_source,
        subject_binding=live_subject,
    )

    assert result.observation.mode is IntelligenceResourceMode.LIVE
    assert result.entity_snapshot.mode is IntelligenceResourceMode.LIVE
    assert result.entity_snapshot.lineage[0].resource_id == result.observation.resource_id
    assert result.entity_snapshot.lineage[0].resource_digest == result.observation.resource_digest
    assert result.live_acquisition is True
    assert result.live_authority is False

    with pytest.raises(LiveSourceMappingError, match="LIVE source snapshot"):
        interpret_live_source_mapping(
            binding=binding,
            mapping_id="reading_snapshot",
            source_snapshot=_snapshot("numeric"),
            subject_binding=live_subject,
        )
    with pytest.raises(LiveSourceMappingError, match="LIVE subject binding"):
        interpret_live_source_mapping(
            binding=binding,
            mapping_id="reading_snapshot",
            source_snapshot=live_source,
            subject_binding=prepared_subject,
        )
