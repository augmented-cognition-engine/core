"""ACE built the code, verified it, passed the critic — and never committed it to its branch.

Build #7 succeeded. Then:

    branch arm/code-eb30adcb  ->  points at master's commit. No commit of ACE's work.
    worktree:  M core/engine/arms/registry.py          <- the change, uncommitted

The arm writes files into an isolated git worktree and NOTHING EVER COMMITS THEM. So the branch
carries no work, and promotion — which does `git merge <branch>` — would get "Already up to date",
exit 0, and report a SUCCESSFUL PROMOTION having merged nothing. The spec gets marked shipped. Zero
code ships.

That is this whole codebase's favourite bug in its purest form: a green success that delivers
nothing. Every gate passes, the ledger says verified, the human is congratulated, and the diff
evaporates.

Two things must be true, and they are different:
  - a verified build COMMITS its work, so the branch is a real, mergeable thing;
  - and promotion REFUSES a branch with nothing on it, rather than cheerfully merging the void.

The second matters even with the first fixed: fail closed, because the day the commit silently stops
happening again, promotion must be the thing that notices — not you, three weeks later, wondering
where the feature went.
"""

from __future__ import annotations

import subprocess

import pytest


def _repo(tmp_path) -> str:
    repo = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-q", "-b", "master", repo], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
    (tmp_path / "repo" / "mod.py").write_text("def a():\n    pass\n")
    subprocess.run(["git", "-C", repo, "add", "mod.py"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "seed"], check=True)
    return repo


def test_a_workspace_commits_its_changes_to_its_branch(tmp_path):
    """Without this the branch is empty and promotion merges nothing."""
    from core.engine.arms.execution.workspace import Workspace

    repo = _repo(tmp_path)
    ws = Workspace.create(label="code", repo_root=repo)
    try:
        # The arm writes into the worktree, exactly as ExecutionRuntime does.
        with open(f"{ws.path}/mod.py", "w") as f:
            f.write('"""A docstring."""\n\ndef a():\n    pass\n')
        with open(f"{ws.path}/new.py", "w") as f:
            f.write("x = 1\n")

        sha = ws.commit("code: add a docstring")

        assert sha, "commit() must return the new sha — there is no branch to merge without one"

        # The BRANCH must now actually carry the work: that is the whole point.
        diff = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only", f"master..{ws.branch}"],
            capture_output=True,
            text=True,
        ).stdout
        assert "mod.py" in diff, "the modified file must be ON the branch, not merely in the worktree"
        assert "new.py" in diff, "and so must a newly CREATED file (plain `git add` misses untracked)"
    finally:
        ws.discard()


def test_committing_nothing_is_honest_about_it(tmp_path):
    """An arm that changed nothing has nothing to commit — and must say so rather than fake a sha."""
    from core.engine.arms.execution.workspace import Workspace

    repo = _repo(tmp_path)
    ws = Workspace.create(label="code", repo_root=repo)
    try:
        assert ws.commit("nothing happened") is None, "no changes => no commit => None, not a lie"
    finally:
        ws.discard()


@pytest.mark.asyncio
async def test_a_verified_build_leaves_a_MERGEABLE_branch(tmp_path, monkeypatch):
    """End to end: dispatch a passing build and prove the branch is something promotion could merge.

    This is the check that would have caught it. Build #7 passed every gate it had — and left a
    branch with nothing on it.
    """
    import core.engine.arms.dispatch as dispatch
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.scaffold_arm import ScaffoldArm
    from core.engine.core.config import settings
    from core.engine.solution import Solution

    monkeypatch.setattr(settings, "arm_adversarial_review", False)
    repo = _repo(tmp_path)
    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )

    async def _choose(solution, llm=None, producer_only=False):
        return ScaffoldArm()

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch.router, "choose_arm", _choose)
    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    _d, result, verdict = await dispatch.dispatch_solution(Solution(intent="scaffold a file"))

    assert verdict.passed is True
    ws = result.workspace
    assert ws is not None

    diff = subprocess.run(
        ["git", "-C", repo, "diff", "--name-only", f"master..{ws.branch}"], capture_output=True, text=True
    ).stdout.strip()
    assert diff, (
        "a VERIFIED build must leave a branch with its work committed on it. Otherwise promotion "
        "runs `git merge`, is told 'Already up to date', exits 0, and reports success having "
        "shipped absolutely nothing."
    )
    ws.discard()


def test_promotion_REFUSES_a_branch_with_nothing_on_it(tmp_path):
    """Fail closed. `git merge` on an empty branch says "Already up to date" and exits 0 — so
    without this check, promotion reports success, marks the spec shipped, and ships nothing."""
    from core.engine.arms.promotion import _merge_and_validate

    repo = _repo(tmp_path)
    subprocess.run(["git", "-C", repo, "branch", "arm/empty"], check=True)  # a branch with no work

    out = _merge_and_validate(repo, "arm/empty", ["true"])  # gate would pass — the branch is the problem

    assert out["ok"] is False, "merging an empty branch must NOT be reported as a successful promotion"
    assert "nothing to promote" in out["reason"].lower()


def test_promotion_still_merges_a_branch_that_HAS_work(tmp_path):
    """And the guard must not block real promotions."""
    from core.engine.arms.promotion import _merge_and_validate

    repo = _repo(tmp_path)
    subprocess.run(["git", "-C", repo, "checkout", "-q", "-b", "arm/real"], check=True)
    (tmp_path / "repo" / "mod.py").write_text('"""doc."""\n\ndef a():\n    pass\n')
    subprocess.run(["git", "-C", repo, "commit", "-qam", "real work"], check=True)
    subprocess.run(["git", "-C", repo, "checkout", "-q", "master"], check=True)

    out = _merge_and_validate(repo, "arm/real", ["true"])

    assert out["ok"] is True, out
