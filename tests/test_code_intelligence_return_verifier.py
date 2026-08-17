"""Adversarial boundaries for the coding-agent return verifier."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.engine.code_intelligence.contracts import CodingAgentReturnV1Alpha1
from scripts.verify_code_intelligence_return import (
    MAX_CODING_AGENT_RETURN_JSON_BYTES,
    load_bounded_return,
)


def _payload() -> dict:
    return {
        "contract": "ace.code-intelligence.coding-agent-return/v1alpha1",
        "receiver_ref": "coding-agent:test",
        "handoff_id": "coding_agent_handoff:" + "a" * 32,
        "index_id": "code_index:" + "b" * 32,
        "lens_id": "atrium_code_lens:" + "c" * 32,
        "manifest_id": "code_context_manifest:" + "d" * 32,
        "disposition": "change_proposed",
        "summary": "Bounded return.",
        "consumed_block_ids": ["code_context_block:" + "e" * 32],
        "changed_paths": ["target.py"],
        "verification_refs": ["pytest:target"],
        "uncertainties": ["Runtime dispatch was not observed."],
        "submitted_at": "2026-08-15T00:00:00Z",
        "claims_source_authority": False,
        "claims_reasoning_authority": False,
        "claims_delivery_authority": False,
        "claims_effect_authority": False,
    }


def test_return_contract_rejects_oversized_fields_and_lists() -> None:
    oversized_field = _payload()
    oversized_field["uncertainties"] = ["x" * 4_001]
    with pytest.raises(ValidationError, match="uncertainties entries"):
        CodingAgentReturnV1Alpha1.model_validate(oversized_field)

    oversized_list = _payload()
    oversized_list["verification_refs"] = [f"pytest:{index}" for index in range(65)]
    with pytest.raises(ValidationError, match="verification_refs exceeds 64 items"):
        CodingAgentReturnV1Alpha1.model_validate(oversized_list)


def test_return_verifier_rejects_total_bytes_before_json_parsing(tmp_path: Path) -> None:
    path = tmp_path / "oversized-return.json"
    path.write_bytes(b"{" + b"x" * MAX_CODING_AGENT_RETURN_JSON_BYTES)

    with pytest.raises(ValueError, match="byte limit"):
        load_bounded_return(path)


def test_return_contract_rejects_extra_or_authority_tampering() -> None:
    extra = _payload()
    extra["unexpected"] = "tampered"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CodingAgentReturnV1Alpha1.model_validate(extra)

    authority = _payload()
    authority["claims_effect_authority"] = True
    with pytest.raises(ValidationError):
        CodingAgentReturnV1Alpha1.model_validate(authority)


def test_return_verifier_accepts_a_bounded_exact_json_document(tmp_path: Path) -> None:
    path = tmp_path / "return.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    returned = load_bounded_return(path)

    assert returned.changed_paths == ("target.py",)
    assert returned.claims_effect_authority is False
