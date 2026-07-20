"""`git diff` does not show untracked files — and arms mostly CREATE files.

This was silently wrong for as long as the execution layer has existed:

  - Workspace.diff() → the diff_summary on every action_outcome row was EMPTY for any build
    whose work was new files (a scaffold, a new module, a new component).
  - Workspace.changed_files() → the afferent `outcome_touches` edges MISSED every new file, so
    the graph's record of "what did this build touch" was systematically incomplete. A lying
    instrument: it looked like builds touched nothing.

It surfaced only when the adversarial critic — which reviews the DIFF — started refuting real
builds with "empty diff: nothing was actually changed". The critic was right.

Fix: `git add -N` (intent-to-add) the untracked files first, so git renders them in the diff
without staging their content. Scoped to the isolated worktree, which contains nothing but the
HEAD checkout and what the arm just wrote.
"""

from __future__ import annotations

import subprocess

import pytest


@pytest.fixture
def worktree(tmp_path):
    from core.engine.arms.execution.workspace import Workspace

    repo = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-q", repo], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
    (tmp_path / "repo" / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", repo, "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "seed"], check=True)
    ws = Workspace.create(label="difftest", repo_root=repo)
    yield ws
    try:
        ws.discard()
    except Exception:
        pass


def test_diff_shows_a_newly_created_file(worktree):
    """The case that matters: arms CREATE files. An empty diff here means the critic reviews
    nothing, the outcome records nothing, and the graph learns nothing."""
    from pathlib import Path

    Path(worktree.path, "brand_new.py").write_text("def hello():\n    return 'world'\n")

    diff = worktree.diff()

    assert "brand_new.py" in diff, "a newly created file MUST appear in the diff"
    assert "def hello" in diff, "the diff must carry the actual content, not just the filename"


def test_changed_files_includes_a_newly_created_file(worktree):
    """These paths become the outcome_touches edges. Missing new files = a graph that thinks
    builds touch nothing."""
    from pathlib import Path

    Path(worktree.path, "brand_new.py").write_text("x = 1\n")
    Path(worktree.path, "seed.txt").write_text("seed\nmodified\n")

    changed = worktree.changed_files()

    assert "brand_new.py" in changed, "a created file is a changed file"
    assert "seed.txt" in changed, "modified tracked files must still be reported"


def test_diff_is_empty_when_nothing_changed(worktree):
    """The guard must not manufacture a diff out of thin air — an untouched worktree is empty,
    and an arm that did nothing must still be caught doing nothing."""
    assert worktree.diff().strip() == ""
    assert worktree.changed_files() == []
