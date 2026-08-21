"""The Personal pack must be able to notice that an admitted source changed.

WS4 made all four local kinds mappable and citable. Without a declared detector
the journey can admit a revised document and still have nothing to compare, so
J6 could never move. Packet section 10 authorized the content-revision family
for exactly this; these tests hold the Personal pack's use of it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ace.intelligence import ActivationState, OrganizationOverlayV1
from ace.intelligence.contracts.activation import AuthorityBindingV1, CapabilityBindingV1
from ace.intelligence.contracts.detection import ContentRevisionRuleV1, DetectionModuleV1Alpha3
from ace.intelligence.contracts.source_mapping import SourceMappingModuleV1
from ace.intelligence.packs.activation import compile_overlay, prepare_activation_revision, prepare_domain_activation
from ace.intelligence.packs.compiler import compile_pack_document
from ace.intelligence.packs.runtime import bind_prepared_activation, resolve_detector_rule

pytestmark = pytest.mark.unit

PACK_ROOT = Path(__file__).resolve().parents[2] / "domain_packs" / "personal_intelligence"
ACTIVATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
WATCHED_ATTRIBUTE = "body"


def _load_pack():
    manifest = (PACK_ROOT / "manifest.json").read_bytes()
    declared = json.loads(manifest)
    resources = {item["path"]: (PACK_ROOT / item["path"]).read_bytes() for item in declared["resources"]}
    return compile_pack_document(manifest, resources)


def _module(pack, module_id: str, model):
    module_ir = next(module for module in pack.modules if module.module_id == module_id)
    return model.model_validate_json(module_ir.canonical_payload)


def _detection(pack) -> DetectionModuleV1Alpha3:
    return _module(pack, "personal_change_detection", DetectionModuleV1Alpha3)


async def _binding(tmp_path):
    """Bind the real installed Personal pack, including its exact conformance evidence."""

    from tests.test_local_first_run_bootstrap import _installed_personal_pack

    artifact, _ = await _installed_personal_pack(tmp_path)
    pack = artifact.pack
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="personal_detection_test",
            version="0.1.0",
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
        ),
    )
    spec = prepare_domain_activation(
        product_id="product:personal-detection",
        activation_key=pack.metadata.pack_id,
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref=artifact.compilation.result_id,
        conformance_receipts=artifact.conformance_receipts,
        capability_bindings=tuple(
            CapabilityBindingV1(
                requirement_id=item.requirement_id,
                capability=item.capability,
                contract=item.contract,
                implementation_id="local_source_snapshot_provider",
                implementation_version="0.1.0",
                artifact_digest="sha256:" + "4" * 64,
            )
            for item in pack.capability_requirements
        ),
        authority_bindings=tuple(
            AuthorityBindingV1(
                request_id=item.request_id,
                authority=item.authority,
                grant_ref=f"authority_grant:{item.request_id}",
            )
            for item in pack.authority_requests
        ),
    )
    revision = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:test-author",
        approval_receipt_ref="receipt:prepared-approval",
        occurred_at=ACTIVATED_AT - timedelta(days=1),
    )
    return pack, bind_prepared_activation(pack=pack, revision=revision)


def test_every_mapped_entity_type_can_be_watched_for_revision() -> None:
    """A source kind the pack can admit but never notice changing is a journey
    that silently goes stale."""

    pack = _load_pack()
    mapped_entity_types = {
        item.entity_type_id for item in _module(pack, "personal_local_sources", SourceMappingModuleV1).mappings
    }
    watched = {rule.entity_type_id for rule in _detection(pack).content_revision_rules}

    assert mapped_entity_types, "the pack maps no source kinds"
    assert watched == mapped_entity_types, f"unwatched={sorted(mapped_entity_types - watched)}"


def test_each_rule_watches_the_mapped_body_declared_by_the_ontology() -> None:
    pack = _load_pack()
    ontology = json.loads(next(m for m in pack.modules if m.module_id == "personal_ontology").canonical_payload)
    declared = {
        entity["entity_type_id"]: {item["attribute_id"] for item in entity["attributes"]}
        for entity in ontology["entity_types"]
    }
    mappings = {
        item.entity_type_id: {attribute.attribute_id for attribute in item.attribute_mappings}
        for item in _module(pack, "personal_local_sources", SourceMappingModuleV1).mappings
    }

    for rule in _detection(pack).content_revision_rules:
        assert isinstance(rule, ContentRevisionRuleV1)
        assert rule.attribute_id == WATCHED_ATTRIBUTE
        # Watched and context attributes must be declared *and* actually filled
        # by the source mapping, or the detector can never fire on real material.
        assert rule.attribute_id in declared[rule.entity_type_id]
        assert rule.attribute_id in mappings[rule.entity_type_id]
        for context_attribute in rule.context_attribute_ids:
            assert context_attribute in declared[rule.entity_type_id]
            assert context_attribute in mappings[rule.entity_type_id]
        assert rule.shift_type and rule.signal_type


@pytest.mark.asyncio
async def test_each_declared_detector_resolves_through_the_bound_pack(tmp_path) -> None:
    pack, binding = await _binding(tmp_path)
    for rule in _detection(pack).content_revision_rules:
        resolved = resolve_detector_rule(binding, detector_id=rule.detector_id)
        assert resolved == rule
