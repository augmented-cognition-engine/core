"""Run one genuine Codex CLI handoff-to-living-update acceptance chain."""

from __future__ import annotations

import argparse
import builtins
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from git import Repo

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if (_PROJECT_ROOT / "core" / "engine" / "code_intelligence").is_dir():
    # Deterministically import this checkout's own ``core`` package, not
    # whichever copy the interpreter's site-packages happen to resolve first
    # (e.g. an unrelated worktree's editable install). A script that ships
    # installed, with no sibling ``core`` package here, falls through to
    # normal installed-package resolution.
    sys.path[:] = [entry for entry in sys.path if entry not in ("", str(_PROJECT_ROOT))]
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.engine.code_intelligence.contracts import (
    CodeIntelligenceJourneyV1Alpha1,
    CodeIntelligenceLivingUpdateV1Alpha1,
    CodingAgentReturnV1Alpha1,
    RepositoryIndexIdentityV1Alpha1,
    deterministic_code_patch,
)
from core.engine.code_intelligence.external_agent import (
    CodeChangeSetReceiptV1Alpha1,
    ExternalAgentReplayExpectationV1Alpha1,
    ExternalCodeVerificationObservationV1Alpha1,
    ExternalCodingAgentAcceptanceRunV1Alpha1,
    ExternalCodingAgentDeliveryReceiptV1Alpha1,
    coding_agent_return_schema,
    derive_external_agent_transcript,
    validate_external_agent_invocation,
    validate_external_coding_agent_acceptance,
)
from core.engine.code_intelligence.handoff import validate_coding_agent_return
from core.engine.code_intelligence.journey import CodeIntelligenceJourney
from core.engine.code_intelligence.snapshot_store import (
    DurablePhase1IndexSnapshotV1Alpha1,
    DurablePhase1IndexStore,
)
from core.engine.intelligence.graph_builder import GraphBuilder
from scripts.verify_code_intelligence_single_chain_living_run import (
    _QUERY,
    _RECEIVER,
    _TARGET,
    _make_repository,
    _source_block,
)

if (_PROJECT_ROOT / "core" / "engine" / "code_intelligence").is_dir():
    _origin = Path(sys.modules[DurablePhase1IndexStore.__module__].__file__).resolve()
    if _PROJECT_ROOT not in _origin.parents:
        raise RuntimeError(
            "verify_code_intelligence_external_agent_round_trip imported "
            f"core.engine.code_intelligence.snapshot_store from {_origin}, not this checkout "
            f"({_PROJECT_ROOT}); refusing to run against a different package copy."
        )

