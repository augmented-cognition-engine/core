"""Adversarial acceptance for the genuine external-agent wrapper."""

from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from core.engine.code_intelligence.contracts import BoundedCodeHandoffV1Alpha1, CodeIntelligenceJourneyV1Alpha1
from core.engine.code_intelligence.external_agent import (
    _ALLOWED_COMMANDS,
    CodeChangeSetReceiptV1Alpha1,
    ExternalAgentReplayExpectationV1Alpha1,
    ExternalCodingAgentAcceptanceRunV1Alpha1,
    ExternalCodingAgentDeliveryReceiptV1Alpha1,
    derive_external_agent_transcript,
    validate_external_coding_agent_acceptance,
)
from core.engine.code_intelligence.snapshot_store import DurablePhase1IndexSnapshotV1Alpha1
from scripts.verify_code_intelligence_external_agent_round_trip import (
    AgentProcessObservation,
    AgentRunRequest,
    _deterministic_archive,
    _sha256,
    replay_external_agent_archive,
    run_acceptance,
    run_codex_exec,
    verify_deterministic_archive,
)

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_code_intelligence_external_agent_round_trip.py"


def _lifecycle_events(target_resolved: str, message_text: str) -> list[dict]:
    check_command, date_command = _ALLOWED_COMMANDS
    return [
        {"type": "thread.started", "thread_id": "fixture-thread"},
        {"type": "turn.started"},
        {
            "type": "item.started",
            "item": {
                "id": "item_0",
                "type": "file_change",
                "changes": [{"path": target_resolved, "kind": "update"}],
                "status": "in_progress",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_0",
                "type": "file_change",
                "changes": [{"path": target_resolved, "kind": "update"}],
                "status": "completed",
            },
        },
        {
            "type": "item.started",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": check_command,
                "aggregated_output": "",
                "exit_code": None,
                "status": "in_progress",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": check_command,
                "aggregated_output": "",
                "exit_code": 0,
                "status": "completed",
            },
        },
        {
            "type": "item.started",
            "item": {
                "id": "item_2",
                "type": "command_execution",
                "command": date_command,
                "aggregated_output": "",
                "exit_code": None,
                "status": "in_progress",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "type": "command_execution",
                "command": date_command,
                "aggregated_output": "2026-08-15T05:08:46Z\n",
                "exit_code": 0,
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {"id": "item_3", "type": "agent_message", "text": message_text},
        },
        {"type": "turn.completed"},
    ]


def _render_transcript(events: list[dict]) -> bytes:
    return b"\n".join(json.dumps(event, sort_keys=True).encode() for event in events) + b"\n"


def _handoff_from_prompt(prompt: bytes) -> dict:
    text = prompt.decode()
    body = text.split("BEGIN_EXACT_ACE_HANDOFF_JSON\n", 1)[1].split("\nEND_EXACT_ACE_HANDOFF_JSON", 1)[0]
    return json.loads(body)


