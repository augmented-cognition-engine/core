"""System B behavioural proof: re-scanning the same repo must not duplicate scanner edges.

Covers all four scanner edge types (``imports`` via scoped clear; ``related_to``/``produced``/
``improves`` via dedup-on-write). The code-level test in ``test_scanner_edge_idempotency`` proves the
clearing logic; this proves the real build->persist->query loop against a live SurrealDB:

    surreal start --user root --pass root --bind 127.0.0.1:8100 memory
    SURREAL_URL=ws://localhost:8100 SURREAL_NS=ace_test SURREAL_DB=ace_test \
        python -m pytest tests/test_scanner_idempotency_live.py -q

Each test is hermetic: a unique graph id and unique fixture content (so commit hashes and decisions
never collide across tests), an edge-table clear, and a second scan that *genuinely reprocesses* (via
a new commit or a forced full re-scan) — so a pass reflects real convergence, not a trivial no-op.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from surrealdb import RecordID

from core.engine.core.db import parse_rows, pool
from core.engine.scanner.scanner import scan_repo

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _gid(tmp_path) -> str:
    # Unique per test invocation -> a fresh graph, so scan 1 is always a full scan and counts are
    # deterministic regardless of leftover state in the shared in-memory DB.
    return "idem_" + "".join(ch for ch in tmp_path.name if ch.isalnum())[:48]


def _patch_out_commit_classifier(monkeypatch) -> None:
    """The LLM commit-classifier shells out to the CLI, which the suite blocks; it is orthogonal to
    edge idempotency."""
    import core.engine.scanner.scanner as scanner_mod

    async def _no_classify(*args, **kwargs):
        return None

    monkeypatch.setattr(scanner_mod, "_classify_commit_decision", _no_classify)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _make_fixture_repo(root: Path) -> Path:
    repo = root / "fixture_repo"
    repo.mkdir()
    token = root.name  # unique per test → unique commit hashes/decisions, no cross-test collision
    (repo / "b.py").write_text(f"# {token}\ndef helper():\n    return 1\n")
    (repo / "a.py").write_text(f"from b import helper\n\n\n# {token}\ndef main():\n    return helper()\n")
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", f"{token}: initial")
    return repo


async def _count_imports() -> int:
    async with pool.connection() as db:
        rows = parse_rows(await db.query("SELECT count() AS c FROM imports GROUP ALL"))
        return rows[0]["c"] if rows else 0


async def _clear_imports() -> None:
    async with pool.connection() as db:
        await db.query("DELETE imports")


async def _count_related() -> int:
    async with pool.connection() as db:
        rows = parse_rows(await db.query("SELECT count() AS c FROM related_to GROUP ALL"))
        return rows[0]["c"] if rows else 0


async def _clear_related() -> None:
    async with pool.connection() as db:
        await db.query("DELETE related_to")


async def _count(table: str) -> int:
    async with pool.connection() as db:
        rows = parse_rows(await db.query(f"SELECT count() AS c FROM {table} GROUP ALL"))
        return rows[0]["c"] if rows else 0


async def _clear(table: str) -> None:
    async with pool.connection() as db:
        await db.query(f"DELETE {table}")


async def _force_full_rescan(graph_id: str) -> None:
    # Clear the last-scan marker so the next scan reprocesses everything (full, not incremental).
    async with pool.connection() as db:
        await db.query("UPDATE $rid SET scan_completed_at = NONE", {"rid": RecordID("graph", graph_id)})


def _make_cochange_repo(root: Path) -> Path:
    """A repo where a.py and b.py change together across 4 commits (co-change >= 3 → related_to)."""
    repo = root / "cochange_repo"
    repo.mkdir()
    token = root.name  # unique per test → unique commit hashes/decisions, no cross-test collision
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    for i in range(1, 5):
        (repo / "a.py").write_text(f"from b import helper\n\n# {token}\nx = {i}\n")
        (repo / "b.py").write_text(f"# {token}\ndef helper():\n    return {i}\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", f"{token}: commit {i} (a and b together)")
    return repo


async def test_rescan_reprocesses_without_duplicating_imports(tmp_path, monkeypatch):
    _patch_out_commit_classifier(monkeypatch)
    await pool.init()
    await _clear_imports()  # isolate from any leftover edges in the shared test DB
    gid = _gid(tmp_path)
    repo = _make_fixture_repo(tmp_path)

    await scan_repo(str(repo), graph_id=gid)
    after_first = await _count_imports()

    # Force a genuine reprocess: modify a.py (keep the import) and commit, so the second scan
    # actually rewrites the edge rather than taking the incremental no-change early return.
    (repo / "a.py").write_text("from b import helper\n\n\n# touched\ndef main():\n    return helper()\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "touch a (import unchanged)")

    second = await scan_repo(str(repo), graph_id=gid)
    after_second = await _count_imports()

    assert after_first >= 1, "expected at least one imports edge (a.py -> b.py)"
    assert second["imports_created"] >= 1, "second scan did not reprocess — test would be trivial"
    assert after_second == after_first, (
        f"re-scan duplicated edges: {after_first} -> {after_second} (idempotency regressed)"
    )


async def test_parse_failure_preserves_prior_imports(tmp_path, monkeypatch):
    # Regression (PR #240 review, finding 1): the imports clear must run only for files that parsed
    # this scan. A file that fails to parse on re-scan must keep its existing edges, not have them
    # deleted-and-not-rewritten.
    _patch_out_commit_classifier(monkeypatch)
    await pool.init()
    await _clear_imports()
    gid = _gid(tmp_path)
    repo = _make_fixture_repo(tmp_path)

    await scan_repo(str(repo), graph_id=gid)
    before = await _count_imports()
    assert before >= 1, "expected an imports edge from the first scan"

    # Make every file fail to parse on the next scan.
    import core.engine.scanner.scanner as scanner_mod

    def _boom(*args, **kwargs):
        raise ValueError("parse failure")

    monkeypatch.setattr(scanner_mod, "parse_file", _boom)

    await _force_full_rescan(gid)
    await scan_repo(str(repo), graph_id=gid)
    after = await _count_imports()

    assert after == before, f"parse failure deleted imports: {before} -> {after} (edge-loss regression)"


async def test_full_rescan_does_not_duplicate_related_to(tmp_path, monkeypatch):
    _patch_out_commit_classifier(monkeypatch)
    await pool.init()
    await _clear_related()  # isolate from any leftover edges in the shared test DB
    gid = _gid(tmp_path)
    repo = _make_cochange_repo(tmp_path)

    await scan_repo(str(repo), graph_id=gid)
    after_first = await _count_related()

    # Force a full re-scan: co-change is recomputed over all commits, so the related_to write is
    # definitely re-attempted — which is exactly what must NOT duplicate (create_edge dedups).
    await _force_full_rescan(gid)
    await scan_repo(str(repo), graph_id=gid)
    after_second = await _count_related()

    assert after_first >= 1, "expected at least one related_to edge (a.py <-> b.py co-change)"
    assert after_second == after_first, (
        f"full re-scan duplicated related_to edges: {after_first} -> {after_second} (idempotency regressed)"
    )


async def test_full_rescan_does_not_duplicate_commit_edges(tmp_path, monkeypatch):
    _patch_out_commit_classifier(monkeypatch)
    await pool.init()
    await _clear("produced")
    await _clear("improves")
    gid = _gid(tmp_path)
    repo = _make_cochange_repo(tmp_path)  # 4 commits -> decisions + produced + improves edges

    await scan_repo(str(repo), graph_id=gid)
    produced_first, improves_first = await _count("produced"), await _count("improves")

    await _force_full_rescan(gid)
    await scan_repo(str(repo), graph_id=gid)
    produced_second, improves_second = await _count("produced"), await _count("improves")

    assert produced_first >= 1 and improves_first >= 1, "expected produced/improves edges from commits"
    assert produced_second == produced_first, (
        f"full re-scan duplicated produced edges: {produced_first} -> {produced_second}"
    )
    assert improves_second == improves_first, (
        f"full re-scan duplicated improves edges: {improves_first} -> {improves_second}"
    )
