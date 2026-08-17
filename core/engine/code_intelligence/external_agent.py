"""Exact receipts for a real external coding-agent round trip.

The external chain is deliberately separate from the settled local harness
chain: an observed Codex interval is not a harness-applied mutation.  Neither
observation grants the external agent any ACE authority.
"""

from __future__ import annotations

import json
import posixpath
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from core.engine.code_intelligence.contracts import (
    CodeIntelligenceJourneyV1Alpha1,
    CodeIntelligenceLivingUpdateV1Alpha1,
    CodingAgentReturnReceiptV1Alpha1,
    CodingAgentReturnV1Alpha1,
    FrozenContract,
    deterministic_code_patch,
    raw_digest,
    stable_id,
)
from core.engine.code_intelligence.handoff import validate_coding_agent_return

_DIGEST = r"^sha256:[a-f0-9]{64}$"
_ALLOWED_COMMANDS = (
    "/bin/zsh -lc \"python3 -B -c 'from pkg.service import transform; assert transform(1) == 3'\"",
    "/bin/zsh -lc 'date -u +%Y-%m-%dT%H:%M:%SZ'",
)
_DATE_COMMAND_OUTPUT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\n$")
_FILE_CHANGE_ITEM_ID = "item_0"
_CHECK_COMMAND_ITEM_ID = "item_1"
_DATE_COMMAND_ITEM_ID = "item_2"
_AGENT_MESSAGE_ITEM_ID = "item_3"
_TRANSCRIPT_EVENT_COUNT = 10


_COMMAND_LIKE_KEYS = ("command", "cmd")


def _normalize_macos_tmp_alias(path: str) -> str:
    """Normalize only macOS's documented ``/private/tmp`` alias."""

    normalized = posixpath.normpath(path)
    if normalized == "/private/tmp" or normalized.startswith("/private/tmp/"):
        return normalized.removeprefix("/private")
    return normalized


def _is_legitimate_command_position(container: dict[str, Any], key: str) -> bool:
    return (
        key == "command"
        and container.get("type") == "command_execution"
        and container.get("id") in (_CHECK_COMMAND_ITEM_ID, _DATE_COMMAND_ITEM_ID)
    )


def _reject_hidden_command_keys(node: Any) -> None:
    """Recursively reject any nested "command"/"cmd" key outside the exact
    command_execution.command positions of the two known command items --
    "cmd" is never a legitimate key anywhere in the frozen lifecycle."""

    if isinstance(node, dict):
        for key, value in node.items():
            if key in _COMMAND_LIKE_KEYS and not _is_legitimate_command_position(node, key):
                raise ValueError(
                    "external-agent transcript contains a command/cmd key outside the exact "
                    "command_execution.command positions in the frozen ten-event lifecycle"
                )
            _reject_hidden_command_keys(value)
    elif isinstance(node, list):
        for item in node:
            _reject_hidden_command_keys(item)


_FORBIDDEN_TOOL_MARKER_TOKENS: dict[str, tuple[str, ...]] = {
    "tool": ("browser", "playwright", "puppeteer", "mcp", "web_search", "network", "http", "fetch", "curl", "wget"),
    "tool_name": ("browser", "mcp", "modelcontextprotocol", "web_search", "network", "http", "fetch", "curl", "wget"),
    "name": ("browser", "mcp", "web_search", "network", "http", "fetch", "curl", "wget"),
}


