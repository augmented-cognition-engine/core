"""Reconcile Slice 6 detached Code Intelligence evidence against the installed contracts.

This suite never re-executes a historical command, invokes Codex, or touches the
network. It replays only frozen, checked-in bytes and revalidates them under the
currently accepted (stronger) contracts. Where the frozen material-use bytes are
expected to be incompatible with the current full-journey contract, that
incompatibility is asserted explicitly -- it is documented history, not a defect.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import socket
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from core.engine.code_intelligence.contracts import (
    CodeIntelligenceJourneyV1Alpha1,
    CodeIntelligenceReplayExpectationV1Alpha1,
)
from core.engine.code_intelligence.external_agent import ExternalAgentReplayExpectationV1Alpha1
from core.engine.code_intelligence.living_run import validate_single_chain_replay_envelope
from scripts.verify_code_intelligence_external_agent_round_trip import replay_external_agent_archive

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_EVIDENCE = _PROJECT_ROOT / "docs" / "evidence"
_ARTIFACTS = _EVIDENCE / "artifacts"


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_tar_members(path: Path) -> dict[str, bytes]:
    """Extract a plain (non-deterministic-manifest) tar.gz, failing closed on any unsafe member."""

    with tarfile.open(path, mode="r:gz") as archive:
        infos = archive.getmembers()
        names = [item.name for item in infos]
        assert len(names) == len(set(names)), f"duplicate archive member names in {path.name}"
        for item in infos:
            assert item.isreg(), f"non-regular archive member in {path.name}: {item.name}"
            assert not Path(item.name).is_absolute(), f"absolute archive member path in {path.name}: {item.name}"
            assert ".." not in Path(item.name).parts, f"path traversal in {path.name}: {item.name}"
        return {item.name: archive.extractfile(item).read() for item in infos}


# ---------------------------------------------------------------------------
# 1. Frozen input byte counts/hashes and safe exact archive inventories
# ---------------------------------------------------------------------------


def test_single_chain_evidence_bytes_and_archive_inventory_match_the_receipt() -> None:
    evidence = _load_json(_EVIDENCE / "code-intelligence-single-chain-living-run-v1.json")
    artifact = evidence["durable_replay_artifact"]
    archive_path = _PROJECT_ROOT / artifact["path"]
    encoded = archive_path.read_bytes()
    assert len(encoded) == artifact["byte_count"]
    assert _sha256_hex(encoded) == artifact["sha256"]

    members = _safe_tar_members(archive_path)
    assert sorted(members) == sorted(item["path"] for item in artifact["members"])
    for expected_member in artifact["members"]:
        payload = members[expected_member["path"]]
        assert len(payload) == expected_member["byte_count"]
        assert _sha256_hex(payload) == expected_member["sha256"]

    for predecessor in evidence["predecessor_evidence"]:
        payload = (_PROJECT_ROOT / predecessor["path"]).read_bytes()
        assert len(payload) == predecessor["byte_count"]
        assert _sha256_hex(payload) == predecessor["sha256"]


def test_external_agent_evidence_bytes_and_archive_inventory_match_the_receipt() -> None:
    evidence = _load_json(_EVIDENCE / "code-intelligence-external-agent-round-trip-v1.json")
    archive_receipt = evidence["archive"]
    encoded = (_PROJECT_ROOT / archive_receipt["path"]).read_bytes()
    assert len(encoded) == archive_receipt["encoded_byte_count"]
    assert _sha256_hex(encoded) == archive_receipt["encoded_sha256"]

    decoded = base64.b64decode(b"".join(encoded.split()), validate=True)
    assert len(decoded) == archive_receipt["decoded_byte_count"]
    assert f"sha256:{_sha256_hex(decoded)}" == archive_receipt["decoded_sha256"]
    assert archive_receipt["decoded_member_count"] == 20 == len(evidence["members"])

    with tarfile.open(fileobj=io.BytesIO(decoded), mode="r:gz") as archive:
        observed = {
            item.name: {"byte_count": item.size, "sha256": _sha256_hex(archive.extractfile(item).read())}
            for item in archive.getmembers()
        }
    assert sorted(observed) == sorted(item["path"] for item in evidence["members"])
    for expected_member in evidence["members"]:
        actual = observed[expected_member["path"]]
        assert actual["byte_count"] == expected_member["byte_count"]
        assert actual["sha256"] == expected_member["sha256"]


def test_material_use_archive_bytes_and_member_closure_match_the_receipt() -> None:
    receipt = _load_json(_EVIDENCE / "code-intelligence-material-use-receipt-v1.json")
    artifact = receipt["durable_replay_artifact"]
    archive_path = _PROJECT_ROOT / artifact["path"]
    encoded = archive_path.read_bytes()
    assert len(encoded) == artifact["byte_count"]
    assert _sha256_hex(encoded) == artifact["sha256"]

    members = _safe_tar_members(archive_path)
    assert sorted(members) == sorted(item["path"] for item in artifact["members"])
    for expected_member in artifact["members"]:
        payload = members[expected_member["path"]]
        assert len(payload) == expected_member["byte_count"]
        assert _sha256_hex(payload) == expected_member["sha256"]


# ---------------------------------------------------------------------------
# 2. Installed/current single-chain paired replay under the stronger accepted contracts
# ---------------------------------------------------------------------------


def test_single_chain_installed_paired_replay_succeeds_and_binds_predecessor_hashes() -> None:
    evidence = _load_json(_EVIDENCE / "code-intelligence-single-chain-living-run-v1.json")
    artifact = evidence["durable_replay_artifact"]
    archive_path = _PROJECT_ROOT / artifact["path"]
    members = _safe_tar_members(archive_path)
    raw = members[artifact["members"][0]["path"]]

    expectation = CodeIntelligenceReplayExpectationV1Alpha1.model_validate(evidence["replay_expectation"])
    run = validate_single_chain_replay_envelope(raw, expectation)
    assert run.run_id == evidence["identities"]["run_id"]

    # The paired replay is bound to the exact predecessor installed-wheel evidence hashes;
    # a rewritten predecessor record would not carry this same digest.
    for predecessor in evidence["predecessor_evidence"]:
        payload = (_PROJECT_ROOT / predecessor["path"]).read_bytes()
        assert _sha256_hex(payload) == predecessor["sha256"]


def test_single_chain_replay_rejects_a_tampered_raw_member() -> None:
    evidence = _load_json(_EVIDENCE / "code-intelligence-single-chain-living-run-v1.json")
    expectation = CodeIntelligenceReplayExpectationV1Alpha1.model_validate(evidence["replay_expectation"])
    with pytest.raises(ValueError, match="differs from externally expected bytes"):
        validate_single_chain_replay_envelope(b"{}", expectation)


# ---------------------------------------------------------------------------
# 3. External-agent base64 decode, exact inventory, and paired/unpaired/partial replay
# ---------------------------------------------------------------------------


def test_external_agent_paired_unpaired_and_partial_replay_with_no_execution_or_network(
    tmp_path: Path,
) -> None:
    evidence = _load_json(_EVIDENCE / "code-intelligence-external-agent-round-trip-v1.json")
    archive_receipt = evidence["archive"]
    encoded = (_PROJECT_ROOT / archive_receipt["path"]).read_bytes()
    decoded = base64.b64decode(b"".join(encoded.split()), validate=True)
    archive_path = tmp_path / "external-agent-round-trip.tar.gz"
    archive_path.write_bytes(decoded)
    expectation = ExternalAgentReplayExpectationV1Alpha1.model_validate(evidence["replay_expectation"])

    def _forbid_subprocess(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("evidence replay attempted to spawn a subprocess")

    def _forbid_socket(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("evidence replay attempted a network connection")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(subprocess, "run", _forbid_subprocess)
        mp.setattr(subprocess, "Popen", _forbid_subprocess)
        mp.setattr(socket.socket, "connect", _forbid_socket)

        unpaired = replay_external_agent_archive(archive_path)
        assert unpaired["accepted"] is False
        assert unpaired["trust_root_authenticated"] is False
        assert unpaired["contract_validated"] is True

        paired = replay_external_agent_archive(
            archive_path,
            expected_archive_sha256=archive_receipt["decoded_sha256"],
            expected_archive_byte_count=archive_receipt["decoded_byte_count"],
            expected_replay_expectation=expectation,
        )
        assert paired["accepted"] is True
        assert paired["trust_root_authenticated"] is True
        assert paired["acceptance_run_id"] == evidence["identities"]["acceptance_run_id"]

        with pytest.raises(ValueError, match="must be supplied together"):
            replay_external_agent_archive(archive_path, expected_archive_sha256=archive_receipt["decoded_sha256"])
        with pytest.raises(ValueError, match="must be supplied together"):
            replay_external_agent_archive(
                archive_path, expected_archive_byte_count=archive_receipt["decoded_byte_count"]
            )


def test_external_agent_paired_replay_rejects_a_mismatched_trust_root(tmp_path: Path) -> None:
    evidence = _load_json(_EVIDENCE / "code-intelligence-external-agent-round-trip-v1.json")
    archive_receipt = evidence["archive"]
    encoded = (_PROJECT_ROOT / archive_receipt["path"]).read_bytes()
    decoded = base64.b64decode(b"".join(encoded.split()), validate=True)
    archive_path = tmp_path / "external-agent-round-trip.tar.gz"
    archive_path.write_bytes(decoded)

    with pytest.raises(AssertionError, match="differs from paired machine evidence"):
        replay_external_agent_archive(
            archive_path,
            expected_archive_sha256="sha256:" + "0" * 64,
            expected_archive_byte_count=archive_receipt["decoded_byte_count"],
            expected_replay_expectation=ExternalAgentReplayExpectationV1Alpha1.model_validate(
                evidence["replay_expectation"]
            ),
        )


# ---------------------------------------------------------------------------
# 4. Material-use archive closure and the explicitly expected current-contract incompatibility
# ---------------------------------------------------------------------------


# The exact, bounded set of stable historical reasons the frozen full-journey capture is
# expected to be incompatible with the current, stricter contract. Anything else -- a
# different loc, a different error type, or a message that has drifted -- is an unrelated
# and unexpected failure, not this documented history, and must fail the test.
_HANDOFF_NAMES_DIFFERENT_MANIFEST = "handoff_receipt_names_different_manifest"
_LEGACY_EXTRA_IDENTITIES_FIELD = "legacy_extra_identities_field"
_EXPECTED_MATERIAL_USE_INCOMPATIBILITY_REASONS = frozenset(
    {_HANDOFF_NAMES_DIFFERENT_MANIFEST, _LEGACY_EXTRA_IDENTITIES_FIELD}
)


def _classify_material_use_incompatibility(error: ValidationError) -> frozenset[str]:
    classified: set[str] = set()
    for item in error.errors():
        loc = item["loc"]
        if loc == ("handoff",) and item["type"] == "value_error" and "names a different manifest" in item["msg"]:
            classified.add(_HANDOFF_NAMES_DIFFERENT_MANIFEST)
        elif loc == ("identities",) and item["type"] == "extra_forbidden":
            classified.add(_LEGACY_EXTRA_IDENTITIES_FIELD)
        else:
            raise AssertionError(
                f"unrecognized material-use incompatibility reason outside the bounded "
                f"classification: loc={loc!r} type={item['type']!r} msg={item['msg']!r}"
            )
    return frozenset(classified)


def test_material_use_frozen_journey_is_explicitly_incompatible_with_the_current_contract() -> None:
    """Documented, expected history: this frozen bytes predate hardening added after Slice 5.

    The frozen full journey capture does not revalidate against the current, stricter
    ``CodeIntelligenceJourneyV1Alpha1`` cross-contract closure checks. This is recorded as an
    explicit, expected incompatibility -- not a current material-use claim and not a product
    failure of the checked-in evidence or of the current contracts. The exact reasons are
    asserted against a bounded classification (a different manifest named by the frozen
    handoff receipt, and the frozen journey's legacy extra ``identities`` field, now
    forbidden), so an unrelated future validation failure fails this test instead of being
    silently absorbed by a bare ``ValidationError`` catch.
    """

    receipt = _load_json(_EVIDENCE / "code-intelligence-material-use-receipt-v1.json")
    artifact = receipt["durable_replay_artifact"]
    members = _safe_tar_members(_PROJECT_ROOT / artifact["path"])
    frozen_journey_member = next(
        item for item in artifact["members"] if item["path"] == "ace-code-dogfood-v3-current.json"
    )
    frozen_journey = json.loads(members[frozen_journey_member["path"]])

    with pytest.raises(ValidationError) as excinfo:
        CodeIntelligenceJourneyV1Alpha1.model_validate(frozen_journey)
    assert _classify_material_use_incompatibility(excinfo.value) == _EXPECTED_MATERIAL_USE_INCOMPATIBILITY_REASONS

    assert receipt["material_use"]["matched_control_or_benefit_evaluation"] is False
    assert receipt["effect_observation"]["causal_benefit_claimed"] is False
    assert receipt["effect_observation"]["deployed_runtime_effect_observed"] is False


# ---------------------------------------------------------------------------
# 5. Every authority field/nonclaim remains false/calibrated
# ---------------------------------------------------------------------------


def test_single_chain_evidence_authority_fields_are_all_false() -> None:
    evidence = _load_json(_EVIDENCE / "code-intelligence-single-chain-living-run-v1.json")
    assert all(value is False for value in evidence["authority"].values())


def test_external_agent_evidence_authority_and_nonclaim_fields_are_all_false() -> None:
    evidence = _load_json(_EVIDENCE / "code-intelligence-external-agent-round-trip-v1.json")
    assert all(value is False for value in evidence["authority"].values())


def test_material_use_receipt_authority_and_delivery_nonclaims_are_all_false() -> None:
    receipt = _load_json(_EVIDENCE / "code-intelligence-material-use-receipt-v1.json")
    assert all(value is False for value in receipt["authority"].values())
    delivery = receipt["delivery_observation"]
    for field in ("committed", "pushed", "published", "deployed", "external_delivery_observed"):
        assert delivery[field] is False
    effect = receipt["effect_observation"]
    for field in ("deployed_runtime_effect_observed", "user_or_business_outcome_observed", "causal_benefit_claimed"):
        assert effect[field] is False


# ---------------------------------------------------------------------------
# 6. Exact 11 public MCP tools unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_mcp_tool_surface_remains_exactly_eleven() -> None:
    from ace_mcp_client.server import mcp

    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert len(tools) == 11
    assert tool_names == {
        "ace_start",
        "ace_load",
        "ace_capture",
        "ace_task",
        "ace_status",
        "ace_capture_idea",
        "ace_search",
        "ace_briefing",
        "ace_impact",
        "ace_history",
        "ace_related",
    }
