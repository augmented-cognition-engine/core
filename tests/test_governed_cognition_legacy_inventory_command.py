"""Operator receipt tests for the deployment-wide legacy inventory command."""

from __future__ import annotations

import json

import pytest

from core.engine.cognition.legacy_import import map_skill_row
from scripts.run_governed_cognition_legacy_inventory import _run_receipt, _write_once


def _skill(product: str | None) -> dict:
    return {
        "id": f"skill:{product or 'unscoped'}",
        "product": product,
        "slug": "legacy_skill",
        "name": "Legacy skill",
        "description": "Migration fixture.",
        "discipline": "architecture",
        "tier": "custom",
        "jobs": [],
        "activation_signals": [],
    }


def test_run_receipt_counts_every_disposition_and_has_stable_identity() -> None:
    receipts = (map_skill_row(_skill("product:alpha")), map_skill_row(_skill(None)))
    first = _run_receipt(
        receipts,
        deployment_id="test-deployment",
        schema_head=171,
        persisted=True,
        verified_persisted_count=2,
    )
    second = _run_receipt(
        receipts,
        deployment_id="test-deployment",
        schema_head=171,
        persisted=True,
        verified_persisted_count=2,
    )
    assert first["run_id"] == second["run_id"]
    assert first["receipt_set_hash"] == second["receipt_set_hash"]
    assert first["total_receipts"] == 2
    assert first["deployment_id"] == "test-deployment"
    assert first["schema_head"] == 171
    assert first["verified_persisted_count"] == 2
    assert first["disposition_counts"] == {
        "mapped_review_required": 1,
        "quarantined": 1,
    }


def test_receipt_output_refuses_implicit_overwrite(tmp_path) -> None:
    output = tmp_path / "legacy-inventory.json"
    _write_once(output, {"run_id": "first"}, replace=False)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _write_once(output, {"run_id": "second"}, replace=False)
    _write_once(output, {"run_id": "second"}, replace=True)
    assert json.loads(output.read_text()) == {"run_id": "second"}