def _matches_forbidden_tool_token(value: str, tokens: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(re.search(rf"(?:^|[^a-z0-9]){re.escape(token)}(?:[^a-z0-9]|$)", lowered) for token in tokens)


def _reject_forbidden_tool_markers(node: Any) -> None:
    """Recursively reject any nested "tool"/"tool_name"/"name" key naming a
    browser, MCP, or network tool -- no legitimate event or item in the
    frozen ten-event lifecycle ever carries one of these markers. Matching is
    case-insensitive and bounded-substring, so qualified or suffixed variants
    (e.g. "mcp__filesystem", "web_search_query", "Browser") are also rejected."""

    if isinstance(node, dict):
        for key, value in node.items():
            forbidden_tokens = _FORBIDDEN_TOOL_MARKER_TOKENS.get(key)
            if forbidden_tokens and isinstance(value, str) and _matches_forbidden_tool_token(value, forbidden_tokens):
                raise ValueError(
                    "external-agent transcript contains a forbidden browser/MCP/network tool "
                    f"marker ({key!r}: {value!r}) outside the frozen ten-event lifecycle"
                )
            _reject_forbidden_tool_markers(value)
    elif isinstance(node, list):
        for item in node:
            _reject_forbidden_tool_markers(item)


def _exact_item(event: dict[str, Any], *, event_type: str, item_type: str, item_id: str) -> dict[str, Any]:
    if event.get("type") != event_type:
        raise ValueError(f"external-agent transcript expected an exact {event_type} event for {item_type} {item_id}")
    item = event.get("item")
    if not isinstance(item, dict):
        raise ValueError("external-agent transcript item event has no exact item object")
    if item.get("id") != item_id or item.get("type") != item_type:
        raise ValueError("external-agent transcript item id or type is crossed")
    return item


def _exact_command_pair(
    started_event: dict[str, Any],
    completed_event: dict[str, Any],
    *,
    item_id: str,
    command: str,
) -> dict[str, Any]:
    started = _exact_item(started_event, event_type="item.started", item_type="command_execution", item_id=item_id)
    completed = _exact_item(
        completed_event, event_type="item.completed", item_type="command_execution", item_id=item_id
    )
    if started.get("command") != command or completed.get("command") != command:
        raise ValueError("external-agent command differs from the exact known allowed command")
    if started.get("status") != "in_progress" or started.get("exit_code") is not None:
        raise ValueError("external-agent command did not start in progress")
    if completed.get("status") != "completed" or completed.get("exit_code") != 0:
        raise ValueError("external-agent command did not complete with exit code zero")
    return completed


def derive_external_agent_transcript(
    transcript: bytes,
    repository_root: Path,
    target_path: str,
    *,
    replay_macos_tmp_alias: bool = False,
) -> tuple[str, str, int, tuple[str, ...], tuple[str, ...], tuple[str, ...], str]:
    """Derive session, commands, exact writes, and the sole return message.

    Validates the exact frozen ten-event Codex lifecycle -- rejecting any
    nested "command"/"cmd" key outside the two known command_execution
    items, and rejecting any nested "tool"/"tool_name"/"name" key naming a
    browser, MCP, or network tool anywhere in the transcript -- rather than
    searching arbitrary nested keys for command-shaped strings: one
    thread.started session, one turn.started, a matched file_change
    item.started/item.completed pair naming the sole target update, two
    matched command_execution pairs for the exact known allowed commands
    (each completed with exit code zero, the date command's output in the
    observed safe shape), one completed agent_message parseable as the
    exact coding-agent return, and one turn.completed -- with no extra,
    reordered, missing, or crossed event or item.
    """

    events: list[dict[str, Any]] = []
    for line in transcript.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("external-agent transcript contains a non-JSON event") from exc
        if not isinstance(event, dict):
            raise ValueError("external-agent transcript contains a non-object event")
        events.append(event)
    if not events:
        raise ValueError("external-agent transcript contains no events")
    _reject_hidden_command_keys(events)
    _reject_forbidden_tool_markers(events)
    if events[0].get("type") != "thread.started":
        raise ValueError("external-agent transcript does not start with thread.started")
    first_thread_id = events[0].get("thread_id")
    if not isinstance(first_thread_id, str) or not first_thread_id:
        raise ValueError("external-agent first thread.started event has no exact thread_id")
    if sum(event.get("type") == "thread.started" for event in events) != 1:
        raise ValueError("external-agent transcript must contain exactly one thread.started session event")
    if len(events) != _TRANSCRIPT_EVENT_COUNT:
        raise ValueError("external-agent transcript does not contain the exact ten-event lifecycle")
    if events[1].get("type") != "turn.started":
        raise ValueError("external-agent transcript second event is not an exact turn.started")
    if events[_TRANSCRIPT_EVENT_COUNT - 1].get("type") != "turn.completed":
        raise ValueError("external-agent transcript does not end with an exact turn.completed")

    expected_write = str((repository_root / target_path).resolve())
    change_started = _exact_item(
        events[2], event_type="item.started", item_type="file_change", item_id=_FILE_CHANGE_ITEM_ID
    )
    change_completed = _exact_item(
        events[3], event_type="item.completed", item_type="file_change", item_id=_FILE_CHANGE_ITEM_ID
    )
    if change_started.get("status") != "in_progress" or change_completed.get("status") != "completed":
        raise ValueError("external-agent file_change item did not move from started to completed")
    if change_started.get("changes") != change_completed.get("changes"):
        raise ValueError("external-agent file_change started and completed changes differ")
    changes = change_completed.get("changes")
    if not isinstance(changes, list) or len(changes) != 1:
        raise ValueError("external-agent file_change item does not contain exactly one exact change")
    change = changes[0]
    path = change.get("path") if isinstance(change, dict) else None
    observed_write = str(Path(path).resolve()) if isinstance(path, str) else None
    audited_write = expected_write
    if replay_macos_tmp_alias:
        # Historical macOS receipts observe ``/tmp`` while pathlib records the
        # same filesystem location as ``/private/tmp``. Normalize only during
        # immutable archive replay; live validation retains exact host paths.
        expected_write = _normalize_macos_tmp_alias(expected_write)
        if observed_write is not None:
            observed_write = _normalize_macos_tmp_alias(observed_write)
    if observed_write != expected_write:
        raise ValueError("external-agent file_change path differs from the exact target")
    if not isinstance(change, dict) or change.get("kind") != "update":
        raise ValueError("external-agent file_change kind is not update")
    writes = ((audited_write, "update"),)

    check_command, date_command = _ALLOWED_COMMANDS
    _exact_command_pair(events[4], events[5], item_id=_CHECK_COMMAND_ITEM_ID, command=check_command)
    date_completed = _exact_command_pair(events[6], events[7], item_id=_DATE_COMMAND_ITEM_ID, command=date_command)
    date_output = date_completed.get("aggregated_output")
    if not isinstance(date_output, str) or not _DATE_COMMAND_OUTPUT.match(date_output):
        raise ValueError("external-agent date command output is not the observed safe shape")

    message_item = _exact_item(
        events[8], event_type="item.completed", item_type="agent_message", item_id=_AGENT_MESSAGE_ITEM_ID
    )
    message_text = message_item.get("text")
    if not isinstance(message_text, str) or not message_text:
        raise ValueError("external-agent agent_message has no exact text")
    try:
        CodingAgentReturnV1Alpha1.model_validate_json(message_text)
    except ValueError as exc:
        raise ValueError("external-agent agent_message text is not an exact coding-agent return") from exc

    return (
        first_thread_id,
        "thread.started",
        len(events),
        (check_command, date_command),
        tuple(path for path, _ in writes),
        tuple(kind for _, kind in writes),
        message_text,
    )


def validate_external_agent_invocation(
    invocation: bytes,
    *,
    executable: str,
    cli_version: str,
    model: str,
    repository_root: Path,
    replay_macos_tmp_alias: bool = False,
) -> tuple[str, ...]:
    """Parse one exact, no-bypass Codex invocation envelope."""

    try:
        envelope = json.loads(invocation)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("external-agent invocation is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"argv", "cli_version", "model"}:
        raise ValueError("external-agent invocation envelope has an unexpected shape")
    argv = envelope["argv"]
    if not isinstance(argv, list) or any(not isinstance(item, str) or not item for item in argv):
        raise ValueError("external-agent invocation argv is not an exact string sequence")
    if envelope["cli_version"] != cli_version or envelope["model"] != model:
        raise ValueError("external-agent invocation version or model differs from delivery")
    expected = [
        executable,
        "exec",
        "--ephemeral",
        "--sandbox",
        "workspace-write",
        "--ignore-user-config",
        "--ignore-rules",
        "--model",
        model,
        "--json",
        "--output-schema",
        str((repository_root.parent / "control" / "return.schema.json").resolve()),
        "--output-last-message",
        str((repository_root.parent / "exchange" / "codex-return.json").resolve()),
        "-C",
        str(repository_root.resolve()),
        "-",
    ]
    normalized = list(argv)
    comparable_expected = list(expected)
    if len(normalized) == len(expected):
        for index in (11, 13, 15):
            normalized[index] = str(Path(normalized[index]).resolve())
            if replay_macos_tmp_alias:
                normalized[index] = _normalize_macos_tmp_alias(normalized[index])
                comparable_expected[index] = _normalize_macos_tmp_alias(comparable_expected[index])
    if normalized != comparable_expected:
        raise ValueError("external-agent invocation differs from the exact no-bypass Codex argv")
    return tuple(argv)


def coding_agent_return_schema(journey: CodeIntelligenceJourneyV1Alpha1) -> dict[str, Any]:
    """Build the run-specific strict output schema for one exact handoff."""

    schema = CodingAgentReturnV1Alpha1.model_json_schema()
    properties = schema["properties"]
    receipt = journey.handoff.receipt
    constants = {
        "contract": "ace.code-intelligence.coding-agent-return/v1alpha1",
        "receiver_ref": receipt.receiver_ref,
        "handoff_id": receipt.handoff_id,
        "index_id": receipt.index_id,
        "lens_id": receipt.lens_id,
        "manifest_id": receipt.manifest_id,
        "disposition": "change_proposed",
        "consumed_block_ids": [block.block_id for block in journey.handoff.blocks],
        "changed_paths": [journey.lens.target_path],
        "claims_source_authority": False,
        "claims_reasoning_authority": False,
        "claims_delivery_authority": False,
        "claims_effect_authority": False,
    }
    for field, value in constants.items():
        if isinstance(value, bool):
            properties[field] = {"type": "boolean", "const": value}
        elif isinstance(value, list):
            properties[field] = {
                "type": "array",
                "items": {"type": "string", "enum": value},
                "minItems": len(value),
                "maxItems": len(value),
            }
        else:
            properties[field] = {"type": "string", "const": value}
    properties["verification_refs"] = {
        "type": "array",
        "items": {"type": "string", "minLength": 1, "maxLength": 2048},
        "minItems": 1,
        "maxItems": 64,
    }
    properties["uncertainties"] = {
        "type": "array",
        "items": {"type": "string", "minLength": 1, "maxLength": 4000},
        "maxItems": 64,
    }
    schema["required"] = list(properties)
    schema["additionalProperties"] = False
    return schema


class ExternalCodingAgentDeliveryReceiptV1Alpha1(FrozenContract):
    """Controller-observed delivery to one exact non-interactive agent run."""

    contract: Literal["ace.code-intelligence.external-agent-delivery/v1alpha1"] = (
        "ace.code-intelligence.external-agent-delivery/v1alpha1"
    )
    controller_run_id: str = Field(min_length=1, max_length=128)
    receiver_ref: str = Field(min_length=1, max_length=256)
    handoff_id: str = Field(min_length=1, max_length=128)
    index_id: str = Field(min_length=1, max_length=128)
    lens_id: str = Field(min_length=1, max_length=128)
    manifest_id: str = Field(min_length=1, max_length=128)
    return_id: str = Field(min_length=1, max_length=128)
    adapter: Literal["codex-exec"] = "codex-exec"
    executable: str = Field(min_length=1, max_length=1_024)
    cli_version: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=256)
    first_event_type: str = Field(min_length=1, max_length=256)
    event_count: int = Field(ge=1)
    sandbox: Literal["workspace-write"] = "workspace-write"
    ephemeral: Literal[True] = True
    user_config_ignored: Literal[True] = True
    project_rules_ignored: Literal[True] = True
    approval_bypass_used: Literal[False] = False
    sandbox_bypass_used: Literal[False] = False
    additional_write_directories: tuple[str, ...] = ()
    prompt_digest: str = Field(pattern=_DIGEST)
    prompt_byte_count: int = Field(ge=1)
    schema_digest: str = Field(pattern=_DIGEST)
    schema_byte_count: int = Field(ge=1)
    output_digest: str = Field(pattern=_DIGEST)
    output_byte_count: int = Field(ge=1)
    normalized_return_digest: str = Field(pattern=_DIGEST)
    normalized_return_byte_count: int = Field(ge=1)
    transcript_digest: str = Field(pattern=_DIGEST)
    transcript_byte_count: int = Field(ge=1)
    stderr_digest: str = Field(pattern=_DIGEST)
    stderr_byte_count: int = Field(ge=0)
    started_at: datetime
    acknowledged_at: datetime
    completed_at: datetime
    exit_code: Literal[0] = 0
    external_delivery_observed: Literal[True] = True
    bounded_access_observed: Literal[True] = True
    cryptographic_read_isolation: Literal[False] = False
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_observed_delivery(self) -> Self:
        if not self.started_at <= self.acknowledged_at <= self.completed_at:
            raise ValueError("external-agent delivery timestamps are not monotonic")
        if self.additional_write_directories:
            raise ValueError("external-agent acceptance cannot grant additional write directories")
        return self

    @property
    def receipt_id(self) -> str:
        return stable_id("external_agent_delivery", self)


class CodeChangeSetReceiptV1Alpha1(FrozenContract):
    """Exact bytes observed across the exclusive external-agent interval."""

    contract: Literal["ace.code-intelligence.external-code-change-set/v1alpha1"] = (
        "ace.code-intelligence.external-code-change-set/v1alpha1"
    )
    controller_run_id: str = Field(min_length=1, max_length=128)
    return_id: str = Field(min_length=1, max_length=128)
    repository_revision_before: str = Field(pattern=r"^[a-f0-9]{40}$")
    repository_revision_after: str = Field(pattern=r"^[a-f0-9]{40}$")
    changed_paths: tuple[str, ...]
    path: str = Field(min_length=1, max_length=1_024)
    mode_before: str = Field(pattern=r"^[0-7]{6}$")
    mode_after: str = Field(pattern=r"^[0-7]{6}$")
    symlink_before: Literal[False] = False
    symlink_after: Literal[False] = False
    before_body: str = Field(max_length=64_000)
    after_body: str = Field(max_length=64_000)
    before_digest: str = Field(pattern=_DIGEST)
    before_byte_count: int = Field(ge=0, le=64_000)
    after_digest: str = Field(pattern=_DIGEST)
    after_byte_count: int = Field(ge=0, le=64_000)
    patch: str = Field(max_length=128_000)
    patch_digest: str = Field(pattern=_DIGEST)
    patch_byte_count: int = Field(ge=1, le=128_000)
    repository_diff_digest: str = Field(pattern=_DIGEST)
    repository_diff_byte_count: int = Field(ge=1)
    git_status_digest: str = Field(pattern=_DIGEST)
    git_status_byte_count: int = Field(ge=1)
    head_unchanged: Literal[True] = True
    index_unchanged: Literal[True] = True
    staged_changes_observed: Literal[False] = False
    untracked_paths_observed: Literal[False] = False
    external_agent_interval_observed: Literal[True] = True
    harness_applied_mutation: Literal[False] = False
    actor_causation_cryptographically_proven: Literal[False] = False
    exact_bytes_observed: Literal[True] = True
    independent_of_coding_agent_claims: Literal[True] = True
    observed_at: datetime
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_single_path_change(self) -> Self:
        if self.repository_revision_after != self.repository_revision_before:
            raise ValueError("external-agent run changed the repository revision")
        if self.changed_paths != (self.path,):
            raise ValueError("change-set path differs from the exact changed-path inventory")
        if self.mode_after != self.mode_before:
            raise ValueError("external-agent run changed the file mode")
        before = self.before_body.encode()
        after = self.after_body.encode()
        patch = self.patch.encode()
        if self.before_byte_count != len(before) or self.before_digest != raw_digest(before):
            raise ValueError("change-set before bytes differ from exact body")
        if self.after_byte_count != len(after) or self.after_digest != raw_digest(after):
            raise ValueError("change-set after bytes differ from exact body")
        if self.patch != deterministic_code_patch(self.path, self.before_body, self.after_body):
            raise ValueError("change-set patch differs from deterministic before/after bytes")
        if self.patch_byte_count != len(patch) or self.patch_digest != raw_digest(patch):
            raise ValueError("change-set patch receipt differs from exact patch bytes")
        if self.after_digest == self.before_digest:
            raise ValueError("change-set before and after bytes are identical")
        return self

    @property
    def receipt_id(self) -> str:
        return stable_id("external_code_change_set", self)


class ExternalCodeVerificationObservationV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.external-code-verification/v1alpha1"] = (
        "ace.code-intelligence.external-code-verification/v1alpha1"
    )
    observer_ref: str = Field(min_length=1, max_length=256)
    return_id: str = Field(min_length=1, max_length=128)
    change_set_id: str = Field(min_length=1, max_length=128)
    changed_paths: tuple[str, ...]
    command: tuple[str, ...]
    status: Literal["passed", "failed"]
    exit_code: int
    stdout_digest: str = Field(pattern=_DIGEST)
    stderr_digest: str = Field(pattern=_DIGEST)
    observed_at: datetime
    independent_of_coding_agent_claims: Literal[True] = True
    self_authenticates_command_execution: Literal[False] = False
    verifier_replay_required: Literal[True] = True
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_observation(self) -> Self:
        if not self.command or len(self.command) > 32:
            raise ValueError("verification command must contain 1..32 arguments")
        if any(not item or len(item) > 2_048 for item in self.command):
            raise ValueError("verification command arguments must contain 1..2048 characters")
        if (
            not self.changed_paths
            or len(self.changed_paths) > 64
            or len(set(self.changed_paths)) != len(self.changed_paths)
        ):
            raise ValueError("verification changed paths must contain 1..64 unique items")
        if any(not item or len(item) > 1_024 for item in self.changed_paths):
            raise ValueError("verification changed paths must contain 1..1024 characters")
        if (self.status == "passed") != (self.exit_code == 0):
            raise ValueError("verification status differs from observed exit code")
        return self

    @property
    def verification_id(self) -> str:
        return stable_id("external_code_verification", self)


