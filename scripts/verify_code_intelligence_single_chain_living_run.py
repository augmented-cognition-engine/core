"""Verify one bounded Code Intelligence handoff-to-living-update chain.

The disposable journey uses one local Python repository. It captures an exact
initial lens and phase-one snapshot, validates a provider-neutral coding-agent
return, independently observes the returned change, appends generation two,
and reopens that child in a provider/rescan-forbidden fresh Python process.
"""

from __future__ import annotations

import argparse
import builtins
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
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
    CodeFileMutationObservationV1Alpha1,
    CodeIntelligenceLivingUpdateV1Alpha1,
    CodeIntelligenceReplayExpectationV1Alpha1,
    CodeIntelligenceSingleChainLivingRunV1Alpha1,
    CodeVerificationObservationV1Alpha1,
    CodingAgentReturnV1Alpha1,
    RepositoryIndexIdentityV1Alpha1,
    deterministic_code_patch,
    raw_digest,
)
from core.engine.code_intelligence.handoff import validate_coding_agent_return
from core.engine.code_intelligence.journey import CodeIntelligenceJourney
from core.engine.code_intelligence.living_run import (
    validate_single_chain_living_run,
    validate_single_chain_replay_envelope,
)
from core.engine.code_intelligence.snapshot_store import DurablePhase1IndexStore
from core.engine.intelligence.graph_builder import GraphBuilder

if (_PROJECT_ROOT / "core" / "engine" / "code_intelligence").is_dir():
    _origin = Path(sys.modules[DurablePhase1IndexStore.__module__].__file__).resolve()
    if _PROJECT_ROOT not in _origin.parents:
        raise RuntimeError(
            "verify_code_intelligence_single_chain_living_run imported "
            f"core.engine.code_intelligence.snapshot_store from {_origin}, not this checkout "
            f"({_PROJECT_ROOT}); refusing to run against a different package copy."
        )

_QUERY = "Change the named transform implementation and verify its observed behavior."
_TARGET = "pkg/service.py"
_RECEIVER = "coding-agent:provider-neutral"
_LIMITATIONS = (
    "Acceptance covers Python in one disposable local Git repository and one exact dirty-tree identity.",
    "The independently observed subprocess proves only the fixture behavior it executes.",
    "The caller supplies the exact changed-path set; this packet adds no watcher, LSP, compiler, or language profile.",
    "Provider and full-rescan paths are forbidden during fresh-process reopen; no coding provider is invoked.",
    "A deserialized verification observation and its output digests are structurally bound but do not self-authenticate command execution; verifier replay is required.",
    "Semantic return-receipt reconstruction excludes validated_at because replay is a new observation; paired archive validation separately requires the externally recorded exact receipt ID and validated_at.",
    "The exact before/after and deterministic patch material records a harness-applied local mutation, not coding-agent delivery or external effect.",
    "The local immutable snapshot chain is not deployment, backup, rollback, recovery UX, or production effect evidence.",
)
_PROVIDER_MODULES = frozenset(("anthropic", "openai", "google.generativeai", "mistralai"))


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _write_json(path: Path, value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_repository(work_root: Path) -> Path:
    repository = work_root / "repository"
    (repository / "pkg").mkdir(parents=True)
    (repository / "tests").mkdir()
    (repository / "pkg" / "service.py").write_text(
        "def helper(value: int) -> int:\n"
        "    return value\n\n"
        "def transform(value: int) -> int:\n"
        "    adjusted = helper(value)\n"
        "    return adjusted + 1\n",
        encoding="utf-8",
    )
    (repository / "pkg" / "consumer.py").write_text(
        "from pkg.service import transform\n\ndef consume() -> int:\n    return transform(1)\n",
        encoding="utf-8",
    )
    (repository / "tests" / "test_service.py").write_text(
        "from pkg.service import transform\n\nassert transform(1) == 3\n",
        encoding="utf-8",
    )
    repo = Repo.init(repository)
    repo.index.add(["pkg/service.py", "pkg/consumer.py", "tests/test_service.py"])
    repo.index.commit("initial bounded code fixture")
    return repository


def _source_block(journey: Any) -> Any:
    matches = [block for block in journey.handoff.blocks if block.path == _TARGET and block.symbol == "transform"]
    if len(matches) != 1:
        raise AssertionError("handoff does not contain exactly one named transform source block")
    block = matches[0]
    if "def transform" not in block.body or "return adjusted" not in block.body:
        raise AssertionError("named transform block does not contain its exact implementation span")
    return block


def _fresh_process_probe(
    *,
    repository: Path,
    storage: Path,
    expected_index: RepositoryIndexIdentityV1Alpha1,
    expected_snapshot_id: str,
    expected_snapshot_digest: str,
    exchange: Path,
) -> dict[str, Any]:
    index_path = exchange / "updated-index.json"
    _write_json(index_path, expected_index)
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
        raise AssertionError("fresh-process living reopen attempted repository analysis")

    original_import = builtins.__import__

    def forbid_provider_import(name: str, *import_args: Any, **import_kwargs: Any) -> Any:
        if any(name == provider or name.startswith(provider + ".") for provider in _PROVIDER_MODULES):
            raise AssertionError(f"fresh-process living reopen attempted provider import: {name}")
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
        raise AssertionError("fresh process reopened a different generation-two snapshot")
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
        "source_symbol": block.symbol,
        "source_symbol_line_start": block.symbol_line_start,
        "source_symbol_line_end": block.symbol_line_end,
        "source_line_start": block.line_start,
        "source_line_end": block.line_end,
        "full_rescan_permitted": False,
        "incremental_rescan_permitted": False,
        "provider_environment_present": False,
        "provider_import_permitted": False,
        "provider_invocation_permitted": False,
        "journey": journey.model_dump(mode="json"),
    }


