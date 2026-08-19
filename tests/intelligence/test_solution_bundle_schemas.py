"""Published Solution Bundle JSON Schemas stay discoverable and fresh (PI10)."""

from __future__ import annotations

import json

import pytest

from ace.intelligence.contracts.solution_bundle import (
    SolutionBundleManifestV1,
    SolutionBundleResolutionReceiptV1,
)
from ace.intelligence.schemas import schema_text

pytestmark = pytest.mark.unit


def test_solution_bundle_schema_index_is_discoverable() -> None:
    index = json.loads(schema_text("solution-bundle-contracts-v1.json"))
    assert index["contract"] == "ace.intelligence.solution-bundle-schema-index/v1"
    manifest_schema = json.loads(schema_text(index["manifest_schema"]))
    receipt_schema = json.loads(schema_text(index["resolution_receipt_schema"]))
    assert manifest_schema["properties"]["contract"]["const"] == "ace.intelligence.solution-bundle-manifest/v1alpha1"
    assert (
        receipt_schema["properties"]["contract"]["const"]
        == "ace.intelligence.solution-bundle-resolution-receipt/v1alpha1"
    )
    assert receipt_schema["properties"]["authority_stage"]["const"] == "resolved"


def test_published_manifest_schema_matches_the_live_contract_exactly() -> None:
    published = json.loads(schema_text("solution-bundle-manifest-v1.schema.json"))
    assert published == SolutionBundleManifestV1.model_json_schema()


def test_published_resolution_receipt_schema_matches_the_live_contract_exactly() -> None:
    published = json.loads(schema_text("solution-bundle-resolution-receipt-v1.schema.json"))
    assert published == SolutionBundleResolutionReceiptV1.model_json_schema()