class ExternalCodingAgentAcceptanceRunV1Alpha1(FrozenContract):
    """External-specific delivery, change, verification, and durable update."""

    contract: Literal["ace.code-intelligence.external-agent-acceptance-run/v1alpha1"] = (
        "ace.code-intelligence.external-agent-acceptance-run/v1alpha1"
    )
    status: Literal["candidate_external_observed"] = "candidate_external_observed"
    receiver_ref: str
    initial_index_id: str
    initial_lens_id: str
    initial_manifest_id: str
    initial_handoff_id: str
    initial_snapshot_id: str
    delivery: ExternalCodingAgentDeliveryReceiptV1Alpha1
    agent_return: CodingAgentReturnV1Alpha1
    return_receipt: CodingAgentReturnReceiptV1Alpha1
    change_set: CodeChangeSetReceiptV1Alpha1
    verification: ExternalCodeVerificationObservationV1Alpha1
    living_update: CodeIntelligenceLivingUpdateV1Alpha1
    limitations: tuple[str, ...]
    external_delivery_observed: Literal[True] = True
    exact_changed_bytes_observed: Literal[True] = True
    independent_verification_passed: Literal[True] = True
    fresh_process_reopen_observed: Literal[True] = True
    old_snapshot_still_readable: Literal[True] = True
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_outer_chain(self) -> Self:
        returned = self.agent_return
        receipt = self.return_receipt
        update = self.living_update
        if self.delivery.controller_run_id != self.change_set.controller_run_id:
            raise ValueError("delivery and changed bytes name different controller runs")
        coordinates = (
            (self.delivery.receiver_ref, self.receiver_ref),
            (returned.receiver_ref, self.receiver_ref),
            (receipt.receiver_ref, self.receiver_ref),
            (self.delivery.handoff_id, self.initial_handoff_id),
            (returned.handoff_id, self.initial_handoff_id),
            (receipt.handoff_id, self.initial_handoff_id),
            (self.delivery.index_id, self.initial_index_id),
            (returned.index_id, self.initial_index_id),
            (receipt.index_id, self.initial_index_id),
            (self.delivery.lens_id, self.initial_lens_id),
            (returned.lens_id, self.initial_lens_id),
            (receipt.lens_id, self.initial_lens_id),
            (self.delivery.manifest_id, self.initial_manifest_id),
            (returned.manifest_id, self.initial_manifest_id),
            (receipt.manifest_id, self.initial_manifest_id),
            (self.delivery.return_id, returned.return_id),
            (receipt.return_id, returned.return_id),
            (self.change_set.return_id, returned.return_id),
            (self.verification.return_id, returned.return_id),
            (update.return_id, returned.return_id),
        )
        if any(actual != expected for actual, expected in coordinates):
            raise ValueError("external-agent acceptance identity chain is crossed")
        if returned.changed_paths != receipt.changed_paths or returned.changed_paths != self.change_set.changed_paths:
            raise ValueError("external-agent changed paths differ across return and exact bytes")
        if returned.changed_paths != self.verification.changed_paths or returned.changed_paths != update.changed_paths:
            raise ValueError("external-agent changed paths differ across verification and update")
        if self.verification.change_set_id != self.change_set.receipt_id:
            raise ValueError("external verification names a different exact change set")
        if update.mutation_id != self.change_set.receipt_id:
            raise ValueError("living update names a different external change set")
        if (
            update.return_receipt_id != receipt.receipt_id
            or update.verification_id != self.verification.verification_id
        ):
            raise ValueError("living update names a different return receipt or verification")
        if update.before_source_digest != self.change_set.before_digest:
            raise ValueError("living update before digest differs from external change set")
        if update.after_source_digest != self.change_set.after_digest:
            raise ValueError("living update after digest differs from external change set")
        if update.patch_digest != self.change_set.patch_digest:
            raise ValueError("living update patch digest differs from external change set")
        if update.initial_snapshot_id != self.initial_snapshot_id:
            raise ValueError("living update initial snapshot differs from external run")
        if update.initial_index_id != self.initial_index_id or update.initial_lens_id != self.initial_lens_id:
            raise ValueError("living update initial index or lens differs from external run")
        if self.verification.status != "passed":
            raise ValueError("external acceptance requires independent passing verification")
        return self

    @property
    def run_id(self) -> str:
        return stable_id("external_agent_acceptance", self)


