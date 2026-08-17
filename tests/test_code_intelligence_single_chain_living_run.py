"""Adversarial acceptance for the bounded single-chain living run."""

from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from core.engine.code_intelligence.contracts import (
    CodeContextBlockV1Alpha1,
    CodeFileMutationObservationV1Alpha1,
    CodeIntelligenceJourneyV1Alpha1,
    CodeIntelligenceReplayExpectationV1Alpha1,
    CodeIntelligenceSingleChainLivingRunV1Alpha1,
    CodeVerificationObservationV1Alpha1,
    CodingAgentReturnReceiptV1Alpha1,
    raw_digest,
    stable_digest,
)
from core.engine.code_intelligence.living_run import (
    validate_single_chain_living_run,
    validate_single_chain_replay_envelope,
)
from core.engine.code_intelligence.snapshot_store import DurablePhase1IndexSnapshotV1Alpha1
from scripts.verify_code_intelligence_single_chain_living_run import run_acceptance


@pytest.fixture(scope="module")
def accepted_packet(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return run_acceptance(tmp_path_factory.mktemp("single-chain"))


def test_single_chain_joins_handoff_return_verification_update_and_restart(accepted_packet: dict) -> None:
    assert accepted_packet["accepted"] is True
    journey = CodeIntelligenceJourneyV1Alpha1.model_validate(accepted_packet["initial_journey"])
    run = CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(accepted_packet["run"])

    assert validate_single_chain_living_run(journey, run) is run
    assert accepted_packet["run_id"] == run.run_id
    assert run.agent_return.changed_paths == ("pkg/service.py",)
    assert run.return_receipt.changed_paths == run.agent_return.changed_paths
    assert run.verification.changed_paths == run.agent_return.changed_paths
    assert run.living_update.changed_paths == run.agent_return.changed_paths
    assert run.verification.independent_of_coding_agent_claims is True
    assert run.verification.self_authenticates_command_execution is False
    assert run.verification.verifier_replay_required is True
    assert run.verification.status == "passed"
    assert run.verification.mutation.path == "pkg/service.py"
    assert run.verification.mutation.harness_applied_mutation is True
    assert run.verification.mutation.external_delivery_observed is False
    assert run.living_update.mutation_id == run.verification.mutation.mutation_id
    assert run.living_update.before_source_digest == run.verification.mutation.before_digest
    assert run.living_update.after_source_digest == run.verification.mutation.after_digest
    assert run.living_update.patch_digest == run.verification.mutation.patch_digest
    assert run.living_update.updated_generation == 2
    assert run.living_update.parent_snapshot_id == run.initial_snapshot_id
    assert run.living_update.fresh_process_reopen is True
    assert run.living_update.full_rescan_permitted is False
    assert run.living_update.provider_invocation_permitted is False
    assert run.living_update.post_restart_index_id == run.living_update.updated_index_id
    assert run.living_update.post_restart_source_path == "pkg/service.py"
    assert run.living_update.post_restart_source_symbol == "transform"
    assert (
        run.living_update.post_restart_symbol_line_start,
        run.living_update.post_restart_symbol_line_end,
    ) == (4, 6)
    assert run.living_update.old_snapshot_still_readable is True
    assert accepted_packet["immutable_history"] == {
        "snapshot_count": 2,
        "old_snapshot_still_readable": True,
        "old_snapshot_digest_unchanged": True,
    }
    assert accepted_packet["fresh_process_reopen"]["source_symbol"] == "transform"
    assert accepted_packet["fresh_process_reopen"]["full_rescan_permitted"] is False
    assert accepted_packet["fresh_process_reopen"]["incremental_rescan_permitted"] is False
    assert accepted_packet["fresh_process_reopen"]["provider_import_permitted"] is False
    assert accepted_packet["fresh_process_reopen"]["provider_invocation_permitted"] is False
    assert DurablePhase1IndexSnapshotV1Alpha1.model_validate(accepted_packet["initial_snapshot"]).generation == 1
    assert DurablePhase1IndexSnapshotV1Alpha1.model_validate(accepted_packet["updated_snapshot"]).generation == 2
    assert accepted_packet["old_snapshot"] == accepted_packet["initial_snapshot"]
    assert accepted_packet["fresh_process_reopen"]["journey"]["contract"].endswith("/v1alpha1")
    assert all(
        getattr(run, field) is False
        for field in (
            "source_authority",
            "reasoning_authority",
            "change_authority",
            "approval_authority",
            "delivery_authority",
            "execution_authority",
            "effect_authority",
        )
    )


def test_single_chain_rejects_changed_path_and_parent_tampering(accepted_packet: dict) -> None:
    changed_path = copy.deepcopy(accepted_packet["run"])
    changed_path["verification"]["changed_paths"] = ["pkg/consumer.py"]
    with pytest.raises(ValidationError, match="verification changed paths differ"):
        CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(changed_path)

    parent = copy.deepcopy(accepted_packet["run"])
    parent["living_update"]["parent_snapshot_id"] = "code_index_snapshot:" + "f" * 32
    with pytest.raises(ValidationError, match="does not name the initial snapshot"):
        CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(parent)


def test_single_chain_rejects_authority_and_observation_forgery(accepted_packet: dict) -> None:
    authority = copy.deepcopy(accepted_packet["run"])
    authority["effect_authority"] = True
    with pytest.raises(ValidationError):
        CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(authority)

    observation = copy.deepcopy(accepted_packet["run"]["verification"])
    observation["status"] = "passed"
    observation["exit_code"] = 1
    with pytest.raises(ValidationError, match="status differs"):
        CodeVerificationObservationV1Alpha1.model_validate(observation)

    extra = copy.deepcopy(accepted_packet["run"])
    extra["provider_reasoning"] = "trusted"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(extra)

    receipt_time = copy.deepcopy(accepted_packet["run"])
    receipt_time["return_receipt"]["validated_at"] = "2020-01-01T00:00:00Z"
    with pytest.raises(ValidationError, match="different return receipt"):
        CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(receipt_time)


def test_single_chain_verifier_rejects_a_different_initial_journey(accepted_packet: dict) -> None:
    journey_payload = copy.deepcopy(accepted_packet["initial_journey"])
    journey_payload["handoff"]["receipt"]["receiver_ref"] = "coding-agent:different"
    different = CodeIntelligenceJourneyV1Alpha1.model_validate(journey_payload)
    run = CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(accepted_packet["run"])

    with pytest.raises(ValueError, match="receiver differs from initial journey"):
        validate_single_chain_living_run(different, run)


def _render(packet: dict) -> bytes:
    return (json.dumps(packet, indent=2, sort_keys=True) + "\n").encode()


def _expectation(packet: dict, raw: bytes) -> CodeIntelligenceReplayExpectationV1Alpha1:
    run = CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(packet["run"])
    initial = DurablePhase1IndexSnapshotV1Alpha1.model_validate(packet["initial_snapshot"])
    updated = DurablePhase1IndexSnapshotV1Alpha1.model_validate(packet["updated_snapshot"])
    return CodeIntelligenceReplayExpectationV1Alpha1(
        raw_member_digest=raw_digest(raw),
        run_id=run.run_id,
        return_receipt_id=run.return_receipt.receipt_id,
        return_receipt_validated_at=run.return_receipt.validated_at,
        initial_snapshot_id=initial.snapshot_id,
        initial_snapshot_digest=initial.snapshot_digest,
        updated_snapshot_id=updated.snapshot_id,
        updated_snapshot_digest=updated.snapshot_digest,
        post_restart_lens_id=packet["fresh_process_reopen"]["lens_id"],
    )


def test_named_symbol_and_exact_patch_are_derived_from_body_material(accepted_packet: dict) -> None:
    forged_block = copy.deepcopy(accepted_packet["initial_journey"]["handoff"]["blocks"][0])
    forged_block.update(
        {
            "body": "pass",
            "body_digest": stable_digest("pass"),
            "byte_count": 4,
            "line_start": 1,
            "line_end": 1,
            "symbol_line_start": 1,
            "symbol_line_end": 1,
            "symbol_body_digest": stable_digest("pass"),
        }
    )
    with pytest.raises(ValidationError, match="not the sole top-level named Python definition"):
        CodeContextBlockV1Alpha1.model_validate(forged_block)

    def symbol_block(body: str, symbol: str) -> CodeContextBlockV1Alpha1:
        payload = copy.deepcopy(accepted_packet["initial_journey"]["handoff"]["blocks"][0])
        line_count = len(body.splitlines())
        payload.update(
            {
                "body": body,
                "body_digest": stable_digest(body),
                "byte_count": len(body.encode()),
                "line_start": 10,
                "line_end": 9 + line_count,
                "symbol": symbol,
                "symbol_line_start": 10,
                "symbol_line_end": 9 + line_count,
                "symbol_body_digest": stable_digest(body),
            }
        )
        return CodeContextBlockV1Alpha1.model_validate(payload)

    nested = "def wrapper():\n    def transform(value):\n        return value\n    return transform(1)"
    with pytest.raises(ValidationError, match="not the sole top-level named Python definition"):
        symbol_block(nested, "transform")

    multiple = "def transform(value):\n    return value\n\nRESULT = transform(1)"
    with pytest.raises(ValidationError, match="not the sole top-level named Python definition"):
        symbol_block(multiple, "transform")

    valid_bodies = (
        ("def transform(value):\n    return value", "transform"),
        ("async def transform(value):\n    return value", "transform"),
        ("    @staticmethod\n    def transform(value):\n        return value", "Service.transform"),
        ("class Transform:\n    pass", "Transform"),
    )
    for body, symbol in valid_bodies:
        assert symbol_block(body, symbol).symbol == symbol

    forged_patch = copy.deepcopy(accepted_packet["run"]["verification"]["mutation"])
    forged_patch["patch"] = ""
    forged_patch["patch_byte_count"] = 0
    forged_patch["patch_digest"] = raw_digest("")
    with pytest.raises(ValidationError, match="differs from deterministic"):
        CodeFileMutationObservationV1Alpha1.model_validate(forged_patch)


def test_paired_envelope_rejects_coherent_receipt_time_forgery(accepted_packet: dict) -> None:
    original_raw = _render(accepted_packet)
    original_expected = _expectation(accepted_packet, original_raw)
    forged = copy.deepcopy(accepted_packet)
    forged["run"]["return_receipt"]["validated_at"] = "2020-01-01T00:00:00Z"
    receipt = CodingAgentReturnReceiptV1Alpha1.model_validate(forged["run"]["return_receipt"])
    forged["run"]["living_update"]["return_receipt_id"] = receipt.receipt_id
    forged_run = CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(forged["run"])
    forged["run_id"] = forged_run.run_id
    forged["identities"]["return_receipt_id"] = receipt.receipt_id
    forged["identities"]["living_update_id"] = forged_run.living_update.update_id
    forged_raw = _render(forged)
    paired = original_expected.model_copy(
        update={"raw_member_digest": raw_digest(forged_raw), "run_id": forged_run.run_id}
    )

    with pytest.raises(ValueError, match="return receipt differs from externally expected"):
        validate_single_chain_replay_envelope(forged_raw, paired)


def test_paired_envelope_rejects_coherent_snapshot_forgery(accepted_packet: dict) -> None:
    original_raw = _render(accepted_packet)
    original_expected = _expectation(accepted_packet, original_raw)
    forged = copy.deepcopy(accepted_packet)
    forged["updated_snapshot"]["created_at"] = "2020-01-01T00:00:00Z"
    forged_snapshot = DurablePhase1IndexSnapshotV1Alpha1.model_validate(forged["updated_snapshot"])
    forged["run"]["living_update"]["updated_snapshot_id"] = forged_snapshot.snapshot_id
    forged["run"]["living_update"]["updated_snapshot_digest"] = forged_snapshot.snapshot_digest
    forged["fresh_process_reopen"]["snapshot_id"] = forged_snapshot.snapshot_id
    forged["fresh_process_reopen"]["snapshot_digest"] = forged_snapshot.snapshot_digest
    forged_run = CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(forged["run"])
    forged["run_id"] = forged_run.run_id
    forged["identities"]["living_update_id"] = forged_run.living_update.update_id
    forged_raw = _render(forged)
    paired = original_expected.model_copy(
        update={"raw_member_digest": raw_digest(forged_raw), "run_id": forged_run.run_id}
    )

    with pytest.raises(ValueError, match="updated snapshot differs from externally expected"):
        validate_single_chain_replay_envelope(forged_raw, paired)


def test_paired_envelope_rejects_relabeled_initial_scanner_stat_count(accepted_packet: dict) -> None:
    """A coherent-looking count (999) that just does not match the full snapshot must fail."""
    original_raw = _render(accepted_packet)
    original_expected = _expectation(accepted_packet, original_raw)
    forged = copy.deepcopy(accepted_packet)
    forged["initial_journey"]["scanner_stats"]["functions"] = 999
    forged_raw = _render(forged)
    paired = original_expected.model_copy(update={"raw_member_digest": raw_digest(forged_raw)})

    with pytest.raises(ValueError, match="initial journey scanner_stats differs"):
        validate_single_chain_replay_envelope(forged_raw, paired)


def test_paired_envelope_rejects_relabeled_post_restart_scanner_stat_count(accepted_packet: dict) -> None:
    original_raw = _render(accepted_packet)
    original_expected = _expectation(accepted_packet, original_raw)
    forged = copy.deepcopy(accepted_packet)
    forged["fresh_process_reopen"]["journey"]["scanner_stats"]["classes"] = 999
    forged_raw = _render(forged)
    paired = original_expected.model_copy(update={"raw_member_digest": raw_digest(forged_raw)})

    with pytest.raises(ValueError, match="post-restart journey scanner_stats differs"):
        validate_single_chain_replay_envelope(forged_raw, paired)


def test_paired_envelope_rejects_negative_scanner_stat(accepted_packet: dict) -> None:
    original_raw = _render(accepted_packet)
    original_expected = _expectation(accepted_packet, original_raw)
    forged = copy.deepcopy(accepted_packet)
    forged["initial_journey"]["scanner_stats"]["files"] = -1
    forged_raw = _render(forged)
    paired = original_expected.model_copy(update={"raw_member_digest": raw_digest(forged_raw)})

    with pytest.raises(ValueError, match="nonnegative int"):
        validate_single_chain_replay_envelope(forged_raw, paired)


def test_paired_envelope_rejects_extra_scanner_stat_key(accepted_packet: dict) -> None:
    original_raw = _render(accepted_packet)
    original_expected = _expectation(accepted_packet, original_raw)
    forged = copy.deepcopy(accepted_packet)
    forged["initial_journey"]["scanner_stats"]["symbols"] = 1
    forged_raw = _render(forged)
    paired = original_expected.model_copy(update={"raw_member_digest": raw_digest(forged_raw)})

    with pytest.raises(ValueError, match="exactly the keys"):
        validate_single_chain_replay_envelope(forged_raw, paired)
