"""Validation for one bounded Code Intelligence living-update chain."""

from __future__ import annotations

import json
from typing import Any

from core.engine.code_intelligence.contracts import (
    BoundedCodeHandoffV1Alpha1,
    CodeContextBlockV1Alpha1,
    CodeIntelligenceJourneyV1Alpha1,
    CodeIntelligenceReplayExpectationV1Alpha1,
    CodeIntelligenceSingleChainLivingRunV1Alpha1,
    raw_digest,
)
from core.engine.code_intelligence.handoff import validate_coding_agent_return
from core.engine.code_intelligence.snapshot_store import DurablePhase1IndexSnapshotV1Alpha1


def validate_single_chain_living_run(
    initial_journey: CodeIntelligenceJourneyV1Alpha1,
    run: CodeIntelligenceSingleChainLivingRunV1Alpha1,
) -> CodeIntelligenceSingleChainLivingRunV1Alpha1:
    """Fail closed unless ``run`` closes the exact initial journey and return.

    The independently observed verification and durable update are already
    cross-checked by the frozen run contract. This verifier additionally binds
    that chain to the full initial handoff, including its bounded block set.
    """

    expected = initial_journey.handoff.receipt
    coordinates = (
        ("receiver", run.receiver_ref, expected.receiver_ref),
        ("index", run.initial_index_id, initial_journey.lens.index.index_id),
        ("lens", run.initial_lens_id, initial_journey.lens.lens_id),
        ("manifest", run.initial_manifest_id, initial_journey.handoff.manifest.manifest_id),
        ("handoff", run.initial_handoff_id, expected.handoff_id),
    )
    for label, actual, wanted in coordinates:
        if actual != wanted:
            raise ValueError(f"single-chain living run {label} differs from initial journey")

    expected_receipt = validate_coding_agent_return(initial_journey.handoff, run.agent_return)
    actual_receipt = run.return_receipt
    # ``validated_at`` is deliberately excluded from semantic reconstruction:
    # verifier replay is a new observation. Paired archive validation separately
    # requires the externally recorded original receipt ID *and* validated_at.
    comparable_fields = (
        "return_id",
        "receiver_ref",
        "handoff_id",
        "index_id",
        "lens_id",
        "manifest_id",
        "disposition",
        "consumed_block_ids",
        "changed_paths",
        "verification_refs",
        "warnings",
        "chain_validated",
        "source_authority",
        "reasoning_authority",
        "delivery_authority",
        "effect_authority",
        "execution_authority_revalidation_required",
    )
    for field in comparable_fields:
        if getattr(actual_receipt, field) != getattr(expected_receipt, field):
            raise ValueError(f"single-chain living run return receipt differs at {field}")
    return run


def _named_source_block(handoff: BoundedCodeHandoffV1Alpha1, block_id: str) -> CodeContextBlockV1Alpha1:
    matches = [item for item in handoff.blocks if item.block_id == block_id and item.symbol is not None]
    if len(matches) != 1:
        raise ValueError("single-chain envelope does not contain the exact named source block")
    return matches[0]


def _source_excerpt(body: str, block: CodeContextBlockV1Alpha1) -> str:
    lines = body.splitlines()
    if block.line_end > len(lines):
        raise ValueError("single-chain source block extends beyond exact file material")
    return "\n".join(lines[block.line_start - 1 : block.line_end])


def _validate_source_anchor(journey: CodeIntelligenceJourneyV1Alpha1, block: CodeContextBlockV1Alpha1) -> None:
    anchors = [item for item in journey.lens.evidence if item.anchor_id == block.evidence_ref]
    if len(anchors) != 1:
        raise ValueError("single-chain named source block lacks its exact journey anchor")
    anchor = anchors[0]
    if (
        anchor.path != block.path
        or anchor.line_start != block.symbol_line_start
        or anchor.line_end != block.symbol_line_end
        or anchor.content_digest != block.symbol_body_digest
    ):
        raise ValueError("single-chain named source block differs from its exact journey anchor")


def _validate_snapshot_symbol(
    snapshot: DurablePhase1IndexSnapshotV1Alpha1,
    block: CodeContextBlockV1Alpha1,
) -> None:
    if not any(
        item.get("file") == block.path
        and item.get("name") == block.symbol
        and int(item.get("line_start", 0)) == block.symbol_line_start
        and int(item.get("line_end", 0)) == block.symbol_line_end
        for item in snapshot.phase1_state.symbols
    ):
        raise ValueError("single-chain snapshot does not contain the exact named source symbol")