class ExternalAgentReplayExpectationV1Alpha1(FrozenContract):
    """Machine coordinates for replaying the paired durable evidence envelope."""

    contract: Literal["ace.code-intelligence.external-agent-replay-expectation/v1alpha1"] = (
        "ace.code-intelligence.external-agent-replay-expectation/v1alpha1"
    )
    raw_member_digest: str = Field(pattern=_DIGEST)
    invocation_digest: str = Field(pattern=_DIGEST)
    invocation_byte_count: int = Field(ge=1)
    transcript_digest: str = Field(pattern=_DIGEST)
    workspace_root: str = Field(min_length=1, max_length=2_048)
    target_path: str = Field(min_length=1, max_length=1_024)
    audited_write_paths: tuple[str, ...]
    audited_write_kinds: tuple[Literal["update"], ...]
    acceptance_run_id: str
    delivery_receipt_id: str
    return_id: str
    return_receipt_id: str
    change_set_receipt_id: str
    verification_id: str
    living_update_id: str
    initial_snapshot_id: str
    initial_snapshot_digest: str = Field(pattern=_DIGEST)
    updated_snapshot_id: str
    updated_snapshot_digest: str = Field(pattern=_DIGEST)
    old_snapshot_id: str
    old_snapshot_digest: str = Field(pattern=_DIGEST)
    post_restart_index_id: str
    post_restart_lens_id: str
    post_restart_source_block_id: str
    post_restart_source_body_digest: str = Field(pattern=_DIGEST)
    post_restart_source_file_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def exact_observed_write(self) -> Self:
        expected = str((Path(self.workspace_root) / self.target_path).resolve())
        if self.audited_write_paths != (expected,) or self.audited_write_kinds != ("update",):
            raise ValueError("external-agent replay expectation does not bind the exact audited target update")
        return self


