import os
import subprocess

import pytest

from core.engine.arms.dispatch import dispatch_solution
from core.engine.arms.scaffold_arm import ScaffoldArm
from core.engine.solution import Solution


@pytest.fixture
def tmp_arm_repo(tmp_path, monkeypatch):
    """Redirect Workspace.create into a throwaway git repo so arm execution never
    touches (or leaks a worktree into) the real ace repo."""
    from core.engine.arms.execution.workspace import Workspace

    repo = str(tmp_path / "repo")
    os.makedirs(repo)
    subprocess.run(["git", "init", "-q", repo], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
    with open(os.path.join(repo, "f.txt"), "w") as fh:
        fh.write("seed\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "seed"], check=True)

    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )
    return repo


async def test_scaffold_arm_plans_and_executes(tmp_arm_repo):
    arm = ScaffoldArm()
    sol = Solution(intent="create scaffold file notes.txt with body hello", domain_hint="scaffold")
    assert arm.can_handle(sol) is True
    plan = await arm.plan(sol)
    assert plan.actions and plan.actions[0].verb == "write_file"
    result = await arm.execute(plan)
    assert result.simulated is False and result.performed == plan.actions  # REAL now
    verdict = await arm.verify(result, plan)
    assert verdict.passed is True
    result.workspace.discard()  # no orphan


async def test_dispatch_runs_lifecycle_and_marks_solution(tmp_arm_repo):
    sol = Solution(intent="scaffold a file", domain_hint="scaffold")
    outcome = await dispatch_solution(sol)
    assert outcome is not None
    domain, result, verdict = outcome
    assert domain == "scaffold"
    assert verdict.passed is True
    assert sol.status == "verified"  # lifecycle advanced the Solution
    assert sol.outcome is result
    if result.workspace is not None:
        result.workspace.discard()  # kept on success → discard in test
    # best-effort cleanup of the harmless no-spec action_outcome row (skip if no DB)
    try:
        from core.engine.core.db import pool

        async with pool.connection() as db:
            await db.query("DELETE action_outcome WHERE intent = 'scaffold a file'")
    except Exception:
        pass


async def test_dispatch_no_handler_returns_none():
    sol = Solution(intent="something no arm handles", domain_hint="nonexistent-domain-xyz")
    # ScaffoldArm.can_handle checks domain_hint/intent; ensure neither matches:
    assert await dispatch_solution(sol) is None
    assert sol.status == "open"


async def test_dispatch_non_fatal_on_arm_error(monkeypatch):
    import core.engine.arms.dispatch as d

    async def boom(self, solution):
        raise RuntimeError("plan blew up")

    monkeypatch.setattr(ScaffoldArm, "plan", boom)
    sol = Solution(intent="scaffold", domain_hint="scaffold")
    domain, result, verdict = await d.dispatch_solution(sol)
    assert verdict.passed is False and "plan blew up" in verdict.reason
    assert sol.status == "failed"