def _fake_external_agent(request: AgentRunRequest) -> AgentProcessObservation:
    handoff = _handoff_from_prompt(request.prompt)
    receipt = handoff["receipt"]
    block_ids = [item["block_id"] for item in handoff["manifest"]["blocks"]]
    target = request.repository / "pkg/service.py"
    target.write_text(target.read_text().replace("return adjusted + 1", "return adjusted + 2"))
    returned = {
        "contract": "ace.code-intelligence.coding-agent-return/v1alpha1",
        "receiver_ref": receipt["receiver_ref"],
        "handoff_id": f"coding_agent_handoff:{_handoff_id(handoff)}",
        "index_id": receipt["index_id"],
        "lens_id": receipt["lens_id"],
        "manifest_id": receipt["manifest_id"],
        "disposition": "change_proposed",
        "summary": "Changed the bounded transform implementation and ran the requested check.",
        "consumed_block_ids": block_ids,
        "changed_paths": ["pkg/service.py"],
        "verification_refs": ["fixture-agent-claim:transform(1)==3"],
        "uncertainties": ["The fixture proves only its bounded assertion."],
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "claims_source_authority": False,
        "claims_reasoning_authority": False,
        "claims_delivery_authority": False,
        "claims_effect_authority": False,
    }
    message_text = json.dumps(returned, sort_keys=True)
    output = message_text.encode()
    request.output_path.write_bytes(output)
    target_resolved = str(target.resolve())
    check_command, date_command = _ALLOWED_COMMANDS
    events = _lifecycle_events(target_resolved, message_text)
    transcript = _render_transcript(events)
    argv = (
        request.executable,
        "exec",
        "--ephemeral",
        "--sandbox",
        "workspace-write",
        "--ignore-user-config",
        "--ignore-rules",
        "--model",
        request.model,
        "--json",
        "--output-schema",
        str(request.schema_path),
        "--output-last-message",
        str(request.output_path),
        "-C",
        str(request.repository),
        "-",
    )
    started = datetime.now(timezone.utc)
    return AgentProcessObservation(
        executable=request.executable,
        cli_version="codex-cli 0.147.0-alpha.6.5",
        model=request.model,
        argv=argv,
        session_id="fixture-thread",
        first_event_type="thread.started",
        event_count=len(events),
        transcript=transcript,
        stderr=b"",
        output=output,
        started_at=started,
        acknowledged_at=started + timedelta(microseconds=1),
        completed_at=started + timedelta(microseconds=2),
        exit_code=0,
        bounded_access_observed=True,
        audited_commands=_ALLOWED_COMMANDS,
        audited_write_paths=(target_resolved,),
        audited_write_kinds=("update",),
    )


def _handoff_id(handoff: dict) -> str:
    return BoundedCodeHandoffV1Alpha1.model_validate(handoff).receipt.handoff_id.split(":", 1)[1]