_MODEL = "gpt-5.6-sol"
_EXPECTED_VERSION = "0.147.0-alpha.6.5"
_PROVIDER_MODULES = frozenset(("anthropic", "openai", "google.generativeai", "mistralai"))
_SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(rb"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{12,}\b"),
    re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(
        rb"(?i)\b(?:OPENAI|ANTHROPIC|GITHUB|GH|AWS|GOOGLE|GEMINI|MISTRAL)_[A-Z0-9_]*"
        rb"(?:KEY|TOKEN|SECRET|PASSWORD)\b\s*[:=]\s*[^\s,]+"
    ),
    re.compile(rb"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)\b\s*[:=]\s*[^\s,]+"),
)
_LIMITATIONS = (
    "Acceptance covers one observed Codex CLI run over Python in one disposable local Git repository.",
    "The Codex workspace contained only the three source bodies in the exact live handoff, and its JSONL tool trace was audited; this is observed boundedness, not cryptographic filesystem-read isolation.",
    "The independent subprocess proves only the disposable fixture behavior it executes.",
    "The external tool produced bytes but received no ACE source, reasoning, change, approval, delivery, execution, or effect authority.",
    "The provider/rescan-forbidden fresh process reopens local generation two; this is not deployment, backup, rollback, recovery, or production-effect evidence.",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _canonical(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _pretty(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _validate_secret_free_members(members: dict[str, bytes]) -> dict[str, Any]:
    """Fail closed instead of freezing detected credential material."""

    for path, payload in members.items():
        if any(pattern.search(payload) for pattern in _SECRET_PATTERNS):
            raise AssertionError(f"external-agent evidence member contains secret-like material: {path}")
    return {
        "scanner_contract": "ace.external-agent-secret-scan/v1",
        "members_scanned": len(members),
        "findings": 0,
        "redactions_required": False,
    }


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _run_id(handoff_bytes: bytes, prepared_at: datetime) -> str:
    material = handoff_bytes + prepared_at.isoformat().encode()
    return f"external-agent-controller:{hashlib.sha256(material).hexdigest()[:32]}"


def _prompt(journey: Any, prepared_at: datetime) -> bytes:
    handoff = journey.handoff.model_dump(mode="json")
    blocks = ", ".join(block.block_id for block in journey.handoff.blocks)
    text = f"""You are the external coding agent for one bounded ACE acceptance run.

The JSON below is the complete authorized context. The disposable workspace contains exactly the same three source files. Do not read or write outside the workspace. Do not use network, plugins, MCP, or additional directories. Do not add, delete, rename, stage, or commit files. Edit only pkg/service.py. Make the smallest change that preserves the helper call and makes transform(1) equal 3. Run this check from the repository root:

python3 -B -c 'from pkg.service import transform; assert transform(1) == 3'

Return only JSON matching the supplied schema. Report consumed_block_ids exactly as [{blocks}]. Keep every authority claim false. verification_refs are your claims only; ACE will verify independently. Use an RFC3339 UTC submitted_at. Controller preparation time was {prepared_at.isoformat()}.

BEGIN_EXACT_ACE_HANDOFF_JSON
{json.dumps(handoff, indent=2, sort_keys=True)}
END_EXACT_ACE_HANDOFF_JSON
"""
    return text.encode()


def _external_fresh_process_probe(
    *,
    repository: Path,
    storage: Path,
    expected_index: RepositoryIndexIdentityV1Alpha1,
    expected_snapshot_id: str,
    expected_snapshot_digest: str,
    exchange: Path,
) -> dict[str, Any]:
    index_path = exchange / "external-updated-index.json"
    _write(index_path, _pretty(expected_index))
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--reopen-probe",
        "--repository",
        str(repository),
        "--storage",
        str(storage),
        "--expected-index",
        str(index_path),
        "--expected-snapshot-id",
        expected_snapshot_id,
        "--expected-snapshot-digest",
        expected_snapshot_digest,
    ]
    environment = os.environ.copy()
    for name in tuple(environment):
        if any(token in name.upper() for token in ("ANTHROPIC", "OPENAI", "GEMINI", "MISTRAL")):
            environment.pop(name, None)
    project_root = str(Path(__file__).resolve().parents[1])
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (project_root, environment.get("PYTHONPATH", "")) if item
    )
    completed = subprocess.run(
        command,
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _run_reopen_probe(args: argparse.Namespace) -> dict[str, Any]:
    expected_index = RepositoryIndexIdentityV1Alpha1.model_validate_json(args.expected_index.read_text())
    store = DurablePhase1IndexStore(args.storage, args.repository)

    def forbidden_scan(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("fresh-process external reopen attempted repository analysis")

    original_import = builtins.__import__

    def forbid_provider_import(name: str, *import_args: Any, **import_kwargs: Any) -> Any:
        if any(name == provider or name.startswith(provider + ".") for provider in _PROVIDER_MODULES):
            raise AssertionError(f"fresh-process external reopen attempted provider import: {name}")
        return original_import(name, *import_args, **import_kwargs)

    with (
        patch.object(GraphBuilder, "phase1_treesitter", forbidden_scan),
        patch.object(GraphBuilder, "phase3_analyze", forbidden_scan),
        patch.object(GraphBuilder, "incremental_update", forbidden_scan),
        patch.object(builtins, "__import__", forbid_provider_import),
    ):
        reopened = store.open_latest(
            expected_index=expected_index,
            expected_snapshot_id=args.expected_snapshot_id,
            expected_snapshot_digest=args.expected_snapshot_digest,
        )
        journey = CodeIntelligenceJourney(args.repository).run(
            query=_QUERY,
            target_path=_TARGET,
            receiver_ref=_RECEIVER,
            builder=reopened.builder,
            expected_index=expected_index,
        )
    if reopened.snapshot.snapshot_id != args.expected_snapshot_id:
        raise AssertionError("fresh process reopened a different external generation-two snapshot")
    block = _source_block(journey)
    source_path = Path(args.repository) / _TARGET
    return {
        "fresh_python_process": True,
        "snapshot_id": reopened.snapshot.snapshot_id,
        "snapshot_digest": reopened.snapshot.snapshot_digest,
        "generation": reopened.snapshot.generation,
        "index_id": journey.lens.index.index_id,
        "lens_id": journey.lens.lens_id,
        "manifest_id": journey.handoff.manifest.manifest_id,
        "handoff_id": journey.handoff.receipt.handoff_id,
        "source_path": _TARGET,
        "source_file_digest": _sha256(source_path.read_bytes()),
        "source_block_id": block.block_id,
        "source_body_digest": block.body_digest,
        "source_line_start": block.line_start,
        "source_line_end": block.line_end,
        "source_symbol": block.symbol,
        "source_symbol_line_start": block.symbol_line_start,
        "source_symbol_line_end": block.symbol_line_end,
        "journey": journey.model_dump(mode="json"),
        "full_rescan_permitted": False,
        "incremental_rescan_permitted": False,
        "provider_environment_present": False,
        "provider_import_permitted": False,
        "provider_invocation_permitted": False,
    }


@dataclass(frozen=True)
class AgentRunRequest:
    repository: Path
    schema_path: Path
    output_path: Path
    prompt: bytes
    model: str
    executable: str
    expected_version: str


@dataclass(frozen=True)
class AgentProcessObservation:
    executable: str
    cli_version: str
    model: str
    argv: tuple[str, ...]
    session_id: str
    first_event_type: str
    event_count: int
    transcript: bytes
    stderr: bytes
    output: bytes
    started_at: datetime
    acknowledged_at: datetime
    completed_at: datetime
    exit_code: int
    bounded_access_observed: bool
    audited_commands: tuple[str, ...]
    audited_write_paths: tuple[str, ...]
    audited_write_kinds: tuple[str, ...]


def run_codex_exec(request: AgentRunRequest, *, allow_external_agent: bool = False) -> AgentProcessObservation:
    """Launch one real Codex CLI process. Fails closed before any subprocess call.

    ``allow_external_agent`` must be passed explicitly as ``True`` by the caller;
    there is no ambient or default-on path to a real external process here or in
    ``run_acceptance``. An injected fake/test runner never reaches this function.
    """

    if not allow_external_agent:
        raise PermissionError(
            "run_codex_exec requires explicit allow_external_agent=True; it launches a real "
            "external Codex CLI process. Use an injected agent_runner for tests, or pass "
            "allow_external_agent=True (CLI: --allow-external-agent) only for a genuine run."
        )
    version = subprocess.run(
        [request.executable, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if request.expected_version not in version:
        raise AssertionError(f"unexpected Codex CLI version: {version}")
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
    started_at = _utcnow()
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    stderr_chunks: list[bytes] = []

    def drain_stderr() -> None:
        while chunk := process.stderr.read(65_536):
            stderr_chunks.append(chunk)

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()
    process.stdin.write(request.prompt)
    process.stdin.close()
    transcript_lines: list[bytes] = []
    events: list[dict[str, Any]] = []
    acknowledged_at: datetime | None = None
    for line in process.stdout:
        transcript_lines.append(line)
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError("Codex --json emitted a non-JSON line") from exc
        if not isinstance(event, dict):
            raise AssertionError("Codex --json emitted a non-object event")
        events.append(event)
        if acknowledged_at is None:
            acknowledged_at = _utcnow()
    exit_code = process.wait()
    stderr_thread.join()
    completed_at = _utcnow()
    transcript = b"".join(transcript_lines)
    stderr = b"".join(stderr_chunks)
    if exit_code != 0:
        _write(request.output_path.with_suffix(".failure-events.jsonl"), transcript)
        _write(request.output_path.with_suffix(".failure-stderr.txt"), stderr)
        raise AssertionError(
            f"Codex exec failed with exit {exit_code}; events={transcript.decode(errors='replace')}; "
            f"stderr={stderr.decode(errors='replace')}"
        )
    if acknowledged_at is None:
        raise AssertionError("Codex completed without a delivery acknowledgement event")
    session_id, first_event_type, event_count, commands, write_paths, write_kinds, _ = derive_external_agent_transcript(
        transcript,
        request.repository,
        _TARGET,
    )
    output = request.output_path.read_bytes()
    return AgentProcessObservation(
        executable=request.executable,
        cli_version=version,
        model=request.model,
        argv=argv,
        session_id=session_id,
        first_event_type=first_event_type,
        event_count=event_count,
        transcript=transcript,
        stderr=stderr,
        output=output,
        started_at=started_at,
        acknowledged_at=acknowledged_at,
        completed_at=completed_at,
        exit_code=exit_code,
        bounded_access_observed=True,
        audited_commands=commands,
        audited_write_paths=write_paths,
        audited_write_kinds=write_kinds,
    )


AgentRunner = Callable[[AgentRunRequest], AgentProcessObservation]


def _git_bytes(repository: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=repository, check=True, capture_output=True).stdout


def _git_mode(repository: Path, path: str) -> str:
    line = _git_bytes(repository, "ls-files", "-s", "--", path).decode().strip()
    return line.split(maxsplit=1)[0]


def _member_manifest(members: dict[str, bytes]) -> bytes:
    return _pretty(
        {
            "contract": "ace.code-intelligence.external-agent-archive-manifest/v1alpha1",
            "members": [
                {"path": path, "byte_count": len(payload), "sha256": _sha256(payload)}
                for path, payload in sorted(members.items())
            ],
        }
    )


def _deterministic_archive_bytes(members: dict[str, bytes]) -> bytes:
    members = dict(members)
    _validate_secret_free_members(members)
    members["archive-manifest.json"] = _member_manifest(members)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, payload in sorted(members.items()):
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                info.mtime = 0
                info.mode = 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _deterministic_archive(path: Path, members: dict[str, bytes]) -> None:
    _write(path, _deterministic_archive_bytes(members))


def verify_deterministic_archive(path: Path) -> dict[str, Any]:
    """Validate member safety, exact manifest digests, and byte replay."""

    encoded = path.read_bytes()
    with tarfile.open(fileobj=io.BytesIO(encoded), mode="r:gz") as archive:
        infos = archive.getmembers()
        names = [item.name for item in infos]
        if names != sorted(names) or len(names) != len(set(names)):
            raise AssertionError("external-agent archive names are duplicated or not sorted")
        if any(item.isdir() or item.issym() or item.islnk() or Path(item.name).is_absolute() for item in infos):
            raise AssertionError("external-agent archive contains a non-regular or absolute member")
        if any(".." in Path(item.name).parts for item in infos):
            raise AssertionError("external-agent archive contains path traversal")
        members = {item.name: archive.extractfile(item).read() for item in infos}
    _validate_secret_free_members(members)
    manifest = members.pop("archive-manifest.json", None)
    if manifest is None or manifest != _member_manifest(members):
        raise AssertionError("external-agent archive manifest differs from exact members")
    if encoded != _deterministic_archive_bytes(members):
        raise AssertionError("external-agent archive does not reproduce byte-for-byte")
    return {
        "byte_count": len(encoded),
        "sha256": _sha256(encoded),
        "member_count": len(members) + 1,
        "deterministic_replay": True,
    }


def _snapshot_scan_stats(snapshot: DurablePhase1IndexSnapshotV1Alpha1) -> dict[str, int]:
    return {
        "files": len(snapshot.phase1_state.files),
        "functions": sum(item.get("kind") != "class" for item in snapshot.phase1_state.symbols),
        "classes": sum(item.get("kind") == "class" for item in snapshot.phase1_state.symbols),
        "imports": len(snapshot.phase1_state.imports),
    }


def _validate_source_anchor(journey: CodeIntelligenceJourneyV1Alpha1, block: Any) -> None:
    anchors = [item for item in journey.lens.evidence if item.anchor_id == block.evidence_ref]
    if len(anchors) != 1:
        raise AssertionError("external-agent named source block lacks one exact source anchor")
    anchor = anchors[0]
    if (
        anchor.path != block.path
        or anchor.line_start != block.symbol_line_start
        or anchor.line_end != block.symbol_line_end
        or anchor.content_digest != block.symbol_body_digest
    ):
        raise AssertionError("external-agent source anchor differs from exact symbol coordinates")


def _validate_snapshot_symbol(snapshot: DurablePhase1IndexSnapshotV1Alpha1, block: Any) -> None:
    matches = [
        item
        for item in snapshot.phase1_state.symbols
        if item.get("file") == block.path
        and item.get("name") == block.symbol
        and int(item.get("line_start", 0)) == block.symbol_line_start
        and int(item.get("line_end", 0)) == block.symbol_line_end
    ]
    if len(matches) != 1:
        raise AssertionError("external-agent snapshot lacks one exact target symbol")


def _source_excerpt(body: str, block: Any) -> str:
    lines = body.splitlines()
    if block.line_end > len(lines):
        raise AssertionError("external-agent source block extends beyond exact file bytes")
    return "\n".join(lines[block.line_start - 1 : block.line_end])


def _source_coordinates(block: Any, file_digest: str) -> dict[str, Any]:
    return {
        "source_path": block.path,
        "source_file_digest": file_digest,
        "source_block_id": block.block_id,
        "source_body_digest": block.body_digest,
        "source_symbol": block.symbol,
        "source_line_start": block.line_start,
        "source_line_end": block.line_end,
        "source_symbol_line_start": block.symbol_line_start,
        "source_symbol_line_end": block.symbol_line_end,
    }


def replay_external_agent_archive(
    path: Path,
    *,
    expected_archive_sha256: str | None = None,
    expected_archive_byte_count: int | None = None,
    expected_replay_expectation: ExternalAgentReplayExpectationV1Alpha1 | None = None,
) -> dict[str, Any]:
    """Revalidate the complete external chain from only durable archive bytes."""

    archive_validation = verify_deterministic_archive(path)
    trust_fields = (
        expected_archive_sha256 is not None,
        expected_archive_byte_count is not None,
        expected_replay_expectation is not None,
    )
    if any(trust_fields) and not all(trust_fields):
        raise ValueError("archive digest, byte count, and replay expectation must be supplied together")
    authenticated = all(trust_fields)
    if authenticated and (
        archive_validation["sha256"] != expected_archive_sha256
        or archive_validation["byte_count"] != expected_archive_byte_count
    ):
        raise AssertionError("external-agent archive differs from paired machine evidence")
    with tarfile.open(path, mode="r:gz") as archive:
        members = {item.name: archive.extractfile(item).read() for item in archive.getmembers()}
    expected_members = {
        "archive-manifest.json",
        "control/live-handoff.json",
        "control/prompt.txt",
        "control/return.schema.json",
        "exchange/codex-return.json",
        "exchange/normalized-return.json",
        "exchange/return-receipt.json",
        "external-agent-replay-expectation.json",
        "external-agent-round-trip-raw.json",
        "logs/codex-events.jsonl",
        "logs/codex-invocation.json",
        "logs/codex-stderr.txt",
        "observations/after-pkg-service.py",
        "observations/before-pkg-service.py",
        "observations/change-set-receipt.json",
        "observations/change.patch",
        "observations/repository.diff",
        "observations/verification-stderr.bin",
        "observations/verification-stdout.bin",
        "observations/verification.json",
    }
    if set(members) != expected_members:
        raise AssertionError("external-agent archive has an unexpected exact member inventory")
    raw_member = members["external-agent-round-trip-raw.json"]
    raw = json.loads(raw_member)
    required_sections = {
        "evidence_contract",
        "accepted",
        "controller_run_id",
        "acceptance_run_id",
        "initial_journey",
        "initial_snapshot",
        "updated_snapshot",
        "old_snapshot",
        "post_restart_journey",
        "initial_capture",
        "acceptance_run",
        "audited_commands",
        "audited_write_paths",
        "incremental_update",
        "fresh_process_reopen",
        "immutable_history",
    }
    if set(raw) != required_sections:
        raise AssertionError("external-agent replay envelope has an unexpected section inventory")
    if raw["evidence_contract"] != "ace.code-intelligence.external-agent-round-trip-evidence/v1alpha1":
        raise AssertionError("external-agent replay envelope contract differs")
    if raw["accepted"] is not True:
        raise AssertionError("external-agent replay envelope is not accepted")
    journey = CodeIntelligenceJourneyV1Alpha1.model_validate(raw["initial_journey"])
    post_journey = CodeIntelligenceJourneyV1Alpha1.model_validate(raw["post_restart_journey"])
    initial_snapshot = DurablePhase1IndexSnapshotV1Alpha1.model_validate(raw["initial_snapshot"])
    updated_snapshot = DurablePhase1IndexSnapshotV1Alpha1.model_validate(raw["updated_snapshot"])
    old_snapshot = DurablePhase1IndexSnapshotV1Alpha1.model_validate(raw["old_snapshot"])
    accepted = ExternalCodingAgentAcceptanceRunV1Alpha1.model_validate(raw["acceptance_run"])
    expectation = ExternalAgentReplayExpectationV1Alpha1.model_validate_json(
        members["external-agent-replay-expectation.json"]
    )
    if expected_replay_expectation is not None and expectation != expected_replay_expectation:
        raise AssertionError("external-agent archive expectation differs from paired machine evidence")
    session_id, first_event_type, event_count, commands, write_paths, write_kinds, _ = derive_external_agent_transcript(
        members["logs/codex-events.jsonl"],
        Path(expectation.workspace_root),
        accepted.change_set.path,
        replay_macos_tmp_alias=True,
    )
    validate_external_coding_agent_acceptance(
        journey,
        accepted,
        transcript=members["logs/codex-events.jsonl"],
        invocation=members["logs/codex-invocation.json"],
        prompt=members["control/prompt.txt"],
        schema=members["control/return.schema.json"],
        output=members["exchange/codex-return.json"],
        normalized_return=members["exchange/normalized-return.json"],
        repository_diff=members["observations/repository.diff"],
        repository_root=Path(expectation.workspace_root),
        replay_macos_tmp_alias=True,
    )
    exact_contract_members = {
        "control/live-handoff.json": _pretty(journey.handoff),
        "exchange/return-receipt.json": _pretty(accepted.return_receipt),
        "observations/before-pkg-service.py": accepted.change_set.before_body.encode(),
        "observations/after-pkg-service.py": accepted.change_set.after_body.encode(),
        "observations/change.patch": accepted.change_set.patch.encode(),
        "observations/change-set-receipt.json": _pretty(accepted.change_set),
        "observations/verification.json": _pretty(accepted.verification),
    }
    for name, wanted in exact_contract_members.items():
        if members[name] != wanted:
            raise AssertionError(f"external-agent archive member differs from exact contract: {name}")
    if (
        _sha256(members["logs/codex-stderr.txt"]) != accepted.delivery.stderr_digest
        or len(members["logs/codex-stderr.txt"]) != accepted.delivery.stderr_byte_count
    ):
        raise AssertionError("external-agent stderr member differs from delivery")
    if (
        _sha256(members["observations/verification-stdout.bin"]) != accepted.verification.stdout_digest
        or _sha256(members["observations/verification-stderr.bin"]) != accepted.verification.stderr_digest
    ):
        raise AssertionError("external-agent verification streams differ from observation")
    if raw["acceptance_run_id"] != accepted.run_id or raw["controller_run_id"] != accepted.delivery.controller_run_id:
        raise AssertionError("external-agent archive names a different acceptance run")
    if raw["audited_commands"] != list(commands) or raw["audited_write_paths"] != list(write_paths):
        raise AssertionError("external-agent raw audit summaries differ from exact transcript")
    update = accepted.living_update
    if (
        initial_snapshot.generation != 1
        or initial_snapshot.parent_snapshot_id is not None
        or initial_snapshot.parent_snapshot_digest is not None
        or initial_snapshot.index != journey.lens.index
        or initial_snapshot.snapshot_id != accepted.initial_snapshot_id
        or initial_snapshot.repository_path != expectation.workspace_root
    ):
        raise AssertionError("external-agent initial snapshot differs from initial journey")
    if (
        updated_snapshot.generation != 2
        or updated_snapshot.repository_path != expectation.workspace_root
        or old_snapshot.repository_path != expectation.workspace_root
    ):
        raise AssertionError("external-agent updated snapshot is not generation two")
    if (
        updated_snapshot.parent_snapshot_id != initial_snapshot.snapshot_id
        or updated_snapshot.parent_snapshot_digest != initial_snapshot.snapshot_digest
    ):
        raise AssertionError("external-agent updated snapshot has a crossed parent")
    if old_snapshot != initial_snapshot:
        raise AssertionError("external-agent historical snapshot differs from exact generation one")
    if updated_snapshot.index != post_journey.lens.index:
        raise AssertionError("external-agent updated snapshot index differs from post-restart journey")
    if (
        update.initial_snapshot_id != initial_snapshot.snapshot_id
        or update.initial_snapshot_digest != initial_snapshot.snapshot_digest
        or update.updated_snapshot_id != updated_snapshot.snapshot_id
        or update.updated_snapshot_digest != updated_snapshot.snapshot_digest
        or update.old_snapshot_id != old_snapshot.snapshot_id
        or update.old_snapshot_digest != old_snapshot.snapshot_digest
    ):
        raise AssertionError("external-agent living update differs from exact snapshot envelope")
    initial_blocks = [
        block
        for block in journey.handoff.blocks
        if block.path == accepted.change_set.path and block.symbol == "transform"
    ]
    post_blocks = [
        block
        for block in post_journey.handoff.blocks
        if block.path == accepted.change_set.path and block.symbol == "transform"
    ]
    if len(initial_blocks) != 1 or len(post_blocks) != 1:
        raise AssertionError("external-agent snapshot journeys do not contain one exact target symbol block")
    initial_block, post_block = initial_blocks[0], post_blocks[0]
    before_excerpt = _source_excerpt(accepted.change_set.before_body, initial_block)
    after_excerpt = _source_excerpt(accepted.change_set.after_body, post_block)
    if initial_block.body != before_excerpt or post_block.body != after_excerpt:
        raise AssertionError("external-agent source blocks differ from exact before/after bytes")
    _validate_source_anchor(journey, initial_block)
    _validate_source_anchor(post_journey, post_block)
    _validate_snapshot_symbol(initial_snapshot, initial_block)
    _validate_snapshot_symbol(updated_snapshot, post_block)
    if (
        update.post_restart_index_id != post_journey.lens.index.index_id
        or update.post_restart_lens_id != post_journey.lens.lens_id
        or update.post_restart_source_block_id != post_block.block_id
        or update.post_restart_source_body_digest != post_block.body_digest
        or update.post_restart_source_file_digest != accepted.change_set.after_digest
        or update.post_restart_source_symbol != post_block.symbol
        or update.post_restart_symbol_line_start != post_block.symbol_line_start
        or update.post_restart_symbol_line_end != post_block.symbol_line_end
    ):
        raise AssertionError("external-agent post-restart journey differs from living update")

    initial_capture = {
        "snapshot_id": initial_snapshot.snapshot_id,
        "snapshot_digest": initial_snapshot.snapshot_digest,
        "generation": initial_snapshot.generation,
        "phase1_state_digest": initial_snapshot.phase1_state_digest,
        "index_id": journey.lens.index.index_id,
        "lens_id": journey.lens.lens_id,
        "manifest_id": journey.handoff.manifest.manifest_id,
        "handoff_id": journey.handoff.receipt.handoff_id,
        "scan_stats": _snapshot_scan_stats(initial_snapshot),
        **_source_coordinates(initial_block, accepted.change_set.before_digest),
    }
    if raw["initial_capture"] != initial_capture:
        raise AssertionError("external-agent initial-capture summary differs from full envelope")
    expected_incremental_stats = {
        "updated": len(accepted.change_set.changed_paths),
        "symbols_added": sum(
            item.get("file") in accepted.change_set.changed_paths for item in updated_snapshot.phase1_state.symbols
        ),
    }
    incremental_update = {
        "stats": expected_incremental_stats,
        "changed_paths": list(accepted.change_set.changed_paths),
        "snapshot_id": updated_snapshot.snapshot_id,
        "snapshot_digest": updated_snapshot.snapshot_digest,
        "generation": updated_snapshot.generation,
        "parent_snapshot_id": updated_snapshot.parent_snapshot_id,
        "parent_snapshot_digest": updated_snapshot.parent_snapshot_digest,
        "index_id": updated_snapshot.index_id,
        "lens_id": post_journey.lens.lens_id,
        "manifest_id": post_journey.handoff.manifest.manifest_id,
        "handoff_id": post_journey.handoff.receipt.handoff_id,
        **_source_coordinates(post_block, accepted.change_set.after_digest),
    }
    if raw["incremental_update"] != incremental_update:
        raise AssertionError("external-agent incremental-update summary differs from full envelope")
    reopened = {
        "fresh_python_process": True,
        "snapshot_id": updated_snapshot.snapshot_id,
        "snapshot_digest": updated_snapshot.snapshot_digest,
        "generation": updated_snapshot.generation,
        "index_id": updated_snapshot.index_id,
        "lens_id": post_journey.lens.lens_id,
        "manifest_id": post_journey.handoff.manifest.manifest_id,
        "handoff_id": post_journey.handoff.receipt.handoff_id,
        **_source_coordinates(post_block, accepted.change_set.after_digest),
        "journey": post_journey.model_dump(mode="json"),
        "full_rescan_permitted": False,
        "incremental_rescan_permitted": False,
        "provider_environment_present": False,
        "provider_import_permitted": False,
        "provider_invocation_permitted": False,
    }
    if raw["fresh_process_reopen"] != reopened:
        raise AssertionError("external-agent fresh-process summary differs from full envelope")
    if raw["fresh_process_reopen"]["journey"] != raw["post_restart_journey"]:
        raise AssertionError("external-agent fresh-process journey is crossed")
    if raw["immutable_history"] != {
        "snapshot_count": 2,
        "old_snapshot_still_readable": True,
        "old_snapshot_digest_unchanged": True,
    }:
        raise AssertionError("external-agent immutable-history summary differs from full envelope")
    rebuilt_expectation = ExternalAgentReplayExpectationV1Alpha1(
        raw_member_digest=_sha256(raw_member),
        invocation_digest=_sha256(members["logs/codex-invocation.json"]),
        invocation_byte_count=len(members["logs/codex-invocation.json"]),
        transcript_digest=_sha256(members["logs/codex-events.jsonl"]),
        workspace_root=expectation.workspace_root,
        target_path=accepted.change_set.path,
        audited_write_paths=write_paths,
        audited_write_kinds=write_kinds,
        acceptance_run_id=accepted.run_id,
        delivery_receipt_id=accepted.delivery.receipt_id,
        return_id=accepted.agent_return.return_id,
        return_receipt_id=accepted.return_receipt.receipt_id,
        change_set_receipt_id=accepted.change_set.receipt_id,
        verification_id=accepted.verification.verification_id,
        living_update_id=update.update_id,
        initial_snapshot_id=initial_snapshot.snapshot_id,
        initial_snapshot_digest=initial_snapshot.snapshot_digest,
        updated_snapshot_id=updated_snapshot.snapshot_id,
        updated_snapshot_digest=updated_snapshot.snapshot_digest,
        old_snapshot_id=old_snapshot.snapshot_id,
        old_snapshot_digest=old_snapshot.snapshot_digest,
        post_restart_index_id=post_journey.lens.index.index_id,
        post_restart_lens_id=post_journey.lens.lens_id,
        post_restart_source_block_id=post_block.block_id,
        post_restart_source_body_digest=post_block.body_digest,
        post_restart_source_file_digest=accepted.change_set.after_digest,
    )
    if expectation != rebuilt_expectation:
        raise AssertionError("external-agent replay expectation differs from recomputed machine coordinates")
    return {
        **archive_validation,
        "accepted": authenticated,
        "contract_validated": True,
        "trust_root_authenticated": authenticated,
        "acceptance_run_id": accepted.run_id,
        "delivery_receipt_id": accepted.delivery.receipt_id,
        "change_set_receipt_id": accepted.change_set.receipt_id,
        "verification_id": accepted.verification.verification_id,
        "living_update_id": accepted.living_update.update_id,
    }


def run_acceptance(
    work_root: Path,
    *,
    agent_runner: AgentRunner | None = None,
    allow_external_agent: bool = False,
    codex_executable: str = "codex",
    expected_version: str = _EXPECTED_VERSION,
    model: str = _MODEL,
    archive_path: Path | None = None,
) -> dict[str, Any]:
    """Run one acceptance chain, real or fake, against an injected or gated runner.

    The execution boundary lives here, not only in the CLI: an injected
    ``agent_runner`` (a fake/test double that cannot launch the external
    process) runs with no opt-in required. With no injected runner, a real
    Codex CLI process is only ever reached when the caller passes
    ``allow_external_agent=True`` explicitly -- checked here, before any
    repository, journey, or subprocess work begins -- and that opt-in is
    re-checked independently inside ``run_codex_exec`` itself, so a direct
    import of the real runner also fails closed by default.
    """

    if agent_runner is None:
        if not allow_external_agent:
            raise PermissionError(
                "run_acceptance requires either an injected agent_runner (for deterministic "
                "tests) or allow_external_agent=True to launch a real external coding-agent "
                "process (CLI: --allow-external-agent)."
            )

        def resolved_agent_runner(request: AgentRunRequest) -> AgentProcessObservation:
            return run_codex_exec(request, allow_external_agent=True)

    else:
        resolved_agent_runner = agent_runner

    repository = _make_repository(work_root)
    control = work_root / "control"
    exchange = work_root / "exchange"
    logs = work_root / "logs"
    observations = work_root / "observations"
    storage = work_root / "durable-index"
    for directory in (control, exchange, logs, observations):
        directory.mkdir(parents=True, exist_ok=True)

    builder = GraphBuilder(str(repository))
    initial_scan = builder.phase1_treesitter()
    journey = CodeIntelligenceJourney(repository, max_context_files=4, max_context_bytes=12_000).run(
        query=_QUERY,
        target_path=_TARGET,
        receiver_ref=_RECEIVER,
        builder=builder,
    )
    initial_source = _source_block(journey)
    store = DurablePhase1IndexStore(storage, repository)
    initial_snapshot = store.capture(builder, journey.lens.index, expected_generation=0)

    handoff_bytes = _pretty(journey.handoff)
    prepared_at = _utcnow()
    controller_run_id = _run_id(handoff_bytes, prepared_at)
    schema_bytes = _pretty(coding_agent_return_schema(journey))
    prompt_bytes = _prompt(journey, prepared_at)
    handoff_path = control / "live-handoff.json"
    schema_path = control / "return.schema.json"
    prompt_path = control / "prompt.txt"
    output_path = exchange / "codex-return.json"
    _write(handoff_path, handoff_bytes)
    _write(schema_path, schema_bytes)
    _write(prompt_path, prompt_bytes)

    target = repository / _TARGET
    before_bytes = target.read_bytes()
    before_head = Repo(repository).head.commit.hexsha
    before_index = (repository / ".git" / "index").read_bytes()
    before_mode = _git_mode(repository, _TARGET)
    initial_inventory = {
        path: _sha256((repository / path).read_bytes())
        for path in ("pkg/service.py", "pkg/consumer.py", "tests/test_service.py")
    }

    process_observation = resolved_agent_runner(
        AgentRunRequest(
            repository=repository,
            schema_path=schema_path,
            output_path=output_path,
            prompt=prompt_bytes,
            model=model,
            executable=codex_executable,
            expected_version=expected_version,
        )
    )
    invocation_bytes = _pretty(
        {
            "argv": list(process_observation.argv),
            "cli_version": process_observation.cli_version,
            "model": process_observation.model,
        }
    )
    validate_external_agent_invocation(
        invocation_bytes,
        executable=process_observation.executable,
        cli_version=process_observation.cli_version,
        model=process_observation.model,
        repository_root=repository,
    )
    _write(logs / "codex-events.jsonl", process_observation.transcript)
    _write(logs / "codex-stderr.txt", process_observation.stderr)
    _write(logs / "invocation.json", invocation_bytes)

    returned = CodingAgentReturnV1Alpha1.model_validate_json(process_observation.output)
    expected_blocks = tuple(block.block_id for block in journey.handoff.blocks)
    if returned.disposition != "change_proposed" or returned.changed_paths != (_TARGET,):
        raise AssertionError("Codex did not return the required exact one-path change")
    if returned.consumed_block_ids != expected_blocks:
        raise AssertionError("Codex did not report consuming the exact bounded block sequence")
    return_receipt = validate_coding_agent_return(journey.handoff, returned)
    normalized_return = _pretty(returned)
    _write(exchange / "normalized-return.json", normalized_return)
    _write(exchange / "return-receipt.json", _pretty(return_receipt))

    after_bytes = target.read_bytes()
    after_head = Repo(repository).head.commit.hexsha
    after_index = (repository / ".git" / "index").read_bytes()
    after_mode = _git_mode(repository, _TARGET)
    status = _git_bytes(repository, "status", "--porcelain=v1", "-z")
    changed_paths = tuple(
        path
        for path in _git_bytes(repository, "diff", "--name-only", "--diff-filter=ACDMRTUXB").decode().splitlines()
        if path
    )
    staged = _git_bytes(repository, "diff", "--cached", "--name-only")
    untracked = _git_bytes(repository, "ls-files", "--others", "--exclude-standard")
    repository_diff = _git_bytes(repository, "diff", "--binary", "--no-ext-diff", "--no-renames", "--", _TARGET)
    final_inventory = {
        path: _sha256((repository / path).read_bytes())
        for path in ("pkg/service.py", "pkg/consumer.py", "tests/test_service.py")
    }
    if changed_paths != returned.changed_paths or status != b" M pkg/service.py\0":
        raise AssertionError(f"repository change inventory differs from return: {status!r}, {changed_paths}")
    if staged or untracked or after_head != before_head or after_index != before_index:
        raise AssertionError("Codex staged, committed, added, or otherwise changed repository control state")
    if any(final_inventory[path] != digest for path, digest in initial_inventory.items() if path != _TARGET):
        raise AssertionError("Codex changed a source file outside the exact returned path")
    if target.is_symlink() or not repository_diff:
        raise AssertionError("Codex change is a symlink or has no exact patch bytes")

    before_body = before_bytes.decode("utf-8")
    after_body = after_bytes.decode("utf-8")
    patch_body = deterministic_code_patch(_TARGET, before_body, after_body)
    patch = patch_body.encode()

    change_set = CodeChangeSetReceiptV1Alpha1(
        controller_run_id=controller_run_id,
        return_id=returned.return_id,
        repository_revision_before=before_head,
        repository_revision_after=after_head,
        changed_paths=changed_paths,
        path=_TARGET,
        mode_before=before_mode,
        mode_after=after_mode,
        before_body=before_body,
        after_body=after_body,
        before_digest=_sha256(before_bytes),
        before_byte_count=len(before_bytes),
        after_digest=_sha256(after_bytes),
        after_byte_count=len(after_bytes),
        patch=patch_body,
        patch_digest=_sha256(patch),
        patch_byte_count=len(patch),
        repository_diff_digest=_sha256(repository_diff),
        repository_diff_byte_count=len(repository_diff),
        git_status_digest=_sha256(status),
        git_status_byte_count=len(status),
        observed_at=_utcnow(),
    )
    _write(observations / "before-pkg-service.py", before_bytes)
    _write(observations / "after-pkg-service.py", after_bytes)
    _write(observations / "change.patch", patch)
    _write(observations / "repository.diff", repository_diff)
    _write(observations / "change-set-receipt.json", _pretty(change_set))

    verification_command = (
        sys.executable,
        "-B",
        "-c",
        "from pkg.service import transform; assert transform(1) == 3",
    )
    completed = subprocess.run(verification_command, cwd=repository, capture_output=True, check=False)
    verification = ExternalCodeVerificationObservationV1Alpha1(
        observer_ref="ace-local-subprocess:independent-observer",
        return_id=returned.return_id,
        change_set_id=change_set.receipt_id,
        changed_paths=changed_paths,
        command=verification_command,
        status="passed" if completed.returncode == 0 else "failed",
        exit_code=completed.returncode,
        stdout_digest=_sha256(completed.stdout),
        stderr_digest=_sha256(completed.stderr),
        observed_at=_utcnow(),
    )
    _write(observations / "verification-stdout.bin", completed.stdout)
    _write(observations / "verification-stderr.bin", completed.stderr)
    _write(observations / "verification.json", _pretty(verification))
    if verification.status != "passed":
        raise AssertionError("independent verification did not observe the changed behavior")

    incremental_stats = builder.incremental_update(list(changed_paths))
    updated_index = CodeIntelligenceJourney(repository).index_identity(builder)
    updated_snapshot = store.capture(
        builder,
        updated_index,
        expected_generation=1,
        expected_parent_snapshot_id=initial_snapshot.snapshot_id,
        expected_parent_snapshot_digest=initial_snapshot.snapshot_digest,
    )
    restarted = _external_fresh_process_probe(
        repository=repository,
        storage=storage,
        expected_index=updated_index,
        expected_snapshot_id=updated_snapshot.snapshot_id,
        expected_snapshot_digest=updated_snapshot.snapshot_digest,
        exchange=exchange,
    )
    old_snapshot = store.read(
        initial_snapshot.snapshot_id,
        expected_index=journey.lens.index,
        expected_snapshot_digest=initial_snapshot.snapshot_digest,
    )
    inventory = store.list_snapshots()
    if incremental_stats.get("updated") != 1 or len(inventory) != 2:
        raise AssertionError("external-agent change did not produce exactly one generation-two update")

    living_update = CodeIntelligenceLivingUpdateV1Alpha1(
        return_id=returned.return_id,
        return_receipt_id=return_receipt.receipt_id,
        verification_id=verification.verification_id,
        mutation_id=change_set.receipt_id,
        changed_paths=changed_paths,
        before_source_digest=change_set.before_digest,
        after_source_digest=change_set.after_digest,
        patch_digest=change_set.patch_digest,
        initial_index_id=journey.lens.index.index_id,
        initial_lens_id=journey.lens.lens_id,
        initial_snapshot_id=initial_snapshot.snapshot_id,
        initial_snapshot_digest=initial_snapshot.snapshot_digest,
        updated_index_id=updated_snapshot.index_id,
        updated_snapshot_id=updated_snapshot.snapshot_id,
        updated_snapshot_digest=updated_snapshot.snapshot_digest,
        parent_snapshot_id=updated_snapshot.parent_snapshot_id,
        parent_snapshot_digest=updated_snapshot.parent_snapshot_digest,
        post_restart_index_id=restarted["index_id"],
        post_restart_lens_id=restarted["lens_id"],
        post_restart_source_block_id=restarted["source_block_id"],
        post_restart_source_body_digest=restarted["source_body_digest"],
        post_restart_source_path=restarted["source_path"],
        post_restart_source_file_digest=restarted["source_file_digest"],
        post_restart_source_symbol=restarted["source_symbol"],
        post_restart_symbol_line_start=restarted["source_symbol_line_start"],
        post_restart_symbol_line_end=restarted["source_symbol_line_end"],
        old_snapshot_id=old_snapshot.snapshot_id,
        old_snapshot_digest=old_snapshot.snapshot_digest,
        observed_at=_utcnow(),
    )
    delivery = ExternalCodingAgentDeliveryReceiptV1Alpha1(
        controller_run_id=controller_run_id,
        receiver_ref=_RECEIVER,
        handoff_id=journey.handoff.receipt.handoff_id,
        index_id=journey.lens.index.index_id,
        lens_id=journey.lens.lens_id,
        manifest_id=journey.handoff.manifest.manifest_id,
        return_id=returned.return_id,
        executable=process_observation.executable,
        cli_version=process_observation.cli_version,
        model=process_observation.model,
        session_id=process_observation.session_id,
        first_event_type=process_observation.first_event_type,
        event_count=process_observation.event_count,
        prompt_digest=_sha256(prompt_bytes),
        prompt_byte_count=len(prompt_bytes),
        schema_digest=_sha256(schema_bytes),
        schema_byte_count=len(schema_bytes),
        output_digest=_sha256(process_observation.output),
        output_byte_count=len(process_observation.output),
        normalized_return_digest=_sha256(normalized_return),
        normalized_return_byte_count=len(normalized_return),
        transcript_digest=_sha256(process_observation.transcript),
        transcript_byte_count=len(process_observation.transcript),
        stderr_digest=_sha256(process_observation.stderr),
        stderr_byte_count=len(process_observation.stderr),
        started_at=process_observation.started_at,
        acknowledged_at=process_observation.acknowledged_at,
        completed_at=process_observation.completed_at,
        exit_code=process_observation.exit_code,
        bounded_access_observed=process_observation.bounded_access_observed,
    )
    accepted = ExternalCodingAgentAcceptanceRunV1Alpha1(
        receiver_ref=_RECEIVER,
        initial_index_id=journey.lens.index.index_id,
        initial_lens_id=journey.lens.lens_id,
        initial_manifest_id=journey.handoff.manifest.manifest_id,
        initial_handoff_id=journey.handoff.receipt.handoff_id,
        initial_snapshot_id=initial_snapshot.snapshot_id,
        delivery=delivery,
        agent_return=returned,
        return_receipt=return_receipt,
        change_set=change_set,
        verification=verification,
        living_update=living_update,
        limitations=_LIMITATIONS,
    )
    validate_external_coding_agent_acceptance(
        journey,
        accepted,
        transcript=process_observation.transcript,
        invocation=invocation_bytes,
        prompt=prompt_bytes,
        schema=schema_bytes,
        output=process_observation.output,
        normalized_return=normalized_return,
        repository_diff=repository_diff,
        repository_root=repository,
    )

    result = {
        "evidence_contract": "ace.code-intelligence.external-agent-round-trip-evidence/v1alpha1",
        "accepted": True,
        "controller_run_id": controller_run_id,
        "acceptance_run_id": accepted.run_id,
        "initial_journey": journey.model_dump(mode="json"),
        "initial_snapshot": initial_snapshot.model_dump(mode="json"),
        "updated_snapshot": updated_snapshot.model_dump(mode="json"),
        "old_snapshot": old_snapshot.model_dump(mode="json"),
        "post_restart_journey": restarted["journey"],
        "initial_capture": {
            "snapshot_id": initial_snapshot.snapshot_id,
            "snapshot_digest": initial_snapshot.snapshot_digest,
            "generation": initial_snapshot.generation,
            "phase1_state_digest": initial_snapshot.phase1_state_digest,
            "index_id": journey.lens.index.index_id,
            "lens_id": journey.lens.lens_id,
            "manifest_id": journey.handoff.manifest.manifest_id,
            "handoff_id": journey.handoff.receipt.handoff_id,
            "scan_stats": initial_scan,
            **_source_coordinates(initial_source, change_set.before_digest),
        },
        "acceptance_run": accepted.model_dump(mode="json"),
        "audited_commands": list(process_observation.audited_commands),
        "audited_write_paths": list(process_observation.audited_write_paths),
        "incremental_update": {
            "stats": incremental_stats,
            "changed_paths": list(changed_paths),
            "snapshot_id": updated_snapshot.snapshot_id,
            "snapshot_digest": updated_snapshot.snapshot_digest,
            "generation": updated_snapshot.generation,
            "parent_snapshot_id": updated_snapshot.parent_snapshot_id,
            "parent_snapshot_digest": updated_snapshot.parent_snapshot_digest,
            "index_id": updated_snapshot.index_id,
            "lens_id": restarted["lens_id"],
            "manifest_id": restarted["manifest_id"],
            "handoff_id": restarted["handoff_id"],
            **_source_coordinates(
                _source_block(CodeIntelligenceJourneyV1Alpha1.model_validate(restarted["journey"])),
                change_set.after_digest,
            ),
        },
        "fresh_process_reopen": restarted,
        "immutable_history": {
            "snapshot_count": len(inventory),
            "old_snapshot_still_readable": True,
            "old_snapshot_digest_unchanged": old_snapshot.snapshot_digest == initial_snapshot.snapshot_digest,
        },
    }
    raw_result = _pretty(result)
    replay_expectation = ExternalAgentReplayExpectationV1Alpha1(
        raw_member_digest=_sha256(raw_result),
        invocation_digest=_sha256(invocation_bytes),
        invocation_byte_count=len(invocation_bytes),
        transcript_digest=_sha256(process_observation.transcript),
        workspace_root=str(repository.resolve()),
        target_path=_TARGET,
        audited_write_paths=process_observation.audited_write_paths,
        audited_write_kinds=process_observation.audited_write_kinds,
        acceptance_run_id=accepted.run_id,
        delivery_receipt_id=delivery.receipt_id,
        return_id=returned.return_id,
        return_receipt_id=return_receipt.receipt_id,
        change_set_receipt_id=change_set.receipt_id,
        verification_id=verification.verification_id,
        living_update_id=living_update.update_id,
        initial_snapshot_id=initial_snapshot.snapshot_id,
        initial_snapshot_digest=initial_snapshot.snapshot_digest,
        updated_snapshot_id=updated_snapshot.snapshot_id,
        updated_snapshot_digest=updated_snapshot.snapshot_digest,
        old_snapshot_id=old_snapshot.snapshot_id,
        old_snapshot_digest=old_snapshot.snapshot_digest,
        post_restart_index_id=restarted["index_id"],
        post_restart_lens_id=restarted["lens_id"],
        post_restart_source_block_id=restarted["source_block_id"],
        post_restart_source_body_digest=restarted["source_body_digest"],
        post_restart_source_file_digest=restarted["source_file_digest"],
    )
    members = {
        "external-agent-round-trip-raw.json": raw_result,
        "external-agent-replay-expectation.json": _pretty(replay_expectation),
        "control/live-handoff.json": handoff_bytes,
        "control/return.schema.json": schema_bytes,
        "control/prompt.txt": prompt_bytes,
        "exchange/codex-return.json": process_observation.output,
        "exchange/normalized-return.json": normalized_return,
        "exchange/return-receipt.json": _pretty(return_receipt),
        "logs/codex-events.jsonl": process_observation.transcript,
        "logs/codex-invocation.json": invocation_bytes,
        "logs/codex-stderr.txt": process_observation.stderr,
        "observations/before-pkg-service.py": before_bytes,
        "observations/after-pkg-service.py": after_bytes,
        "observations/change.patch": patch,
        "observations/repository.diff": repository_diff,
        "observations/change-set-receipt.json": _pretty(change_set),
        "observations/verification.json": _pretty(verification),
        "observations/verification-stdout.bin": completed.stdout,
        "observations/verification-stderr.bin": completed.stderr,
    }
    if archive_path is not None:
        _deterministic_archive(archive_path, members)
        archive_receipt = verify_deterministic_archive(archive_path)
        archive_validation = replay_external_agent_archive(
            archive_path,
            expected_archive_sha256=archive_receipt["sha256"],
            expected_archive_byte_count=archive_receipt["byte_count"],
            expected_replay_expectation=replay_expectation,
        )
        result["durable_archive"] = {
            "path": str(archive_path),
            **archive_validation,
        }
    return result


def repackage_external_agent_archive(
    source_archive: Path,
    work_root: Path,
    archive_path: Path,
) -> dict[str, Any]:
    """Close a successful immutable Codex event with the full replay envelope."""

    verify_deterministic_archive(source_archive)
    with tarfile.open(source_archive, mode="r:gz") as archive:
        members = {item.name: archive.extractfile(item).read() for item in archive.getmembers()}
    members.pop("archive-manifest.json")
    old_raw = json.loads(members["external-agent-round-trip-raw.json"])
    journey = CodeIntelligenceJourneyV1Alpha1.model_validate(old_raw["initial_journey"])
    accepted = ExternalCodingAgentAcceptanceRunV1Alpha1.model_validate(old_raw["acceptance_run"])
    original_acceptance_bytes = _pretty(accepted)
    repository = (work_root / "repository").resolve()
    storage = work_root / "durable-index"
    exchange = work_root / "exchange"
    store = DurablePhase1IndexStore(storage, repository)
    snapshots = store.list_snapshots()
    if len(snapshots) != 2 or [item.generation for item in snapshots] != [1, 2]:
        raise AssertionError("preserved external run does not contain exact generations one and two")
    initial_snapshot, updated_snapshot = snapshots
    old_snapshot = store.read(
        initial_snapshot.snapshot_id,
        expected_index=journey.lens.index,
        expected_snapshot_digest=initial_snapshot.snapshot_digest,
    )
    restarted = _external_fresh_process_probe(
        repository=repository,
        storage=storage,
        expected_index=updated_snapshot.index,
        expected_snapshot_id=updated_snapshot.snapshot_id,
        expected_snapshot_digest=updated_snapshot.snapshot_digest,
        exchange=exchange,
    )
    post_journey = CodeIntelligenceJourneyV1Alpha1.model_validate(restarted["journey"])
    initial_source = _source_block(journey)
    post_source = _source_block(post_journey)
    transcript = members["logs/codex-events.jsonl"]
    _, _, _, commands, write_paths, write_kinds, _ = derive_external_agent_transcript(
        transcript,
        repository,
        accepted.change_set.path,
    )
    preserved_invocation = json.loads((work_root / "logs" / "invocation.json").read_text())
    invocation_bytes = _pretty(
        {
            "argv": preserved_invocation["argv"],
            "cli_version": accepted.delivery.cli_version,
            "model": accepted.delivery.model,
        }
    )
    validate_external_agent_invocation(
        invocation_bytes,
        executable=accepted.delivery.executable,
        cli_version=accepted.delivery.cli_version,
        model=accepted.delivery.model,
        repository_root=repository,
    )
    members["logs/codex-invocation.json"] = invocation_bytes
    incremental_stats = {
        "updated": len(accepted.change_set.changed_paths),
        "symbols_added": sum(
            item.get("file") in accepted.change_set.changed_paths for item in updated_snapshot.phase1_state.symbols
        ),
    }
    result = {
        "evidence_contract": "ace.code-intelligence.external-agent-round-trip-evidence/v1alpha1",
        "accepted": True,
        "controller_run_id": accepted.delivery.controller_run_id,
        "acceptance_run_id": accepted.run_id,
        "initial_journey": journey.model_dump(mode="json"),
        "initial_snapshot": initial_snapshot.model_dump(mode="json"),
        "updated_snapshot": updated_snapshot.model_dump(mode="json"),
        "old_snapshot": old_snapshot.model_dump(mode="json"),
        "post_restart_journey": post_journey.model_dump(mode="json"),
        "initial_capture": {
            "snapshot_id": initial_snapshot.snapshot_id,
            "snapshot_digest": initial_snapshot.snapshot_digest,
            "generation": initial_snapshot.generation,
            "phase1_state_digest": initial_snapshot.phase1_state_digest,
            "index_id": journey.lens.index.index_id,
            "lens_id": journey.lens.lens_id,
            "manifest_id": journey.handoff.manifest.manifest_id,
            "handoff_id": journey.handoff.receipt.handoff_id,
            "scan_stats": _snapshot_scan_stats(initial_snapshot),
            **_source_coordinates(initial_source, accepted.change_set.before_digest),
        },
        "acceptance_run": accepted.model_dump(mode="json"),
        "audited_commands": list(commands),
        "audited_write_paths": list(write_paths),
        "incremental_update": {
            "stats": incremental_stats,
            "changed_paths": list(accepted.change_set.changed_paths),
            "snapshot_id": updated_snapshot.snapshot_id,
            "snapshot_digest": updated_snapshot.snapshot_digest,
            "generation": updated_snapshot.generation,
            "parent_snapshot_id": updated_snapshot.parent_snapshot_id,
            "parent_snapshot_digest": updated_snapshot.parent_snapshot_digest,
            "index_id": updated_snapshot.index_id,
            "lens_id": post_journey.lens.lens_id,
            "manifest_id": post_journey.handoff.manifest.manifest_id,
            "handoff_id": post_journey.handoff.receipt.handoff_id,
            **_source_coordinates(post_source, accepted.change_set.after_digest),
        },
        "fresh_process_reopen": restarted,
        "immutable_history": {
            "snapshot_count": 2,
            "old_snapshot_still_readable": True,
            "old_snapshot_digest_unchanged": old_snapshot.snapshot_digest == initial_snapshot.snapshot_digest,
        },
    }
    raw_result = _pretty(result)
    expectation = ExternalAgentReplayExpectationV1Alpha1(
        raw_member_digest=_sha256(raw_result),
        invocation_digest=_sha256(invocation_bytes),
        invocation_byte_count=len(invocation_bytes),
        transcript_digest=_sha256(transcript),
        workspace_root=str(repository),
        target_path=accepted.change_set.path,
        audited_write_paths=write_paths,
        audited_write_kinds=write_kinds,
        acceptance_run_id=accepted.run_id,
        delivery_receipt_id=accepted.delivery.receipt_id,
        return_id=accepted.agent_return.return_id,
        return_receipt_id=accepted.return_receipt.receipt_id,
        change_set_receipt_id=accepted.change_set.receipt_id,
        verification_id=accepted.verification.verification_id,
        living_update_id=accepted.living_update.update_id,
        initial_snapshot_id=initial_snapshot.snapshot_id,
        initial_snapshot_digest=initial_snapshot.snapshot_digest,
        updated_snapshot_id=updated_snapshot.snapshot_id,
        updated_snapshot_digest=updated_snapshot.snapshot_digest,
        old_snapshot_id=old_snapshot.snapshot_id,
        old_snapshot_digest=old_snapshot.snapshot_digest,
        post_restart_index_id=post_journey.lens.index.index_id,
        post_restart_lens_id=post_journey.lens.lens_id,
        post_restart_source_block_id=post_source.block_id,
        post_restart_source_body_digest=post_source.body_digest,
        post_restart_source_file_digest=accepted.change_set.after_digest,
    )
    if (
        _pretty(ExternalCodingAgentAcceptanceRunV1Alpha1.model_validate(result["acceptance_run"]))
        != original_acceptance_bytes
    ):
        raise AssertionError("repackaging changed the accepted external event")
    members["external-agent-round-trip-raw.json"] = raw_result
    members["external-agent-replay-expectation.json"] = _pretty(expectation)
    _deterministic_archive(archive_path, members)
    archive_receipt = verify_deterministic_archive(archive_path)
    replay = replay_external_agent_archive(
        archive_path,
        expected_archive_sha256=archive_receipt["sha256"],
        expected_archive_byte_count=archive_receipt["byte_count"],
        expected_replay_expectation=expectation,
    )
    result["durable_archive"] = {"path": str(archive_path), **replay}
    result["replay_expectation"] = expectation.model_dump(mode="json")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--expected-version", default=_EXPECTED_VERSION)
    parser.add_argument("--model", default=_MODEL)
    parser.add_argument(
        "--allow-external-agent",
        action="store_true",
        help="Required to invoke a real external coding-agent process or repackage a prior real run. "
        "Omitted by default; offline replay of an already-built archive never needs this flag.",
    )
    parser.add_argument(
        "--replay-archive",
        type=Path,
        help="Offline-only: revalidate an already-built deterministic archive and exit. "
        "Invokes no external process and requires no network.",
    )
    parser.add_argument("--reopen-probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--repository", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--storage", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-index", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-snapshot-id", help=argparse.SUPPRESS)
    parser.add_argument("--expected-snapshot-digest", help=argparse.SUPPRESS)
    parser.add_argument("--repackage-source", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.reopen_probe:
        required = (
            args.repository,
            args.storage,
            args.expected_index,
            args.expected_snapshot_id,
            args.expected_snapshot_digest,
        )
        if any(item is None for item in required):
            parser.error(
                "fresh reopen probe requires repository, storage, expected index, snapshot id, and snapshot digest"
            )
        print(json.dumps(_run_reopen_probe(args), sort_keys=True))
        return 0
    if args.replay_archive is not None:
        # Offline-only: revalidate already-built archive bytes. No codex, no network.
        print(json.dumps(replay_external_agent_archive(args.replay_archive), sort_keys=True, default=str))
        return 0
    if args.repackage_source is not None:
        if not args.allow_external_agent:
            parser.error("repackaging a prior real external-agent run requires --allow-external-agent")
        if args.output is None or args.archive is None or args.work_root is None:
            parser.error("repackaging requires --output, --archive, and --work-root")
        result = repackage_external_agent_archive(args.repackage_source, args.work_root, args.archive)
        _write(args.output, _pretty(result))
        print(json.dumps({"accepted": True, "run_id": result["acceptance_run_id"], **result["durable_archive"]}))
        return 0
    if args.output is None or args.archive is None:
        parser.error("--output and --archive are required for an external-agent acceptance run")
    if not args.allow_external_agent:
        parser.error(
            "invoking a real external coding-agent process requires --allow-external-agent; "
            "use --replay-archive for offline verification of an already-built archive"
        )
    temporary = tempfile.TemporaryDirectory(prefix="ace-code-external-") if args.work_root is None else None
    root = Path(temporary.name) if temporary is not None else args.work_root
    root.mkdir(parents=True, exist_ok=True)
    result = run_acceptance(
        root,
        allow_external_agent=True,
        codex_executable=args.codex_executable,
        expected_version=args.expected_version,
        model=args.model,
        archive_path=args.archive,
    )
    _write(args.output, _pretty(result))
    print(json.dumps({"accepted": True, "run_id": result["acceptance_run_id"], **result["durable_archive"]}))
    if temporary is not None:
        temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