def run_acceptance(work_root: Path) -> dict[str, Any]:
    """Execute and validate the complete disposable living-run packet."""

    repository = _make_repository(work_root)
    storage = work_root / "durable-index"
    exchange = work_root / "exchange"
    exchange.mkdir()

    builder = GraphBuilder(str(repository))
    initial_scan = builder.phase1_treesitter()
    journey_builder = CodeIntelligenceJourney(repository, max_context_files=4, max_context_bytes=12_000)
    initial_journey = journey_builder.run(
        query=_QUERY,
        target_path=_TARGET,
        receiver_ref=_RECEIVER,
        builder=builder,
    )
    initial_source = _source_block(initial_journey)
    before_body = (repository / _TARGET).read_text(encoding="utf-8")
    store = DurablePhase1IndexStore(storage, repository)
    initial_snapshot = store.capture(builder, initial_journey.lens.index, expected_generation=0)

    returned = CodingAgentReturnV1Alpha1(
        receiver_ref=_RECEIVER,
        handoff_id=initial_journey.handoff.receipt.handoff_id,
        index_id=initial_journey.lens.index.index_id,
        lens_id=initial_journey.lens.lens_id,
        manifest_id=initial_journey.handoff.manifest.manifest_id,
        disposition="change_proposed",
        summary="Increment transform by two while preserving the helper call, then observe the fixture assertion.",
        consumed_block_ids=tuple(block.block_id for block in initial_journey.handoff.blocks),
        changed_paths=(_TARGET,),
        verification_refs=("coding-agent-claim:python tests/test_service.py",),
        uncertainties=("The fixture does not resolve runtime dispatch or external consumers.",),
        submitted_at=datetime.now(timezone.utc),
    )
    return_receipt = validate_coding_agent_return(initial_journey.handoff, returned)

    after_body = (
        "def helper(value: int) -> int:\n"
        "    return value\n\n"
        "def transform(value: int) -> int:\n"
        "    adjusted = helper(value)\n"
        "    return adjusted + 2\n"
    )
    (repository / _TARGET).write_text(after_body, encoding="utf-8")
    observed_changed_paths = tuple(
        sorted(
            path for path in Repo(repository).git.diff("--name-only", "--diff-filter=ACDMRTUXB").splitlines() if path
        )
    )
    if observed_changed_paths != returned.changed_paths:
        raise AssertionError(
            f"repository-observed changed paths differ from coding-agent return: {observed_changed_paths}"
        )
    patch_body = deterministic_code_patch(_TARGET, before_body, after_body)
    mutation = CodeFileMutationObservationV1Alpha1(
        path=_TARGET,
        before_body=before_body,
        after_body=after_body,
        before_byte_count=len(before_body.encode()),
        after_byte_count=len(after_body.encode()),
        before_digest=raw_digest(before_body),
        after_digest=raw_digest(after_body),
        patch=patch_body,
        patch_byte_count=len(patch_body.encode()),
        patch_digest=raw_digest(patch_body),
    )
    verification_command = (
        sys.executable,
        "-c",
        "from pkg.service import transform; assert transform(1) == 3",
    )
    completed = subprocess.run(
        verification_command,
        cwd=repository,
        capture_output=True,
        check=False,
    )
    verification = CodeVerificationObservationV1Alpha1(
        observer_ref="ace-local-subprocess:independent-observer",
        return_id=returned.return_id,
        changed_paths=observed_changed_paths,
        mutation=mutation,
        command=verification_command,
        status="passed" if completed.returncode == 0 else "failed",
        exit_code=completed.returncode,
        stdout_digest=_sha256(completed.stdout),
        stderr_digest=_sha256(completed.stderr),
        observed_at=datetime.now(timezone.utc),
    )
    if verification.status != "passed":
        raise AssertionError("independently observed fixture verification failed")

    incremental_stats = builder.incremental_update(list(observed_changed_paths))
    updated_index = CodeIntelligenceJourney(repository).index_identity(builder)
    updated_snapshot = store.capture(
        builder,
        updated_index,
        expected_generation=1,
        expected_parent_snapshot_id=initial_snapshot.snapshot_id,
        expected_parent_snapshot_digest=initial_snapshot.snapshot_digest,
    )
    restarted = _fresh_process_probe(
        repository=repository,
        storage=storage,
        expected_index=updated_index,
        expected_snapshot_id=updated_snapshot.snapshot_id,
        expected_snapshot_digest=updated_snapshot.snapshot_digest,
        exchange=exchange,
    )
    old_snapshot = store.read(
        initial_snapshot.snapshot_id,
        expected_index=initial_journey.lens.index,
        expected_snapshot_digest=initial_snapshot.snapshot_digest,
    )
    inventory = store.list_snapshots()

    if incremental_stats.get("updated") != 1:
        raise AssertionError(f"unexpected exact incremental update stats: {incremental_stats}")
    if updated_snapshot.parent_snapshot_id != initial_snapshot.snapshot_id:
        raise AssertionError("generation two does not name generation one as parent")
    if updated_snapshot.parent_snapshot_digest != initial_snapshot.snapshot_digest:
        raise AssertionError("generation two parent digest differs from generation one")
    if old_snapshot.snapshot_digest != initial_snapshot.snapshot_digest:
        raise AssertionError("generation one changed after the living update")
    if len(inventory) != 2:
        raise AssertionError("living update did not preserve exactly two immutable generations")

    update = CodeIntelligenceLivingUpdateV1Alpha1(
        return_id=returned.return_id,
        return_receipt_id=return_receipt.receipt_id,
        verification_id=verification.verification_id,
        mutation_id=mutation.mutation_id,
        changed_paths=returned.changed_paths,
        before_source_digest=mutation.before_digest,
        after_source_digest=mutation.after_digest,
        patch_digest=mutation.patch_digest,
        initial_index_id=initial_journey.lens.index.index_id,
        initial_lens_id=initial_journey.lens.lens_id,
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
        observed_at=datetime.now(timezone.utc),
    )
    run = CodeIntelligenceSingleChainLivingRunV1Alpha1(
        receiver_ref=_RECEIVER,
        initial_index_id=initial_journey.lens.index.index_id,
        initial_lens_id=initial_journey.lens.lens_id,
        initial_manifest_id=initial_journey.handoff.manifest.manifest_id,
        initial_handoff_id=initial_journey.handoff.receipt.handoff_id,
        initial_snapshot_id=initial_snapshot.snapshot_id,
        agent_return=returned,
        return_receipt=return_receipt,
        verification=verification,
        living_update=update,
        limitations=_LIMITATIONS,
    )
    validate_single_chain_living_run(initial_journey, run)

    payload = {
        "evidence_contract": "ace.code-intelligence.single-chain-living-run-evidence/v1alpha1",
        "accepted": True,
        "run_id": run.run_id,
        "identities": {
            "return_id": returned.return_id,
            "return_receipt_id": return_receipt.receipt_id,
            "verification_id": verification.verification_id,
            "living_update_id": update.update_id,
            "mutation_id": mutation.mutation_id,
        },
        "initial_journey": initial_journey.model_dump(mode="json"),
        "initial_snapshot": initial_snapshot.model_dump(mode="json"),
        "updated_snapshot": updated_snapshot.model_dump(mode="json"),
        "old_snapshot": old_snapshot.model_dump(mode="json"),
        "initial_capture": {
            "snapshot_id": initial_snapshot.snapshot_id,
            "snapshot_digest": initial_snapshot.snapshot_digest,
            "generation": initial_snapshot.generation,
            "phase1_state_digest": initial_snapshot.phase1_state_digest,
            "scan_stats": initial_scan,
            "source_block_id": initial_source.block_id,
            "source_body_digest": initial_source.body_digest,
            "source_symbol": initial_source.symbol,
            "context_span": [initial_source.line_start, initial_source.line_end],
            "symbol_span": [initial_source.symbol_line_start, initial_source.symbol_line_end],
        },
        "run": run.model_dump(mode="json"),
        "incremental_update": {
            "stats": incremental_stats,
            "changed_paths": list(returned.changed_paths),
        },
        "fresh_process_reopen": restarted,
        "immutable_history": {
            "snapshot_count": len(inventory),
            "old_snapshot_still_readable": True,
            "old_snapshot_digest_unchanged": old_snapshot.snapshot_digest == initial_snapshot.snapshot_digest,
        },
    }
    raw_payload = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    expectation = CodeIntelligenceReplayExpectationV1Alpha1(
        raw_member_digest=raw_digest(raw_payload),
        run_id=run.run_id,
        return_receipt_id=return_receipt.receipt_id,
        return_receipt_validated_at=return_receipt.validated_at,
        initial_snapshot_id=initial_snapshot.snapshot_id,
        initial_snapshot_digest=initial_snapshot.snapshot_digest,
        updated_snapshot_id=updated_snapshot.snapshot_id,
        updated_snapshot_digest=updated_snapshot.snapshot_digest,
        post_restart_lens_id=restarted["lens_id"],
    )
    validate_single_chain_replay_envelope(raw_payload, expectation)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--reopen-probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--repository", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--storage", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-index", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-snapshot-id", help=argparse.SUPPRESS)
    parser.add_argument("--expected-snapshot-digest", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.reopen_probe:
        if not all(
            (
                args.repository,
                args.storage,
                args.expected_index,
                args.expected_snapshot_id,
                args.expected_snapshot_digest,
            )
        ):
            parser.error("internal reopen probe requires repository, storage, index, and snapshot")
        payload = _run_reopen_probe(args)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="ace-code-single-chain-") if args.work_root is None else None
        context = temporary if temporary is not None else nullcontext(str(args.work_root))
        with context as root:
            work_root = Path(root)
            work_root.mkdir(parents=True, exist_ok=True)
            payload = run_acceptance(work_root)

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