@pytest.fixture(scope="module")
def accepted_packet(tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("external-agent")
    return run_acceptance(root, agent_runner=_fake_external_agent, archive_path=root / "acceptance.tar.gz")


def _models(packet: dict) -> tuple[CodeIntelligenceJourneyV1Alpha1, ExternalCodingAgentAcceptanceRunV1Alpha1]:
    journey = CodeIntelligenceJourneyV1Alpha1.model_validate(packet["initial_journey"])
    accepted = ExternalCodingAgentAcceptanceRunV1Alpha1.model_validate(packet["acceptance_run"])
    return journey, accepted


def _archive_members(path: Path) -> dict[str, bytes]:
    with tarfile.open(path, "r:gz") as archive:
        return {item.name: archive.extractfile(item).read() for item in archive.getmembers()}


def _render(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def test_external_chain_is_not_the_local_harness_contract(accepted_packet: dict) -> None:
    _, accepted = _models(accepted_packet)
    encoded = json.dumps(accepted.model_dump(mode="json"), sort_keys=True)
    assert accepted.status == "candidate_external_observed"
    assert accepted.delivery.external_delivery_observed is True
    assert accepted.change_set.external_agent_interval_observed is True
    assert accepted.change_set.harness_applied_mutation is False
    assert accepted.change_set.actor_causation_cryptographically_proven is False
    assert '"harness_applied_mutation": true' not in encoded
    assert "single-chain-living-run" not in encoded


def test_external_chain_closes_exact_bytes_verification_and_restart(accepted_packet: dict) -> None:
    _, accepted = _models(accepted_packet)
    assert accepted.delivery.return_id == accepted.agent_return.return_id
    assert accepted.change_set.after_digest == accepted.living_update.post_restart_source_file_digest
    assert accepted.change_set.receipt_id == accepted.verification.change_set_id
    assert accepted.change_set.receipt_id == accepted.living_update.mutation_id
    assert accepted.verification.status == "passed"
    assert accepted.living_update.updated_generation == 2
    assert accepted.living_update.old_snapshot_still_readable is True
    archive_path = Path(accepted_packet["durable_archive"]["path"])
    unauthenticated = replay_external_agent_archive(archive_path)
    assert unauthenticated["accepted"] is False
    assert unauthenticated["trust_root_authenticated"] is False
    receipt = accepted_packet["durable_archive"]
    expectation = ExternalAgentReplayExpectationV1Alpha1.model_validate_json(
        _archive_members(archive_path)["external-agent-replay-expectation.json"]
    )
    replayed = replay_external_agent_archive(
        archive_path,
        expected_archive_sha256=receipt["sha256"],
        expected_archive_byte_count=receipt["byte_count"],
        expected_replay_expectation=expectation,
    )
    assert replayed["accepted"] is True
    assert replayed["acceptance_run_id"] == accepted.run_id


def test_change_set_rejects_harness_or_byte_tampering(accepted_packet: dict) -> None:
    _, accepted = _models(accepted_packet)
    body = accepted.change_set.model_dump(mode="json")
    body["harness_applied_mutation"] = True
    with pytest.raises(ValidationError):
        CodeChangeSetReceiptV1Alpha1.model_validate(body)
    body = accepted.change_set.model_dump(mode="json")
    body["after_body"] += "# crossed\n"
    with pytest.raises(ValidationError, match="after bytes"):
        CodeChangeSetReceiptV1Alpha1.model_validate(body)


def test_outer_chain_rejects_crossed_return_and_authority(accepted_packet: dict) -> None:
    _, accepted = _models(accepted_packet)
    body = accepted.model_dump(mode="json")
    body["delivery"]["return_id"] = "coding_agent_return:crossed"
    with pytest.raises(ValidationError, match="identity chain"):
        ExternalCodingAgentAcceptanceRunV1Alpha1.model_validate(body)
    delivery = accepted.delivery.model_dump(mode="json")
    delivery["delivery_authority"] = True
    with pytest.raises(ValidationError):
        ExternalCodingAgentDeliveryReceiptV1Alpha1.model_validate(delivery)


def test_raw_transcript_and_normalized_return_are_revalidated(accepted_packet: dict) -> None:
    journey, accepted = _models(accepted_packet)
    with pytest.raises(ValueError, match="digest|transcript|invocation"):
        validate_external_coding_agent_acceptance(
            journey,
            accepted,
            transcript=b'{"type":"thread.started","thread_id":"crossed"}\n',
            invocation=b"crossed",
            prompt=b"crossed",
            schema=b"crossed",
            output=b"crossed",
            normalized_return=b"crossed",
            repository_diff=b"crossed",
            repository_root=Path("/tmp/repository"),
        )


def test_archive_writer_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    members = {"b.txt": b"two", "a.txt": b"one"}
    _deterministic_archive(first, members)
    _deterministic_archive(second, members)
    assert first.read_bytes() == second.read_bytes()
    assert verify_deterministic_archive(first)["deterministic_replay"] is True


def _valid_coding_agent_return_text(changed_path: str) -> str:
    returned = {
        "contract": "ace.code-intelligence.coding-agent-return/v1alpha1",
        "receiver_ref": "fixture-receiver",
        "handoff_id": "coding_agent_handoff:fixture",
        "index_id": "fixture-index",
        "lens_id": "fixture-lens",
        "manifest_id": "fixture-manifest",
        "disposition": "change_proposed",
        "summary": "Fixture return for exact transcript-shape tests.",
        "consumed_block_ids": ["block_0"],
        "changed_paths": [changed_path],
        "verification_refs": ["fixture-verification"],
        "uncertainties": [],
        "submitted_at": "2026-08-15T00:00:00Z",
        "claims_source_authority": False,
        "claims_reasoning_authority": False,
        "claims_delivery_authority": False,
        "claims_effect_authority": False,
    }
    return json.dumps(returned, sort_keys=True)


def _valid_transcript_events(tmp_path: Path) -> tuple[list[dict], Path, str]:
    repository = tmp_path / "repository"
    (repository / "pkg").mkdir(parents=True)
    target_resolved = str((repository / "pkg/service.py").resolve())
    message_text = _valid_coding_agent_return_text("pkg/service.py")
    events = _lifecycle_events(target_resolved, message_text)
    return events, repository, message_text


def test_transcript_rejects_wrong_event_type_at_a_fixed_position(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[1] = {"type": "note.created"}
    with pytest.raises(ValueError, match="exact turn.started"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_derive_external_agent_transcript_accepts_the_exact_valid_baseline(tmp_path: Path) -> None:
    events, repository, message_text = _valid_transcript_events(tmp_path)
    result = derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")
    session_id, first_event_type, event_count, commands, write_paths, write_kinds, returned_message = result
    assert session_id == "fixture-thread"
    assert first_event_type == "thread.started"
    assert event_count == 10
    assert commands == _ALLOWED_COMMANDS
    assert write_paths == (str((repository / "pkg/service.py").resolve()),)
    assert write_kinds == ("update",)
    assert returned_message == message_text


def test_transcript_rejects_hidden_command_and_cmd_keys_inserted_into_turn_started(tmp_path: Path) -> None:
    # Regression: the frozen lifecycle's only legitimate "command" positions are the
    # two known command_execution items -- a "cmd" or "command" key hidden anywhere
    # else, including a wholly unrelated event like turn.started, must be rejected
    # for that reason specifically, not because of some unrelated broken field.
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[1] = {
        "type": "turn.started",
        "note": {"cmd": "git commit -am pwned", "command": "cat /etc/passwd"},
    }
    with pytest.raises(ValueError, match="outside the exact command_execution.command positions"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_browser_tool_marker_hidden_in_turn_started(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[1] = {"type": "turn.started", "note": {"tool": "browser"}}
    with pytest.raises(ValueError, match="forbidden browser/MCP/network tool"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_an_mcp_tool_name_marker_hidden_in_turn_started(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[1] = {"type": "turn.started", "note": {"tool_name": "mcp"}}
    with pytest.raises(ValueError, match="forbidden browser/MCP/network tool"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_web_search_name_marker_hidden_in_turn_started(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[1] = {"type": "turn.started", "note": {"name": "web_search"}}
    with pytest.raises(ValueError, match="forbidden browser/MCP/network tool"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_capitalized_browser_tool_marker_hidden_in_turn_started(tmp_path: Path) -> None:
    # Regression: case must not be a bypass for the forbidden-tool marker check.
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[1] = {"type": "turn.started", "note": {"tool": "Browser"}}
    with pytest.raises(ValueError, match="forbidden browser/MCP/network tool"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_qualified_mcp_tool_name_marker_hidden_in_turn_started(tmp_path: Path) -> None:
    # Regression: a qualified MCP tool name (server::tool style suffix) must not
    # bypass the forbidden-tool marker check just because it isn't an exact match.
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[1] = {"type": "turn.started", "note": {"tool_name": "mcp__filesystem"}}
    with pytest.raises(ValueError, match="forbidden browser/MCP/network tool"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_suffixed_web_search_name_marker_hidden_in_turn_started(tmp_path: Path) -> None:
    # Regression: a suffixed web_search variant must not bypass the forbidden-tool
    # marker check just because it isn't an exact match.
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[1] = {"type": "turn.started", "note": {"name": "web_search_query"}}
    with pytest.raises(ValueError, match="forbidden browser/MCP/network tool"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_command_key_hidden_inside_a_legitimate_command_execution_item(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    check_command, _ = _ALLOWED_COMMANDS
    events[4]["item"]["note"] = {"command": check_command}
    with pytest.raises(ValueError, match="outside the exact command_execution.command positions"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_cmd_key_anywhere_even_in_file_change_items(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[2]["item"]["changes"][0]["cmd"] = "cat /etc/passwd"
    with pytest.raises(ValueError, match="outside the exact command_execution.command positions"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_missing_completion(tmp_path: Path) -> None:
    events, repository, message_text = _valid_transcript_events(tmp_path)
    target_resolved = str((repository / "pkg/service.py").resolve())
    del events[3]
    events.append({"type": "item.completed", "item": {"id": "item_3", "type": "agent_message", "text": message_text}})
    with pytest.raises(ValueError, match="does not end with an exact turn.completed"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_crossed_item_id(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[3]["item"] = {**events[3]["item"], "id": "item_1"}
    with pytest.raises(ValueError, match="item id or type is crossed"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_second_thread_started_event(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events.insert(5, {"type": "thread.started", "thread_id": "second-thread"})
    with pytest.raises(ValueError, match="exactly one thread.started session event"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_started_only_write(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[3] = {"type": "item.started", "item": events[4]["item"]}
    with pytest.raises(ValueError, match="exact item.completed event for file_change item_0"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_nonzero_command_exit_code(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[5]["item"] = {**events[5]["item"], "exit_code": 1}
    with pytest.raises(ValueError, match="exit code zero"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_non_completed_command_status(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[7]["item"] = {**events[7]["item"], "status": "in_progress"}
    with pytest.raises(ValueError, match="exit code zero"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_an_outside_repository_read_command(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    for index in (4, 5):
        events[index]["item"] = {**events[index]["item"], "command": "cat /etc/passwd"}
    with pytest.raises(ValueError, match="exact known allowed command"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_an_extra_event(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events.append({"type": "turn.started"})
    with pytest.raises(ValueError, match="exact ten-event lifecycle"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_a_date_command_output_outside_the_observed_safe_shape(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[7]["item"] = {**events[7]["item"], "aggregated_output": "not-a-date"}
    with pytest.raises(ValueError, match="observed safe shape"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_transcript_rejects_an_agent_message_that_is_not_an_exact_coding_agent_return(tmp_path: Path) -> None:
    events, repository, _ = _valid_transcript_events(tmp_path)
    events[8]["item"] = {**events[8]["item"], "text": "not json"}
    with pytest.raises(ValueError, match="exact coding-agent return"):
        derive_external_agent_transcript(_render_transcript(events), repository, "pkg/service.py")


def test_acceptance_rejects_an_agent_message_that_differs_from_the_output_file_beyond_a_trailing_newline(
    accepted_packet: dict,
) -> None:
    journey, accepted = _models(accepted_packet)
    archive_path = Path(accepted_packet["durable_archive"]["path"])
    members = _archive_members(archive_path)
    events = json.loads(b"[" + b",".join(members["logs/codex-events.jsonl"].splitlines()) + b"]")
    events[8]["item"] = {**events[8]["item"], "text": events[8]["item"]["text"] + " "}
    tampered_transcript = _render_transcript(events)
    retagged_delivery = accepted.delivery.model_copy(
        update={
            "transcript_digest": _sha256(tampered_transcript),
            "transcript_byte_count": len(tampered_transcript),
        }
    )
    accepted = accepted.model_copy(update={"delivery": retagged_delivery})
    with pytest.raises(ValueError, match="agent_message"):
        validate_external_coding_agent_acceptance(
            journey,
            accepted,
            transcript=tampered_transcript,
            invocation=members["logs/codex-invocation.json"],
            prompt=members["control/prompt.txt"],
            schema=members["control/return.schema.json"],
            output=members["exchange/codex-return.json"],
            normalized_return=members["exchange/normalized-return.json"],
            repository_diff=members["observations/repository.diff"],
            repository_root=archive_path.parent / "repository",
        )


def test_transcript_rejects_any_event_before_exact_thread_start(tmp_path: Path) -> None:
    transcript = b'{"type":"garbage"}\n{"type":"thread.started","thread_id":"too-late"}\n'
    with pytest.raises(ValueError, match="does not start with thread.started"):
        derive_external_agent_transcript(transcript, tmp_path / "repository", "pkg/service.py")
    with pytest.raises(ValueError, match="no exact thread_id"):
        derive_external_agent_transcript(b'{"type":"thread.started"}\n', tmp_path / "repository", "pkg/service.py")


def test_paired_machine_evidence_rejects_coherent_snapshot_forgery(
    accepted_packet: dict,
    tmp_path: Path,
) -> None:
    original_path = Path(accepted_packet["durable_archive"]["path"])
    members = _archive_members(original_path)
    members.pop("archive-manifest.json")
    original_expectation = ExternalAgentReplayExpectationV1Alpha1.model_validate_json(
        members["external-agent-replay-expectation.json"]
    )
    raw = json.loads(members["external-agent-round-trip-raw.json"])
    forged = copy.deepcopy(raw)
    forged["updated_snapshot"]["created_at"] = "2020-01-01T00:00:00Z"
    forged_snapshot = DurablePhase1IndexSnapshotV1Alpha1.model_validate(forged["updated_snapshot"])
    forged["acceptance_run"]["living_update"]["updated_snapshot_id"] = forged_snapshot.snapshot_id
    forged["acceptance_run"]["living_update"]["updated_snapshot_digest"] = forged_snapshot.snapshot_digest
    forged["fresh_process_reopen"]["snapshot_id"] = forged_snapshot.snapshot_id
    forged["fresh_process_reopen"]["snapshot_digest"] = forged_snapshot.snapshot_digest
    forged["incremental_update"]["snapshot_id"] = forged_snapshot.snapshot_id
    forged["incremental_update"]["snapshot_digest"] = forged_snapshot.snapshot_digest
    forged_run = ExternalCodingAgentAcceptanceRunV1Alpha1.model_validate(forged["acceptance_run"])
    forged["acceptance_run_id"] = forged_run.run_id
    forged_raw = _render(forged)
    forged_expectation = original_expectation.model_copy(
        update={
            "raw_member_digest": f"sha256:{hashlib.sha256(forged_raw).hexdigest()}",
            "acceptance_run_id": forged_run.run_id,
            "living_update_id": forged_run.living_update.update_id,
            "updated_snapshot_id": forged_snapshot.snapshot_id,
            "updated_snapshot_digest": forged_snapshot.snapshot_digest,
        }
    )
    members["external-agent-round-trip-raw.json"] = forged_raw
    members["external-agent-replay-expectation.json"] = _render(forged_expectation.model_dump(mode="json"))
    forged_path = tmp_path / "coherent-forgery.tar.gz"
    _deterministic_archive(forged_path, members)
    forged_receipt = verify_deterministic_archive(forged_path)

    with pytest.raises(AssertionError, match="expectation differs from paired machine evidence"):
        replay_external_agent_archive(
            forged_path,
            expected_archive_sha256=forged_receipt["sha256"],
            expected_archive_byte_count=forged_receipt["byte_count"],
            expected_replay_expectation=original_expectation,
        )


def test_workspace_root_relabel_is_rejected_by_exact_transcript_path(
    accepted_packet: dict,
    tmp_path: Path,
) -> None:
    members = _archive_members(Path(accepted_packet["durable_archive"]["path"]))
    members.pop("archive-manifest.json")
    expectation = ExternalAgentReplayExpectationV1Alpha1.model_validate_json(
        members["external-agent-replay-expectation.json"]
    )
    relabeled_root = str((tmp_path / "relabeled-repository").resolve())
    relabeled = expectation.model_copy(
        update={
            "workspace_root": relabeled_root,
            "audited_write_paths": (str((Path(relabeled_root) / expectation.target_path).resolve()),),
        }
    )
    members["external-agent-replay-expectation.json"] = _render(relabeled.model_dump(mode="json"))
    path = tmp_path / "workspace-relabel.tar.gz"
    _deterministic_archive(path, members)
    with pytest.raises(ValueError, match="differs from the exact target"):
        replay_external_agent_archive(path)


@pytest.mark.parametrize("kind", ["traversal", "symlink", "duplicate"])
def test_archive_rejects_unsafe_or_duplicate_members(tmp_path: Path, kind: str) -> None:
    path = tmp_path / f"{kind}.tar.gz"
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            names = ["../escape"] if kind == "traversal" else ["same", "same"] if kind == "duplicate" else ["link"]
            for name in names:
                info = tarfile.TarInfo(name)
                if kind == "symlink":
                    info.type = tarfile.SYMTYPE
                    info.linkname = "target"
                    archive.addfile(info)
                else:
                    payload = b"x"
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))
    path.write_bytes(buffer.getvalue())
    with pytest.raises(AssertionError, match="duplicated|non-regular|path traversal"):
        verify_deterministic_archive(path)


def test_archive_replay_accepts_only_the_paired_external_trust_root(accepted_packet: dict) -> None:
    path = Path(accepted_packet["durable_archive"]["path"])
    members = _archive_members(path)
    expectation = ExternalAgentReplayExpectationV1Alpha1.model_validate_json(
        members["external-agent-replay-expectation.json"]
    )
    receipt = accepted_packet["durable_archive"]
    replayed = replay_external_agent_archive(
        path,
        expected_archive_sha256=receipt["sha256"],
        expected_archive_byte_count=receipt["byte_count"],
        expected_replay_expectation=expectation,
    )
    assert replayed["accepted"] is True


def test_checked_in_machine_evidence_replays_from_external_trust_root(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    evidence = json.loads(
        (project_root / "docs/evidence/code-intelligence-external-agent-round-trip-v1.json").read_text()
    )
    archive_receipt = evidence["archive"]
    encoded = (project_root / archive_receipt["path"]).read_bytes()
    assert len(encoded) == archive_receipt["encoded_byte_count"]
    assert hashlib.sha256(encoded).hexdigest() == archive_receipt["encoded_sha256"]
    decoded = base64.b64decode(b"".join(encoded.split()), validate=True)
    assert len(decoded) == archive_receipt["decoded_byte_count"]
    assert f"sha256:{hashlib.sha256(decoded).hexdigest()}" == archive_receipt["decoded_sha256"]
    archive_path = tmp_path / "external-agent-round-trip.tar.gz"
    archive_path.write_bytes(decoded)
    with tarfile.open(archive_path, "r:gz") as archive:
        observed_members = []
        for item in archive.getmembers():
            stream = archive.extractfile(item)
            assert stream is not None
            payload = stream.read()
            observed_members.append(
                {
                    "byte_count": len(payload),
                    "path": item.name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    assert observed_members == evidence["members"]
    expected = ExternalAgentReplayExpectationV1Alpha1.model_validate(evidence["replay_expectation"])
    replayed = replay_external_agent_archive(
        archive_path,
        expected_archive_sha256=archive_receipt["decoded_sha256"],
        expected_archive_byte_count=archive_receipt["decoded_byte_count"],
        expected_replay_expectation=expected,
    )
    assert replayed["acceptance_run_id"] == evidence["identities"]["acceptance_run_id"]


# ---------------------------------------------------------------------------
# Execution-boundary opt-in: the real external agent may only be reached by an
# explicit allow_external_agent opt-in, checked before any process is spawned,
# never exercised against a real Codex process in this acceptance.
# ---------------------------------------------------------------------------


def _forbid_process_call(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("attempted to launch a real process without an explicit allow_external_agent opt-in")


def test_run_acceptance_denies_default_direct_real_run_before_any_process_call(tmp_path: Path) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(subprocess, "run", _forbid_process_call)
        mp.setattr(subprocess, "Popen", _forbid_process_call)
        with pytest.raises(PermissionError, match="allow_external_agent"):
            run_acceptance(tmp_path)


def test_run_codex_exec_denies_direct_invocation_before_any_process_call(tmp_path: Path) -> None:
    request = AgentRunRequest(
        repository=tmp_path,
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        prompt=b"{}",
        model="fixture-model",
        executable="codex",
        expected_version="0.0.0",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(subprocess, "run", _forbid_process_call)
        mp.setattr(subprocess, "Popen", _forbid_process_call)
        with pytest.raises(PermissionError, match="allow_external_agent"):
            run_codex_exec(request)


def test_run_acceptance_injected_fake_runner_needs_no_real_execution_opt_in(accepted_packet: dict) -> None:
    # accepted_packet (module fixture) is built by run_acceptance(root, agent_runner=_fake_external_agent, ...)
    # with no allow_external_agent argument at all: an injected fake/test runner is exempt from
    # the real-execution opt-in precisely because it cannot launch the external process.
    assert accepted_packet["accepted"] is True


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_help_is_offline_and_exits_zero() -> None:
    result = _run_cli("--help")
    assert result.returncode == 0
    assert "--allow-external-agent" in result.stdout
    assert "--replay-archive" in result.stdout


def test_cli_no_args_fails_closed_offline() -> None:
    result = _run_cli()
    assert result.returncode != 0
    assert "--output and --archive are required" in result.stderr


def test_cli_unknown_option_fails_closed_offline() -> None:
    result = _run_cli("--not-a-real-flag")
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


def test_cli_replay_archive_is_offline_and_never_requires_allow_external_agent(accepted_packet: dict) -> None:
    archive_path = Path(accepted_packet["durable_archive"]["path"])
    result = _run_cli("--replay-archive", str(archive_path))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["contract_validated"] is True
    assert payload["trust_root_authenticated"] is False


def test_cli_live_run_without_allow_external_agent_fails_closed_before_any_process(tmp_path: Path) -> None:
    result = _run_cli("--output", str(tmp_path / "out.json"), "--archive", str(tmp_path / "archive.tar.gz"))
    assert result.returncode != 0
    assert "--allow-external-agent" in result.stderr
    assert not (tmp_path / "out.json").exists()