def validate_external_coding_agent_acceptance(
    initial_journey: CodeIntelligenceJourneyV1Alpha1,
    accepted: ExternalCodingAgentAcceptanceRunV1Alpha1,
    *,
    transcript: bytes,
    invocation: bytes,
    prompt: bytes,
    schema: bytes,
    output: bytes,
    normalized_return: bytes,
    repository_diff: bytes,
    repository_root: Path,
    replay_macos_tmp_alias: bool = False,
) -> ExternalCodingAgentAcceptanceRunV1Alpha1:
    """Rebuild delivery coordinates from raw envelopes and revalidate the return."""

    delivery = accepted.delivery
    validate_external_agent_invocation(
        invocation,
        executable=delivery.executable,
        cli_version=delivery.cli_version,
        model=delivery.model,
        repository_root=repository_root,
        replay_macos_tmp_alias=replay_macos_tmp_alias,
    )
    session_id, first_event_type, event_count, _, _, _, message_text = derive_external_agent_transcript(
        transcript,
        repository_root,
        accepted.change_set.path,
        replay_macos_tmp_alias=replay_macos_tmp_alias,
    )
    byte_checks = (
        (delivery.transcript_digest, raw_digest(transcript), delivery.transcript_byte_count, len(transcript)),
        (delivery.prompt_digest, raw_digest(prompt), delivery.prompt_byte_count, len(prompt)),
        (delivery.schema_digest, raw_digest(schema), delivery.schema_byte_count, len(schema)),
        (delivery.output_digest, raw_digest(output), delivery.output_byte_count, len(output)),
        (
            delivery.normalized_return_digest,
            raw_digest(normalized_return),
            delivery.normalized_return_byte_count,
            len(normalized_return),
        ),
    )
    if any(
        actual != expected or actual_size != expected_size
        for actual, expected, actual_size, expected_size in byte_checks
    ):
        raise ValueError("external-agent delivery envelope digest or byte count differs")
    if (delivery.session_id, delivery.first_event_type, delivery.event_count) != (
        session_id,
        first_event_type,
        event_count,
    ):
        raise ValueError("external-agent delivery transcript coordinates differ")
    expected = initial_journey.handoff.receipt
    coordinates = (
        (delivery.receiver_ref, expected.receiver_ref),
        (delivery.handoff_id, expected.handoff_id),
        (delivery.index_id, expected.index_id),
        (delivery.lens_id, expected.lens_id),
        (delivery.manifest_id, expected.manifest_id),
    )
    if any(actual != wanted for actual, wanted in coordinates):
        raise ValueError("external-agent delivery differs from the exact live handoff")
    prompt_text = prompt.decode("utf-8")
    try:
        prompt_handoff = json.loads(
            prompt_text.split("BEGIN_EXACT_ACE_HANDOFF_JSON\n", 1)[1].split("\nEND_EXACT_ACE_HANDOFF_JSON", 1)[0]
        )
    except (IndexError, json.JSONDecodeError) as exc:
        raise ValueError("external-agent prompt does not contain one valid exact handoff envelope") from exc
    if prompt_handoff != initial_journey.handoff.model_dump(mode="json"):
        raise ValueError("external-agent prompt handoff differs from initial journey")
    try:
        observed_schema = json.loads(schema)
    except json.JSONDecodeError as exc:
        raise ValueError("external-agent schema envelope is not JSON") from exc
    if observed_schema != coding_agent_return_schema(initial_journey):
        raise ValueError("external-agent schema differs from the exact live return schema")
    try:
        output_return = CodingAgentReturnV1Alpha1.model_validate_json(output)
    except ValueError as exc:
        raise ValueError("external-agent output is not an exact coding-agent return") from exc
    if output_return != accepted.agent_return:
        raise ValueError("external-agent output return differs from accepted return")
    message_bytes = message_text.encode()
    if output not in (message_bytes, message_bytes + b"\n"):
        raise ValueError(
            "external-agent agent_message text differs from the exact output file beyond a trailing newline"
        )
    if CodingAgentReturnV1Alpha1.model_validate_json(message_text) != accepted.agent_return:
        raise ValueError("external-agent agent_message return differs from accepted return")
    expected_normalized = (
        json.dumps(accepted.agent_return.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode()
    if normalized_return != expected_normalized:
        raise ValueError("external-agent normalized return differs from accepted return")
    if accepted.change_set.repository_diff_digest != raw_digest(repository_diff):
        raise ValueError("external-agent repository diff digest differs from raw archive member")
    if accepted.change_set.repository_diff_byte_count != len(repository_diff):
        raise ValueError("external-agent repository diff byte count differs from raw archive member")
    rebuilt = validate_coding_agent_return(initial_journey.handoff, accepted.agent_return)
    for field in (
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
    ):
        if getattr(rebuilt, field) != getattr(accepted.return_receipt, field):
            raise ValueError(f"external-agent return receipt differs at {field}")
    return accepted
