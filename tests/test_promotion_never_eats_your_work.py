"""Promotion would have destroyed uncommitted work that was never its to touch.

_merge_and_validate reverts a red gate like this:

    git reset --hard <pre_sha>
    git clean -fd            # "remove gate-created untracked files"

Both are aimed at undoing the MERGE. Neither can tell the merge's mess apart from YOURS. So on a
red gate, in a repo with uncommitted work — which this one ALWAYS has: a parallel session's edits,
standing untracked canvas/portal/docs directories — promotion silently:

  - reset --hard  : discards every modified tracked file
  - clean -fd     : deletes every untracked file and directory

It has never fired because promotion has never been run for real. "It never happened" is not a
safety property; it means nobody has pulled the pin yet.

So promotion REFUSES to run in a dirty tree. Not because merging is unsafe — a merge leaves
unrelated dirty files alone — but because the REVERT is unsafe, and you cannot know in advance
whether you will need it. A gate that might have to destroy your work to clean up after itself has
no business starting.
"""

from __future__ import annotations

import subprocess

from core.engine.arms.promotion import _merge_and_validate


def _repo(tmp_path) -> str:
    repo = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-q", "-b", "master", repo], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
    (tmp_path / "repo" / "mod.py").write_text("def a():\n    pass\n")
    subprocess.run(["git", "-C", repo, "add", "mod.py"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "seed"], check=True)
    # a real branch with real work on it
    subprocess.run(["git", "-C", repo, "checkout", "-q", "-b", "arm/real"], check=True)
    (tmp_path / "repo" / "mod.py").write_text('"""doc."""\n\ndef a():\n    pass\n')
    subprocess.run(["git", "-C", repo, "commit", "-qam", "work"], check=True)
    subprocess.run(["git", "-C", repo, "checkout", "-q", "master"], check=True)
    return repo


def test_promotion_refuses_to_run_with_MODIFIED_files_in_the_tree(tmp_path):
    """A red gate would `reset --hard` and throw them away."""
    repo = _repo(tmp_path)
    (tmp_path / "repo" / "mod.py").write_text("# somebody else is working on this\n")

    out = _merge_and_validate(repo, "arm/real", ["true"])  # the gate would PASS — the tree is the problem

    assert out["ok"] is False
    assert "uncommitted" in out["reason"].lower() or "dirty" in out["reason"].lower()
    assert (tmp_path / "repo" / "mod.py").read_text() == "# somebody else is working on this\n", (
        "and their work must be untouched"
    )


def test_promotion_refuses_to_run_with_UNTRACKED_files_in_the_tree(tmp_path):
    """A red gate would `clean -fd` and delete them. This repo permanently carries untracked WIP."""
    repo = _repo(tmp_path)
    (tmp_path / "repo" / "scratch").mkdir()
    (tmp_path / "repo" / "scratch" / "wip.py").write_text("hours of work\n")

    out = _merge_and_validate(repo, "arm/real", ["true"])

    assert out["ok"] is False
    assert "uncommitted" in out["reason"].lower() or "untracked" in out["reason"].lower()
    assert (tmp_path / "repo" / "scratch" / "wip.py").exists(), "their untracked work must survive"


def test_promotion_still_works_in_a_CLEAN_tree(tmp_path):
    """The guard must not block the thing promotion exists to do."""
    repo = _repo(tmp_path)

    out = _merge_and_validate(repo, "arm/real", ["true"])

    assert out["ok"] is True, out
    assert '"""doc."""' in (tmp_path / "repo" / "mod.py").read_text(), "the work must actually be merged"
