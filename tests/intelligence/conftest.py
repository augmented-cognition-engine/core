from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import pytest

from ace.intelligence.contracts.pack import (
    AuthorityRequestV1,
    CapabilityRequirementV1,
    DomainPackManifestV1,
    OverlaySlotDeclarationV1,
    OverlayValueKind,
    PackMetadataV1,
    PackModuleRefV1,
    PackResourceV1,
)


def encode_json(value: Any, *, pretty: bool = False) -> bytes:
    options: dict[str, Any] = {"ensure_ascii": False, "sort_keys": not pretty}
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return json.dumps(value, **options).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


@pytest.fixture
def pack_factory() -> Callable[..., tuple[DomainPackManifestV1, dict[str, bytes]]]:
    def factory(
        payload: dict[str, Any],
        *,
        pack_id: str = "market_intelligence",
        display_name: str = "Market Intelligence",
        module_id: str = "domain_ontology",
        raw_bytes: bytes | None = None,
        capability_requirements: tuple[CapabilityRequirementV1, ...] = (),
        authority_requests: tuple[AuthorityRequestV1, ...] = (),
        overlay_slots: tuple[OverlaySlotDeclarationV1, ...] = (),
        contract: str = "ace.intelligence.ontology/v1alpha1",
    ) -> tuple[DomainPackManifestV1, dict[str, bytes]]:
        module_payload = dict(payload)
        module_payload.setdefault("contract", "ace.intelligence.ontology/v1alpha1")
        module_payload.setdefault("module_id", module_id)
        resource_bytes = raw_bytes if raw_bytes is not None else encode_json(module_payload)
        path = "modules/ontology.json"
        manifest = DomainPackManifestV1(
            metadata=PackMetadataV1(pack_id=pack_id, version="0.1.0", display_name=display_name),
            resources=(
                PackResourceV1(
                    resource_id="ontology_resource",
                    path=path,
                    digest=digest_bytes(resource_bytes),
                ),
            ),
            modules=(
                PackModuleRefV1(
                    module_id=module_id,
                    contract=contract,
                    resource_id="ontology_resource",
                ),
            ),
            capability_requirements=capability_requirements,
            authority_requests=authority_requests,
            overlay_slots=overlay_slots,
        )
        return manifest, {path: resource_bytes}

    return factory


@pytest.fixture
def market_payload() -> dict[str, Any]:
    return {
        "entity_types": [
            {
                "entity_type_id": "competitor",
                "attributes": [{"attribute_id": "name", "value_type": "string", "required": True}],
            },
            {
                "entity_type_id": "product",
                "attributes": [
                    {"attribute_id": "price", "value_type": "number"},
                    {"attribute_id": "name", "value_type": "string", "required": True},
                ],
            },
        ],
        "relation_types": [
            {
                "relation_type_id": "makes",
                "source_entity_types": ["competitor"],
                "target_entity_types": ["product"],
            }
        ],
    }


@pytest.fixture
def threat_payload() -> dict[str, Any]:
    return {
        "entity_types": [
            {"entity_type_id": "threat_actor", "attributes": []},
            {"entity_type_id": "malware", "attributes": []},
        ],
        "relation_types": [
            {
                "relation_type_id": "uses",
                "source_entity_types": ["threat_actor"],
                "target_entity_types": ["malware"],
            }
        ],
    }


@pytest.fixture
def activation_declarations():
    return {
        "capabilities": (
            CapabilityRequirementV1(
                requirement_id="public_snapshot",
                capability="source_snapshot",
                contract="ace.source.snapshot/v1alpha1",
            ),
        ),
        "authorities": (AuthorityRequestV1(request_id="read_public_source", authority="source_read"),),
        "slots": (
            OverlaySlotDeclarationV1(
                slot_id="watched_subjects",
                value_kind=OverlayValueKind.STRING_LIST,
                required=True,
            ),
        ),
    }
