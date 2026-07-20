from __future__ import annotations

import os
import subprocess

import pytest


def _init_tmp_repo(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "t"], check=True)
    with open(os.path.join(path, "f.txt"), "w") as fh:
        fh.write("seed\n")
    subprocess.run(["git", "-C", path, "add", "-A"], check=True)
    subprocess.run(["git", "-C", path, "commit", "-qm", "seed"], check=True)


@pytest.mark.e2e
def test_workspace_write_is_isolated_then_reversed(tmp_path):
    """The core safety proof: a write lands in the worktree, never the main tree,
    and discard() leaves the main tree pristine."""
    from core.engine.arms.execution.executors import write_file
    from core.engine.arms.execution.workspace import Workspace

    repo = str(tmp_path / "repo")
    _init_tmp_repo(repo)
    ws = Workspace.create(label="e2e", repo_root=repo)

    write_file(ws.path, {"path": "new_artifact.txt", "content": "real work"})
    assert os.path.exists(os.path.join(ws.path, "new_artifact.txt"))  # in the worktree
    assert not os.path.exists(os.path.join(repo, "new_artifact.txt"))  # NOT in the main tree

    ws.discard()
    assert not os.path.exists(ws.path)  # worktree gone
    status = subprocess.run(["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True).stdout
    assert status.strip() == ""  # main tree pristine
    wt = subprocess.run(["git", "-C", repo, "worktree", "list"], capture_output=True, text=True).stdout
    assert ".worktrees" not in wt  # no orphan worktree


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_dispatch_failure_discards_no_orphan(tmp_path, monkeypatch, no_adversarial_review):
    """A failing verify discards the workspace — no orphaned worktree left behind."""
    from core.engine.arms.base import Action, ActionPlan, RiskTier
    from core.engine.arms.dispatch import dispatch_solution
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.scaffold_arm import ScaffoldArm  # ensures @register_arm registration
    from core.engine.solution import Solution

    repo = str(tmp_path / "repo")
    _init_tmp_repo(repo)
    orig_create = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig_create(cls, label, repo))
    )

    # Force verify to fail by making the arm's planned write escape confinement.
    async def bad_plan(self, solution):
        return ActionPlan(
            summary="bad",
            actions=[
                Action(verb="write_file", args={"path": "../escape.txt", "content": "x"}, risk=RiskTier.REVERSIBLE)
            ],
        )

    monkeypatch.setattr(ScaffoldArm, "plan", bad_plan)

    sol = Solution(intent="scaffold", domain_hint="scaffold")
    domain, result, verdict = await dispatch_solution(sol)

    assert verdict.passed is False  # escape blocked → verify fails
    wt = subprocess.run(["git", "-C", repo, "worktree", "list"], capture_output=True, text=True).stdout
    assert ".worktrees" not in wt  # discarded — no orphan
    assert not os.path.exists(os.path.join(repo, "escape.txt"))  # nothing escaped
