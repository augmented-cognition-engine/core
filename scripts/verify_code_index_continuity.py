"""Verify durable, provider-free continuity for the bounded phase-one code index.

The harness creates a small disposable Git repository, captures an initial Python
phase-one index, and reopens it in a fresh Python process with full scanning
disabled. It then changes exactly one file, applies the existing incremental
update path, captures an immutable child generation, and proves that the parent
generation remains readable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from contextlib import nullcontext
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

from core.engine.code_intelligence.contracts import RepositoryIndexIdentityV1Alpha1
from core.engine.code_intelligence.journey import CodeIntelligenceJourney
from core.engine.code_intelligence.snapshot_store import DurablePhase1IndexStore
from core.engine.intelligence.graph_builder import GraphBuilder

if (_PROJECT_ROOT / "core" / "engine" / "code_intelligence").is_dir():
    _origin = Path(sys.modules[DurablePhase1IndexStore.__module__].__file__).resolve()
    if _PROJECT_ROOT not in _origin.parents:
        raise RuntimeError(
            "verify_code_index_continuity imported "
            f"core.engine.code_intelligence.snapshot_store from {_origin}, not this checkout "
            f"({_PROJECT_ROOT}); refusing to run against a different package copy."
        )

_LIMITATIONS = (
    "Acceptance covers Python parsed by the phase-one Tree-sitter profile; other observed languages remain inventory-only.",
    "Static imports and symbols do not resolve runtime dispatch, reflection, generated code, monkey-patching, or dynamic imports.",
    "Incremental freshness depends on the caller supplying the exact changed-file set; this packet does not provide a watcher.",
    "Durability is a local single-repository snapshot contract, not replicated storage, backup, or disaster recovery.",
    "Reopening requires an exact repository index identity and does not claim that an old snapshot describes newer source.",
    "The writable snapshot cache does not self-authenticate; trusted reopening requires the exact snapshot id and digest the caller recorded outside it.",
)


def _make_repository(root: Path) -> Path:
    repository = root / "repository"
    (repository / "pkg").mkdir(parents=True)
    (repository / "tests").mkdir()
    (repository / "pkg" / "service.py").write_text(
        "def transform(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    (repository / "pkg" / "consumer.py").write_text(
        "from pkg.service import transform\n\ndef consume() -> int:\n    return transform(1)\n",
        encoding="utf-8",
    )
    (repository / "tests" / "test_service.py").write_text(
        "from pkg.service import transform\n\ndef test_transform():\n    assert transform(1) == 2\n",
        encoding="utf-8",
    )
    repo = Repo.init(repository)
    repo.index.add(["pkg/service.py", "pkg/consumer.py", "tests/test_service.py"])
    repo.index.commit("initial code intelligence fixture")
    return repository


def _index_identity(repository: Path, builder: GraphBuilder) -> RepositoryIndexIdentityV1Alpha1:
    # The journey owns the exact Git/working-tree identity algorithm used by the
    # Code lens. Reusing it avoids an acceptance-only identity approximation.
    return CodeIntelligenceJourney(repository).index_identity(builder)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fresh_process_probe(
    *,
    repository: Path,
    storage: Path,
    expected_index: RepositoryIndexIdentityV1Alpha1,
    expected_snapshot_id: str,
    expected_snapshot_digest: str,
    exchange: Path,
) -> dict[str, Any]:
    index_path = exchange / "expected-index.json"
    _write_json(index_path, expected_index.model_dump(mode="json"))
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
        raise AssertionError("fresh-process reopen attempted a full repository scan")

    with (
        patch.object(GraphBuilder, "phase1_treesitter", forbidden_scan),
        patch.object(GraphBuilder, "phase3_analyze", forbidden_scan),
    ):
        reopened = store.open_latest(
            expected_index=expected_index,
            expected_snapshot_id=args.expected_snapshot_id,
            expected_snapshot_digest=args.expected_snapshot_digest,
        )

    if reopened.snapshot.snapshot_id != args.expected_snapshot_id:
        raise AssertionError("fresh process reopened a different snapshot")
    if reopened.snapshot.index_id != expected_index.index_id:
        raise AssertionError("fresh process reopened a different index identity")
    return {
        "fresh_python_process": True,
        "snapshot_id": reopened.snapshot.snapshot_id,
        "index_id": reopened.snapshot.index_id,
        "generation": reopened.snapshot.generation,
        "file_count": len(reopened.builder.get_files()),
        "symbol_count": len(reopened.builder.get_symbols()),
        "import_count": len(reopened.builder.get_imports()),
        "full_rescan_permitted": False,
        "provider_environment_present": False,
        "provider_invocation_permitted": False,
    }


def run_acceptance(work_root: Path) -> dict[str, Any]:
    """Run the self-contained continuity acceptance journey under ``work_root``."""

    repository = _make_repository(work_root)
    storage = work_root / "durable-index"
    exchange = work_root / "exchange"
    exchange.mkdir()

    builder = GraphBuilder(str(repository))
    initial_scan = builder.phase1_treesitter()
    initial_index = _index_identity(repository, builder)
    store = DurablePhase1IndexStore(storage, repository)
    initial = store.capture(builder, initial_index, expected_generation=0)

    reopened = _fresh_process_probe(
        repository=repository,
        storage=storage,
        expected_index=initial_index,
        expected_snapshot_id=initial.snapshot_id,
        expected_snapshot_digest=initial.snapshot_digest,
        exchange=exchange,
    )

    changed_path = "pkg/service.py"
    (repository / changed_path).write_text(
        "def transform(value: int) -> int:\n"
        "    return value + 2\n\n"
        "def newly_observed() -> str:\n"
        "    return 'generation-two'\n",
        encoding="utf-8",
    )
    incremental_stats = builder.incremental_update([changed_path])
    updated_index = _index_identity(repository, builder)
    updated = store.capture(
        builder,
        updated_index,
        expected_generation=1,
        expected_parent_snapshot_id=initial.snapshot_id,
        expected_parent_snapshot_digest=initial.snapshot_digest,
    )

    old = store.read(
        initial.snapshot_id,
        expected_index=initial_index,
        expected_snapshot_digest=initial.snapshot_digest,
    )
    latest = store.open_latest(
        expected_index=updated_index,
        expected_snapshot_id=updated.snapshot_id,
        expected_snapshot_digest=updated.snapshot_digest,
    )
    inventory = store.list_snapshots()

    if incremental_stats["updated"] != 1:
        raise AssertionError("incremental update did not report exactly one updated file")
    if updated.generation != 2 or updated.parent_snapshot_id != initial.snapshot_id:
        raise AssertionError("generation two does not name its immutable parent")
    if updated.parent_snapshot_digest != initial.snapshot_digest:
        raise AssertionError("generation two parent digest does not match generation one")
    if old.snapshot_digest != initial.snapshot_digest or old.phase1_state_digest != initial.phase1_state_digest:
        raise AssertionError("generation one changed after generation two was captured")
    if latest.snapshot.snapshot_id != updated.snapshot_id:
        raise AssertionError("latest reopen did not return generation two")
    if any(item.execution_authority for item in inventory):
        raise AssertionError("a durable index snapshot unexpectedly grants execution authority")

    initial_symbols = {item["name"] for item in old.phase1_state.symbols}
    updated_symbols = {item["name"] for item in updated.phase1_state.symbols}
    if "newly_observed" in initial_symbols or "newly_observed" not in updated_symbols:
        raise AssertionError("old/new symbol states do not prove immutable incremental capture")

    return {
        "contract": "ace.code-intelligence.continuity-acceptance/v1alpha1",
        "accepted": True,
        "initial_capture": {
            "snapshot_id": initial.snapshot_id,
            "snapshot_digest": initial.snapshot_digest,
            "index_id": initial.index_id,
            "generation": initial.generation,
            "parent_snapshot_id": initial.parent_snapshot_id,
            "phase1_state_digest": initial.phase1_state_digest,
            "scan_stats": initial_scan,
        },
        "fresh_process_reopen": reopened,
        "incremental_update": {
            "changed_files": [changed_path],
            "stats": incremental_stats,
            "snapshot_id": updated.snapshot_id,
            "snapshot_digest": updated.snapshot_digest,
            "index_id": updated.index_id,
            "generation": updated.generation,
            "parent_snapshot_id": updated.parent_snapshot_id,
            "parent_snapshot_digest": updated.parent_snapshot_digest,
            "phase1_state_digest": updated.phase1_state_digest,
        },
        "immutable_history": {
            "snapshot_count": len(inventory),
            "old_snapshot_still_readable": True,
            "old_snapshot_digest_unchanged": old.snapshot_digest == initial.snapshot_digest,
            "old_symbol_absent": "newly_observed" not in initial_symbols,
            "new_symbol_present": "newly_observed" in updated_symbols,
        },
        "authority": {
            "provider_neutral": all(item.provider_neutral for item in inventory),
            "grants_source_authority": any(item.grants_source_authority for item in inventory),
            "grants_reasoning_authority": any(item.grants_reasoning_authority for item in inventory),
            "grants_delivery_authority": any(item.grants_delivery_authority for item in inventory),
            "grants_execution_authority": any(item.execution_authority for item in inventory),
            "grants_effect_authority": any(item.grants_effect_authority for item in inventory),
            "repository_revalidation_required": all(item.repository_revalidation_required for item in inventory),
        },
        "limitations": list(_LIMITATIONS),
    }


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
            parser.error("the internal reopen probe requires repository, storage, index, and snapshot arguments")
        payload = _run_reopen_probe(args)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="ace-code-index-continuity-") if args.work_root is None else None
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
