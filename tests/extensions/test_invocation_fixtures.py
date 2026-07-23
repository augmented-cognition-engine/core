from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.engine.extensions.invocation import (
    ExtensionInvocationEnvelope,
    ExtensionInvocationReceipt,
    build_extension_receipt,
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