def _snapshot_scanner_stats(snapshot: DurablePhase1IndexSnapshotV1Alpha1) -> dict[str, int]:
    """Recompute the exact files/functions/classes/imports counts from one full snapshot.

    Functions and classes are derived by symbol kind, matching the same
    derivation a reopened ``GraphBuilder`` uses; files and imports are exact
    record counts. This is the sole trusted source for the counts a journey's
    ``scanner_stats`` must equal after any snapshot capture or reopen.
    """
    symbols = snapshot.phase1_state.symbols
    return {
        "files": len(snapshot.phase1_state.files),
        "functions": sum(item.get("kind") != "class" for item in symbols),
        "classes": sum(item.get("kind") == "class" for item in symbols),
        "imports": len(snapshot.phase1_state.imports),
    }


def validate_single_chain_replay_envelope(
    raw_payload: bytes,
    expected: CodeIntelligenceReplayExpectationV1Alpha1,
) -> CodeIntelligenceSingleChainLivingRunV1Alpha1:
    """Validate the archived packet against separately recorded exact coordinates.

    This paired validator closes the full snapshot/journey/source envelope. It
    does not claim that stored verification output digests authenticate command
    execution; the observation contract continues to require verifier replay.
    """

    if raw_digest(raw_payload) != expected.raw_member_digest:
        raise ValueError("single-chain replay member differs from externally expected bytes")
    try:
        packet: dict[str, Any] = json.loads(raw_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("single-chain replay member is not valid JSON") from exc
    required_sections = {
        "evidence_contract",
        "accepted",
        "run_id",
        "identities",
        "initial_journey",
        "initial_snapshot",
        "updated_snapshot",
        "old_snapshot",
        "initial_capture",
        "run",
        "incremental_update",
        "fresh_process_reopen",
        "immutable_history",
    }
    if set(packet) != required_sections:
        raise ValueError("single-chain replay envelope has an unexpected section inventory")
    if packet["evidence_contract"] != "ace.code-intelligence.single-chain-living-run-evidence/v1alpha1":
        raise ValueError("single-chain replay envelope contract differs")
    if packet["accepted"] is not True:
        raise ValueError("single-chain replay envelope is not accepted")

    journey = CodeIntelligenceJourneyV1Alpha1.model_validate(packet["initial_journey"])
    run = CodeIntelligenceSingleChainLivingRunV1Alpha1.model_validate(packet["run"])
    initial = DurablePhase1IndexSnapshotV1Alpha1.model_validate(packet["initial_snapshot"])
    updated = DurablePhase1IndexSnapshotV1Alpha1.model_validate(packet["updated_snapshot"])
    old = DurablePhase1IndexSnapshotV1Alpha1.model_validate(packet["old_snapshot"])
    reopened_payload = packet["fresh_process_reopen"]
    post_journey = CodeIntelligenceJourneyV1Alpha1.model_validate(reopened_payload["journey"])

    validate_single_chain_living_run(journey, run)
    identities = packet.get("identities", {})
    expected_identities = {
        "return_id": run.agent_return.return_id,
        "return_receipt_id": run.return_receipt.receipt_id,
        "verification_id": run.verification.verification_id,
        "living_update_id": run.living_update.update_id,
        "mutation_id": run.verification.mutation.mutation_id,
    }
    if identities != expected_identities:
        raise ValueError("single-chain replay identity inventory differs from exact run contracts")
    if packet.get("run_id") != run.run_id or run.run_id != expected.run_id:
        raise ValueError("single-chain replay run differs from externally expected identity")
    if (
        run.return_receipt.receipt_id != expected.return_receipt_id
        or run.return_receipt.validated_at != expected.return_receipt_validated_at
    ):
        raise ValueError("single-chain replay return receipt differs from externally expected identity or time")

    update = run.living_update
    if (
        initial.snapshot_id != expected.initial_snapshot_id
        or initial.snapshot_digest != expected.initial_snapshot_digest
    ):
        raise ValueError("single-chain initial snapshot differs from externally expected coordinates")
    if (
        updated.snapshot_id != expected.updated_snapshot_id
        or updated.snapshot_digest != expected.updated_snapshot_digest
    ):
        raise ValueError("single-chain updated snapshot differs from externally expected coordinates")
    if post_journey.lens.lens_id != expected.post_restart_lens_id:
        raise ValueError("single-chain post-restart lens differs from externally expected coordinate")

    if initial.index != journey.lens.index or initial.snapshot_id != run.initial_snapshot_id:
        raise ValueError("single-chain initial snapshot differs from initial journey/run")
    if updated.index != post_journey.lens.index or updated.index_id != update.updated_index_id:
        raise ValueError("single-chain updated snapshot differs from post-restart journey/update")
    if (
        updated.generation != 2
        or updated.parent_snapshot_id != initial.snapshot_id
        or updated.parent_snapshot_digest != initial.snapshot_digest
    ):
        raise ValueError("single-chain updated snapshot has invalid generation-one parent linkage")
    if old != initial or old.snapshot_id != update.old_snapshot_id or old.snapshot_digest != update.old_snapshot_digest:
        raise ValueError("single-chain archived old snapshot differs from immutable generation one")

    initial_capture = packet["initial_capture"]
    initial_scan = _snapshot_scanner_stats(initial)
    updated_scan = _snapshot_scanner_stats(updated)
    initial_coordinates = {
        "snapshot_id": initial.snapshot_id,
        "snapshot_digest": initial.snapshot_digest,
        "generation": initial.generation,
        "phase1_state_digest": initial.phase1_state_digest,
        "scan_stats": initial_scan,
    }
    if any(initial_capture.get(field) != value for field, value in initial_coordinates.items()):
        raise ValueError("single-chain initial-capture summary differs from full snapshot")
    if journey.scanner_stats != initial_scan:
        raise ValueError("single-chain initial journey scanner_stats differs from full initial snapshot counts")
    if post_journey.scanner_stats != updated_scan:
        raise ValueError("single-chain post-restart journey scanner_stats differs from full updated snapshot counts")
    if packet["incremental_update"]["changed_paths"] != list(run.agent_return.changed_paths):
        raise ValueError("single-chain incremental summary differs from exact return paths")
    if packet["incremental_update"]["stats"].get("updated") != len(run.agent_return.changed_paths):
        raise ValueError("single-chain incremental summary differs from exact updated-path count")
    if packet["immutable_history"] != {
        "snapshot_count": 2,
        "old_snapshot_still_readable": True,
        "old_snapshot_digest_unchanged": True,
    }:
        raise ValueError("single-chain immutable-history summary differs from full snapshot envelope")

    initial_block = _named_source_block(journey.handoff, packet["initial_capture"]["source_block_id"])
    post_block = _named_source_block(post_journey.handoff, update.post_restart_source_block_id)
    _validate_source_anchor(journey, initial_block)
    _validate_source_anchor(post_journey, post_block)
    _validate_snapshot_symbol(initial, initial_block)
    _validate_snapshot_symbol(updated, post_block)
    initial_source_coordinates = {
        "source_block_id": initial_block.block_id,
        "source_body_digest": initial_block.body_digest,
        "source_symbol": initial_block.symbol,
        "context_span": [initial_block.line_start, initial_block.line_end],
        "symbol_span": [initial_block.symbol_line_start, initial_block.symbol_line_end],
    }
    if any(initial_capture.get(field) != value for field, value in initial_source_coordinates.items()):
        raise ValueError("single-chain initial-capture source summary differs from exact source block")

    mutation = run.verification.mutation
    if initial_block.path != mutation.path or post_block.path != mutation.path:
        raise ValueError("single-chain source blocks differ from exact mutation path")
    if _source_excerpt(mutation.before_body, initial_block) != initial_block.body:
        raise ValueError("single-chain initial block differs from exact before-source bytes")
    if _source_excerpt(mutation.after_body, post_block) != post_block.body:
        raise ValueError("single-chain post-restart block differs from exact after-source bytes")
    if reopened_payload["source_file_digest"] != mutation.after_digest:
        raise ValueError("single-chain fresh-process source digest differs from exact after-source bytes")
    if (
        update.post_restart_source_block_id != post_block.block_id
        or update.post_restart_source_body_digest != post_block.body_digest
        or update.post_restart_source_path != post_block.path
        or update.post_restart_source_symbol != post_block.symbol
        or update.post_restart_symbol_line_start != post_block.symbol_line_start
        or update.post_restart_symbol_line_end != post_block.symbol_line_end
    ):
        raise ValueError("single-chain living update differs from exact post-restart source block")
    forbidden_flags = (
        "full_rescan_permitted",
        "incremental_rescan_permitted",
        "provider_environment_present",
        "provider_import_permitted",
        "provider_invocation_permitted",
    )
    if reopened_payload.get("fresh_python_process") is not True or any(
        reopened_payload.get(field) is not False for field in forbidden_flags
    ):
        raise ValueError("single-chain fresh-process provider/rescan boundary differs")

    reopened_coordinates = (
        ("snapshot_id", updated.snapshot_id),
        ("snapshot_digest", updated.snapshot_digest),
        ("index_id", updated.index_id),
        ("lens_id", post_journey.lens.lens_id),
        ("manifest_id", post_journey.handoff.manifest.manifest_id),
        ("handoff_id", post_journey.handoff.receipt.handoff_id),
        ("source_block_id", post_block.block_id),
        ("source_body_digest", post_block.body_digest),
    )
    for field, wanted in reopened_coordinates:
        if reopened_payload.get(field) != wanted:
            raise ValueError(f"single-chain fresh-process {field} differs from full archived journey/snapshot")
    return run
