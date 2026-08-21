"""Prove the installed Personal pack's local_markdown_note mapping resolves real fixture bytes.

This closes the gap between the declarative ``modules/source_mapping.json``
pointers and what a real markdown-normalized capture payload actually looks
like. The ``ace-local-source-normalizers``/``ace-local-source-snapshot``
adapter packages are not installed in this test environment, so this proves
the pointer contract against the exact one-heading-section normalization the
shipped ``tests/fixtures/pi13_ws0/notes/vault.md`` fixture produces (its only
heading is ``# PI13 WS0 Vault Note``, so it normalizes to exactly one
``anchor_kind="heading"`` unit) -- no executor and no payload mutation
involved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ace.core.contracts import canonical_json
from ace.intelligence.contracts.source_mapping import SourceMappingModuleV1
from ace.intelligence.packs.compiler import compile_pack_document

pytestmark = pytest.mark.unit

PACK_ROOT = Path(__file__).resolve().parents[2] / "domain_packs" / "personal_intelligence"
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "pi13_ws0"
VAULT_NOTE = FIXTURE_ROOT / "notes" / "vault.md"
PROFILE = PACK_ROOT / "onboarding_profile.json"

# The exact first normalized unit each shipped adapter produces for its fixture,
# captured from the real ``ace-local-source-normalizers`` output. Mapping
# pointers address the normalized payload, so these are the shapes the pack's
# declarations must resolve against.
FIRST_UNIT_BY_KIND = {
    "local_pdf_document": {"anchor_kind": "page", "anchor_value": "1", "text": "PI13 fixture"},
    "local_csv_table": {"anchor_kind": "row", "anchor_value": "1", "text": "id: 1 | name: alpha | value: 10"},
    "local_json_document": {"anchor_kind": "pointer", "anchor_value": "/fixture", "text": "pi13_ws0"},
}


def _pointer(payload: object, pointer: str) -> object:
    current = payload
    for segment in pointer.split("/")[1:]:
        segment = segment.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(segment)]
        else:
            current = current[segment]
    return current


def _load_pack():
    manifest = (PACK_ROOT / "manifest.json").read_bytes()
    declared = json.loads(manifest)
    resources = {item["path"]: (PACK_ROOT / item["path"]).read_bytes() for item in declared["resources"]}
    return compile_pack_document(manifest, resources)


def test_local_markdown_note_mapping_resolves_the_real_normalized_vault_fixture() -> None:
    pack = _load_pack()
    module_ir = next(module for module in pack.modules if module.module_id == "personal_local_sources")
    mapping_module = SourceMappingModuleV1.model_validate_json(module_ir.canonical_payload)
    mapping = next(item for item in mapping_module.mappings if item.mapping_id == "local_markdown_note")

    # The fixture has exactly one Markdown heading, so the real
    # ace-local-markdown-source normalizer produces exactly one section unit
    # for it; its text is the fixture's own body paragraph, read fresh here.
    raw = VAULT_NOTE.read_text()
    heading = "PI13 WS0 Vault Note"
    assert f"# {heading}" in raw
    body_text = raw.split(f"# {heading}", 1)[1].strip()
    assert body_text.startswith("This fixture")

    payload = json.loads(
        canonical_json(
            [
                {"anchor_kind": "heading", "anchor_value": heading, "text": body_text},
            ]
        )
    )

    attributes = {item.attribute_id: item.source_pointer for item in mapping.attribute_mappings}
    assert attributes == {
        "note_ref": "/0/anchor_value",
        "title": "/0/anchor_value",
        "body": "/0/text",
    }

    assert _pointer(payload, attributes["note_ref"]) == "PI13 WS0 Vault Note"
    assert _pointer(payload, attributes["title"]) == "PI13 WS0 Vault Note"
    assert _pointer(payload, attributes["body"]) == payload[0]["text"]


def _mapping_module():
    pack = _load_pack()
    module_ir = next(module for module in pack.modules if module.module_id == "personal_local_sources")
    return SourceMappingModuleV1.model_validate_json(module_ir.canonical_payload)


def test_profile_advertised_source_kinds_are_exactly_the_packs_mapped_kinds() -> None:
    """A kind the onboarding profile advertises but the pack cannot map is a
    promise the journey cannot keep; a mapped kind the profile never offers is
    unreachable. The two sets must be identical."""

    profile = json.loads(PROFILE.read_bytes())
    advertised = {source_id for group in profile["source_groups"] for source_id in group["source_ids"]}
    mapped = {item.source_definition_ref for item in _mapping_module().mappings}

    assert advertised == mapped, (
        f"advertised-only={sorted(advertised - mapped)} mapped-only={sorted(mapped - advertised)}"
    )


@pytest.mark.parametrize("source_definition_ref", sorted(FIRST_UNIT_BY_KIND))
def test_every_local_source_kind_maps_its_real_normalized_first_unit(source_definition_ref: str) -> None:
    """PDF, CSV, and JSON must resolve their declared attributes against the
    exact unit shape their shipped adapter really produces."""

    unit = FIRST_UNIT_BY_KIND[source_definition_ref]
    payload = json.loads(canonical_json([unit]))
    mapping = next(item for item in _mapping_module().mappings if item.source_definition_ref == source_definition_ref)

    attributes = {item.attribute_id: item.source_pointer for item in mapping.attribute_mappings}
    assert set(attributes) >= {"document_ref", "title", "body"}
    resolved = {name: _pointer(payload, pointer) for name, pointer in attributes.items()}
    assert resolved["document_ref"] == unit["anchor_value"]
    assert resolved["title"] == unit["anchor_value"]
    assert resolved["body"] == unit["text"]
    assert mapping.allowed_uri_schemes == ("file",)
    assert mapping.entity_type_id == "document"


def test_every_mapped_entity_type_and_attribute_is_declared_by_the_pack_ontology() -> None:
    """Mappings may only fill attributes the ontology actually declares."""

    pack = _load_pack()
    ontology_ir = next(module for module in pack.modules if module.module_id == "personal_ontology")
    ontology = json.loads(ontology_ir.canonical_payload)
    declared = {
        entity["entity_type_id"]: {item["attribute_id"] for item in entity["attributes"]}
        for entity in ontology["entity_types"]
    }

    for mapping in _mapping_module().mappings:
        assert mapping.entity_type_id in declared, mapping.mapping_id
        for attribute in mapping.attribute_mappings:
            assert attribute.attribute_id in declared[mapping.entity_type_id], (
                f"{mapping.mapping_id} maps undeclared attribute {attribute.attribute_id}"
            )
