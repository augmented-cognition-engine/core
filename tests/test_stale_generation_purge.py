"""Item E — scanner skips the stale generation; purge script is dry-run by default.

The scanner had indexed BOTH an untracked stale `engine/` dir and the canonical `core/engine/`,
doubling the code graph. See docs/superpowers/specs/2026-06-22-stale-generation-graph-pollution-fix.md.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

# scripts/purge_stale_engine_graph.py is private tooling — not shipped in the
# public export (scripts/ allow-list is minimal). The dry-run test below
# imports it directly; the three _is_stale_generation_dir / _walk_repo tests
# above test shipped core.engine.scanner.scanner and must keep running.
_PURGE_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "purge_stale_engine_graph.py"
_HAS_PURGE_SCRIPT = _PURGE_SCRIPT.is_file()
_skip_no_purge_script = pytest.mark.skipif(
    not _HAS_PURGE_SCRIPT,
    reason="requires scripts/purge_stale_engine_graph.py (private tooling, not shipped in the public export)",
)


def _git_init_track(repo: str, track: list[str]) -> None:
    """Init a git repo and track only `track` paths — so untracked dirs (the stale generation) are
    distinguishable from the canonical tracked tree."""
    subprocess.run(["git", "init", "-q", repo], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "t@t.t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True, capture_output=True)
    for p in track:
        subprocess.run(["git", "-C", repo, "add", p], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "init"], check=True, capture_output=True)


def test_is_stale_generation_dir_skips_engine_keeps_portal(tmp_path):
    """A root-level dir with a core/<name> twin that is ALSO git-untracked is a stale generation ->
    skip. A twin-less dir (portal/) is kept; the tracked canonical core/engine is never at root."""
    from core.engine.scanner.scanner import _is_stale_generation_dir

    repo = str(tmp_path)
    for rel in ("core/engine", "engine", "portal"):
        os.makedirs(os.path.join(repo, rel))
    open(os.path.join(repo, "core/engine/keep.py"), "w").close()  # canonical, tracked
    open(os.path.join(repo, "engine/old.py"), "w").close()  # stale, untracked
    _git_init_track(repo, ["core/engine/keep.py"])  # engine/ + portal/ left untracked

    # stale duplicate generation at root, untracked -> skip
    assert _is_stale_generation_dir(repo, repo, "engine") is True
    # no core/portal twin -> keep (short-circuits before the git check)
    assert _is_stale_generation_dir(repo, repo, "portal") is False
    # the canonical core/engine is NOT at the repo root (dirpath != repo) -> never skipped
    assert _is_stale_generation_dir(repo, os.path.join(repo, "core"), "engine") is False


def test_tracked_twin_dir_is_not_skipped(tmp_path):
    """Safety on external repos: a root dir that has a core/ twin but is git-TRACKED (a legit
    canonical root) must NOT be dropped."""
    from core.engine.scanner.scanner import _is_stale_generation_dir

    repo = str(tmp_path)
    for rel in ("core/foo", "foo"):
        os.makedirs(os.path.join(repo, rel))
    open(os.path.join(repo, "core/foo/a.py"), "w").close()
    open(os.path.join(repo, "foo/b.py"), "w").close()
    _git_init_track(repo, ["core/foo/a.py", "foo/b.py"])  # foo/ IS tracked

    assert _is_stale_generation_dir(repo, repo, "foo") is False, "a tracked root dir must not be skipped"


def test_walk_repo_excludes_stale_engine(tmp_path):
    """End-to-end: _walk_repo indexes core/engine/ and portal/ but NOT the stale untracked engine/."""
    from core.engine.scanner.scanner import _walk_repo

    repo = str(tmp_path)
    for rel in ("core/engine/arms", "engine/arms", "portal/src"):
        os.makedirs(os.path.join(repo, rel), exist_ok=True)
    open(os.path.join(repo, "core/engine/arms/outcome.py"), "w").close()
    open(os.path.join(repo, "engine/arms/outcome.py"), "w").close()
    open(os.path.join(repo, "portal/src/App.tsx"), "w").close()
    _git_init_track(repo, ["core/engine/arms/outcome.py", "portal/src/App.tsx"])  # engine/ untracked

    paths = {f["path"] for f in _walk_repo(repo)}
    assert "core/engine/arms/outcome.py" in paths
    assert "portal/src/App.tsx" in paths
    assert "engine/arms/outcome.py" not in paths, "stale engine/ generation must not be indexed"


@_skip_no_purge_script
def test_purge_script_dry_run_by_default(monkeypatch):
    """The purge script must COUNT but never DELETE without --apply (destructive — user-gated)."""
    import asyncio

    import scripts.purge_stale_engine_graph as purge

    deletes: list = []

    class _DB:
        async def query(self, sql, params=None):
            u = sql.upper()
            if u.startswith("SELECT") and "COUNT" in u:
                return [{"count": 675}]
            if u.startswith("SELECT"):
                return [{"path": "engine/arms/outcome.py"}, {"path": "engine/capture/atomic.py"}]
            if u.startswith("DELETE"):
                deletes.append(sql)
            return []

    class _Pool:
        def connection(self):
            class _Ctx:
                async def __aenter__(self):
                    return _DB()

                async def __aexit__(self, *a):
                    return False

            return _Ctx()

    monkeypatch.setattr(purge, "_pool", lambda: _Pool(), raising=False)
    rc = asyncio.run(purge.run(apply=False, pool=_Pool()))
    assert rc == 0
    assert deletes == [], "dry-run must not issue any DELETE"
