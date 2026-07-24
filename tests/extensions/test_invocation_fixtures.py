from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.engine.extensions.invocation import (
    ExtensionInvocationEnvelope,
    ExtensionInvocationReceipt,
    build_extension_receipt,
    normalize_extension_receipt,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "extension_invocations"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_valid_and_degraded_v1_compatibility_fixtures():
    assert (
        ExtensionInvocationEnvelope.model_validate(_load("valid-v1.json")).contract_version == "extension-invocation-v1"
    )
    assert (
        ExtensionInvocationReceipt.model_validate(_load("degraded-receipt-v1.json")).contract_version
        == "extension-invocation-receipt-v1"
    )


def test_unknown_contract_fixture_fails_closed():
    with pytest.raises(ValidationError):
        ExtensionInvocationEnvelope.model_validate(_load("unknown-version.json"))


def test_malicious_private_metadata_fixture_is_not_projected_publicly():
    receipt = build_extension_receipt(
        {
            "id": "task:malicious",
            "status": "failed",
            "error": {"code": "failed", "message": "token=also-private"},
        },
        _load("malicious-metadata.json"),
    )
    serialized = json.dumps(receipt)
    assert "do-not-leak" not in serialized
    assert "also-private" not in serialized
    assert "<redacted>" in serialized


def test_future_stored_outcome_fails_closed_without_reinterpreting_artifacts():
    task = {
        "id": "task:future-outcome",
        "status": "completed",
        "output": "Usable Core output.",
        "execution": {"state": "complete"},
        "reasoning_trace": {"provenance": {"provider": "fixture", "model": "fixture:model"}},
        "extension_invocation": _load("malicious-metadata.json"),
    }
    receipt = normalize_extension_receipt(
        _load("future-outcome-receipt-v1.json"),
        task=task,
    )

    assert receipt["coverage"]["state"] == "degraded"
    assert "unsupported_extension_outcome_version" in receipt["coverage"]["missing_or_degraded"]
    assert receipt["outcome"]["contract_version"] == "product.product-check-outcome-v1"
    assert receipt["outcome"]["artifact_refs"] == []
    assert receipt["artifacts"] == []
    assert receipt["raw_core_output"] == {
        "available": True,
        "content": "Usable Core output.",
    }
    assert "future-outcome-private" not in json.dumps(receipt)


def test_malformed_stored_outcome_fails_closed_without_leaking_private_state():
    task = {
        "id": "task:malformed-outcome",
        "status": "completed",
        "output": "Usable Core output.",
        "execution": {"state": "complete"},
        "reasoning_trace": {"provenance": {"provider": "fixture", "model": "fixture:model"}},
        "extension_invocation": _load("malicious-metadata.json"),
    }
    receipt = normalize_extension_receipt(
        _load("malformed-outcome-receipt-v1.json"),
        task=task,
    )

    assert receipt["coverage"]["state"] == "degraded"
    assert "extension_outcome_invalid" in receipt["coverage"]["missing_or_degraded"]
    assert receipt["outcome"]["artifact_refs"] == []
    assert receipt["artifacts"] == []
    assert receipt["raw_core_output"]["content"] == "Usable Core output."
    assert "malformed-outcome-private" not in json.dumps(receipt)
