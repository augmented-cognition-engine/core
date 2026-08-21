"""Compile the shipped Personal Intelligence Domain Pack through the real compiler.

This proves the declarative ``domain_packs/personal_intelligence`` artifact is a
valid, content-addressed, stable v1 Domain Pack -- not merely well-formed JSON --
by running it through ``compile_pack_document`` and the provider-free conformance
runner exactly as the installed-pack resolver would.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ace.intelligence.contracts.diagnostics import PackCompatibilityStatus
from ace.intelligence.contracts.orientation import OrientationModuleV1
from ace.intelligence.contracts.pack import OntologyModuleV1
from ace.intelligence.contracts.synthesis import SynthesisModuleV1Alpha2
from ace.intelligence.packs.compiler import (
    compile_pack_document,
    compile_pack_document_with_report,
)
from ace.testing import run_domain_pack_conformance

pytestmark = pytest.mark.unit

PACK_ROOT = Path(__file__).resolve().parents[2] / "domain_packs" / "personal_intelligence"

EXPECTED_ENTITY_TYPES = {
    "commitment",
    "concept",
    "decision",
    "document",
    "note",
    "person",
    "project",
    "revision",
    "source",
}
EXPECTED_RELATION_TYPES = {
    "authored_by",
    "commitment_owned_by_person",
    "commitment_supports_decision",
    "concept_relates_to_concept",
    "decision_affects_project",
    "derived_from",
    "document_mentions_person",
    "note_about_project",
    "note_references_concept",
    "person_member_of_project",
    "revises",
}


def _load() -> tuple[bytes, dict[str, bytes], bytes]:
    manifest = (PACK_ROOT / "manifest.json").read_bytes()
    declared = json.loads(manifest)
    resources = {item["path"]: (PACK_ROOT / item["path"]).read_bytes() for item in declared["resources"]}
    fixture = (PACK_ROOT / "conformance" / "activation_golden_fixture.json").read_bytes()
    return manifest, resources, fixture


def test_personal_pack_compiles_as_stable_v1() -> None:
    manifest, resources, _ = _load()

    pack = compile_pack_document(manifest, resources)

    assert pack.contract == "ace.intelligence.compiled-domain-pack/v1"
    assert pack.compiler_contract == "ace.intelligence.pack-compiler/v1"
    assert pack.intelligence_contract == "ace.intelligence.runtime/v1"
    assert pack.manifest_contract == "ace.intelligence.domain-pack-manifest/v1"
    assert pack.metadata.pack_id == "personal_intelligence"
    assert pack.metadata.version == "1.0.0"
    # Content-addressed identity is derived from the exact material.
    assert pack.compiled_pack_id is not None and pack.compiled_pack_id.startswith("pack_ir:")
    assert pack.pack_digest is not None and pack.pack_digest.startswith("sha256:")


def test_personal_pack_models_the_personal_knowledge_domain() -> None:
    manifest, resources, _ = _load()

    pack = compile_pack_document(manifest, resources)
    ontology = next(
        OntologyModuleV1.model_validate_json(module.canonical_payload)
        for module in pack.modules
        if module.module_id == "personal_ontology"
    )

    entity_types = {entity.entity_type_id for entity in ontology.entity_types}
    relation_types = {relation.relation_type_id for relation in ontology.relation_types}
    assert entity_types == EXPECTED_ENTITY_TYPES
    assert relation_types == EXPECTED_RELATION_TYPES

    note = next(entity for entity in ontology.entity_types if entity.entity_type_id == "note")
    required = {attribute.attribute_id for attribute in note.attributes if attribute.required}
    assert required == {"note_ref", "title", "body"}


def test_personal_pack_declares_governed_local_source_policy() -> None:
    manifest, resources, _ = _load()

    pack = compile_pack_document(manifest, resources)

    # The pack requests only inert, non-escalating source authority/capability.
    # The read request names the existing observe_read grant class so the fixed
    # local-owner grants created by setup can satisfy activation exactly
    # (PI13 §8.1); no pack-private authority vocabulary exists to resolve.
    assert [item.capability for item in pack.capability_requirements] == ["source_snapshot"]
    assert [item.authority for item in pack.authority_requests] == ["observe_read"]
    assert {module.module_id for module in pack.modules} == {
        "personal_ontology",
        "personal_local_sources",
        "personal_orientation",
        "personal_orientation_templates",
    }


def test_personal_pack_declares_the_frozen_initial_orientation_policy() -> None:
    """PI13 §8.3: exact declarative policy/template/persona IDs, and no WS5 policy."""

    manifest, resources, _ = _load()
    fixture = json.loads((PACK_ROOT / "conformance" / "initial_orientation_fixture.json").read_bytes())

    pack = compile_pack_document(manifest, resources)
    orientation = next(
        OrientationModuleV1.model_validate_json(module.canonical_payload)
        for module in pack.modules
        if module.module_id == "personal_orientation"
    )
    synthesis = next(
        SynthesisModuleV1Alpha2.model_validate_json(module.canonical_payload)
        for module in pack.modules
        if module.module_id == "personal_orientation_templates"
    )

    [policy] = orientation.initial_orientation_policies
    assert policy.policy_id == fixture["orientation_policy_id"] == "personal_initial_orientation"
    assert policy.brief_template_id == fixture["brief_template_id"] == "personal_orientation_first_brief"
    assert list(policy.persona_ids) == fixture["persona_ids"] == ["personal_orientation_analyst"]
    [persona] = orientation.personas
    assert persona.persona_id == "personal_orientation_analyst"
    [template] = synthesis.brief_templates
    assert template.template_id == fixture["brief_template_id"]
    assert template.brief_type == fixture["brief_type"]
    assert list(template.required_sections) == fixture["required_sections"]
    assert template.recommendation_required is fixture["recommendation_required"]
    assert template.claim_policy == fixture["claim_policy"]

    # Change detection and Signal-routing policy remain WS5 scope: the Personal
    # Pack must declare no detection module and no personas/routing module.
    contracts = {module.contract for module in pack.modules}
    assert not any(contract.startswith("ace.intelligence.detection/") for contract in contracts)
    assert not any(contract.startswith("ace.intelligence.personas/") for contract in contracts)


def test_personal_pack_passes_provider_free_conformance() -> None:
    manifest, resources, fixture = _load()

    report = compile_pack_document_with_report(manifest, resources)
    receipt = run_domain_pack_conformance(
        manifest_document=manifest,
        resources=resources,
        fixture_document=fixture,
    )

    assert receipt.passed is True
    assert receipt.diagnostics == ()
    assert receipt.compatibility_status is PackCompatibilityStatus.SUPPORTED
    assert receipt.pack_id == "personal_intelligence"
    # Conformance binds to the exact compilation material.
    assert receipt.compilation_result_id == report.compilation.result_id
    assert receipt.compilation_result_digest == report.compilation.result_digest
