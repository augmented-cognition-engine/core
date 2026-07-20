"""Workspace.changed_files() — the clean file-path source for afferent `touches` edges (item D).

diff() text is truncated to 500 chars for diff_summary, so it can't be parsed for a full file list;
changed_files() runs `git diff --name-only` directly. Non-fatal: returns [] on error.
"""

from __future__ import annotations

import subprocess


def test_changed_files_parses_name_only(monkeypatch):
    from core.engine.arms.execution.workspace import Workspace

    ws = Workspace(path="/w", branch="b", repo_root="/r", created_by_runtime=True)

    class _Out:
        stdout = "engine/a.py\nengine/b.py\ntests/test_c.py\n"

    def fake_run(cmd, **kw):
        assert "diff" in cmd and "--name-only" in cmd
        return _Out()

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert ws.changed_files() == ["engine/a.py", "engine/b.py", "tests/test_c.py"]


def test_changed_files_empty_on_error(monkeypatch):
    from core.engine.arms.execution.workspace import Workspace

    ws = Workspace(path="/w", branch="b", repo_root="/r", created_by_runtime=True)

    def boom(cmd, **kw):
        raise subprocess.SubprocessError("git missing")

    monkeypatch.setattr(subprocess, "run", boom)
    assert ws.changed_files() == []


def test_changed_files_ignores_blank_lines(monkeypatch):
    from core.engine.arms.execution.workspace import Workspace

    ws = Workspace(path="/w", branch="b", repo_root="/r", created_by_runtime=True)

    class _Out:
        stdout = "engine/a.py\n\n\nengine/b.py\n"

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _Out())
    assert ws.changed_files() == ["engine/a.py", "engine/b.py"]
