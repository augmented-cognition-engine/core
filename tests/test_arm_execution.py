from __future__ import annotations


def test_armresult_workspace_defaults_none_backward_compat():
    from core.engine.arms.base import ActionPlan, ArmResult

    # Existing callers construct ArmResult without a workspace → must default to None.
    r = ArmResult(plan=ActionPlan(summary="x"))
    assert r.workspace is None
    assert r.simulated is True  # existing default unchanged


def test_promotion_request_fields():
    from core.engine.arms.base import PromotionRequest

    pr = PromotionRequest(branch="arm/scaffold-abc", diff_summary="+1 -0", target="master")
    assert pr.branch == "arm/scaffold-abc"
    assert pr.target == "master"


def test_write_then_read_file_confined(tmp_path):
    from core.engine.arms.execution.executors import read_file, write_file

    write_file(str(tmp_path), {"path": "sub/a.txt", "content": "hi"})
    assert (tmp_path / "sub" / "a.txt").read_text() == "hi"
    assert read_file(str(tmp_path), {"path": "sub/a.txt"}) == "hi"


def test_write_file_rejects_dotdot_escape(tmp_path):
    import pytest

    from core.engine.arms.execution.executors import ExecutionError, write_file

    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(ExecutionError):
        write_file(str(ws), {"path": "../escape.txt", "content": "x"})
    assert not (tmp_path / "escape.txt").exists()


def test_write_file_rejects_symlink_escape(tmp_path):
    import os

    import pytest

    from core.engine.arms.execution.executors import ExecutionError, write_file

    outside = tmp_path / "outside"
    outside.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    os.symlink(str(outside), str(ws / "link"))  # ws/link -> outside
    with pytest.raises(ExecutionError):
        write_file(str(ws), {"path": "link/evil.txt", "content": "x"})
    assert not (outside / "evil.txt").exists()


def test_executor_registry_lookup():
    from core.engine.arms.execution.executors import get_executor

    assert get_executor("write_file") is not None
    assert get_executor("read_file") is not None
    assert get_executor("nonexistent_verb") is None


def test_write_file_rejects_absolute_path_escape(tmp_path):
    import pytest

    from core.engine.arms.execution.executors import ExecutionError, write_file

    ws = tmp_path / "ws"
    ws.mkdir()
    sentinel = tmp_path / "abs_target.txt"
    sentinel.write_text("original")
    with pytest.raises(ExecutionError):
        write_file(str(ws), {"path": str(sentinel), "content": "PWNED"})
    assert sentinel.read_text() == "original"  # absolute path must not overwrite


def test_write_file_rejects_prefix_sibling(tmp_path):
    # Guards the load-bearing `root + os.sep` in _confine: /tmp/ws vs /tmp/ws-evil.
    import pytest

    from core.engine.arms.execution.executors import ExecutionError, write_file

    ws = tmp_path / "ws"
    ws.mkdir()
    sibling = tmp_path / "ws-evil"
    sibling.mkdir()
    with pytest.raises(ExecutionError):
        write_file(str(ws), {"path": "../ws-evil/x.txt", "content": "x"})
    assert not (sibling / "x.txt").exists()


def test_write_file_rejects_file_symlink_overwrite(tmp_path):
    # The data-destruction case: overwrite-through a file symlink.
    import os

    import pytest

    from core.engine.arms.execution.executors import ExecutionError, write_file

    outside = tmp_path / "outside"
    outside.mkdir()
    real = outside / "real.txt"
    real.write_text("precious")
    ws = tmp_path / "ws"
    ws.mkdir()
    os.symlink(str(real), str(ws / "flink"))  # ws/flink -> outside/real.txt
    with pytest.raises(ExecutionError):
        write_file(str(ws), {"path": "flink", "content": "PWNED"})
    assert real.read_text() == "precious"  # not overwritten through the symlink


def test_write_file_rejects_ancestor_symlink_escape(tmp_path):
    import os

    import pytest

    from core.engine.arms.execution.executors import ExecutionError, write_file

    outside = tmp_path / "outside"
    outside.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    os.symlink(str(outside), str(ws / "d"))  # ws/d -> outside (ancestor symlink)
    with pytest.raises(ExecutionError):
        write_file(str(ws), {"path": "d/child.txt", "content": "x"})
    assert not (outside / "child.txt").exists()


def test_read_file_rejects_escape(tmp_path):
    # read_file shares _confine — the info-disclosure path must be blocked too.
    import pytest

    from core.engine.arms.execution.executors import ExecutionError, read_file

    ws = tmp_path / "ws"
    ws.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("topsecret")
    with pytest.raises(ExecutionError):
        read_file(str(ws), {"path": "../secret.txt"})


def _init_tmp_repo(path: str) -> None:
    import os
    import subprocess

    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "t"], check=True)
    with open(os.path.join(path, "f.txt"), "w") as fh:
        fh.write("seed\n")
    subprocess.run(["git", "-C", path, "add", "-A"], check=True)
    subprocess.run(["git", "-C", path, "commit", "-qm", "seed"], check=True)


def test_workspace_create_is_isolated_checkout(tmp_path):
    import os

    from core.engine.arms.execution.workspace import Workspace

    repo = str(tmp_path / "repo")
    _init_tmp_repo(repo)
    ws = Workspace.create(label="t", repo_root=repo)
    try:
        assert os.path.isdir(ws.path)  # the worktree exists
        assert "f.txt" in os.listdir(ws.path)  # it's a real checkout of the repo
        assert ".worktrees" in ws.path
    finally:
        ws.discard()


def test_workspace_discard_removes_worktree_and_branch(tmp_path):
    import os
    import subprocess

    from core.engine.arms.execution.workspace import Workspace

    repo = str(tmp_path / "repo")
    _init_tmp_repo(repo)
    ws = Workspace.create(label="t", repo_root=repo)
    branch = ws.branch
    ws.discard()
    assert not os.path.exists(ws.path)  # worktree gone
    branches = subprocess.run(["git", "-C", repo, "branch", "--list", branch], capture_output=True, text=True).stdout
    assert branch not in branches  # branch gone
    ws.discard()  # idempotent — no raise


def test_workspace_diff_and_promote_request_are_unperformed(tmp_path):
    import os

    from core.engine.arms.execution.workspace import Workspace

    repo = str(tmp_path / "repo")
    _init_tmp_repo(repo)
    ws = Workspace.create(label="t", repo_root=repo)
    try:
        with open(os.path.join(ws.path, "f.txt"), "a") as fh:
            fh.write("more\n")
        assert "more" in ws.diff()  # change visible in the worktree
        pr = ws.promote_request()
        assert pr.branch == ws.branch  # surfaced, NOT merged
        assert "more" not in open(os.path.join(repo, "f.txt")).read()  # main untouched
    finally:
        ws.discard()


import pytest


class _FakeWS:
    """run()/run_tests() only need .path — no git required for these unit tests."""

    def __init__(self, path):
        self.path = path


@pytest.mark.asyncio
async def test_runtime_performs_reversible_never_mutating(tmp_path):
    from core.engine.arms.base import Action, ActionPlan, RiskTier
    from core.engine.arms.execution.runtime import ExecutionRuntime

    plan = ActionPlan(
        summary="x",
        actions=[
            Action(verb="write_file", args={"path": "a.txt", "content": "hi"}, risk=RiskTier.REVERSIBLE),
            Action(verb="merge", args={}, risk=RiskTier.MUTATING),
        ],
    )
    result = await ExecutionRuntime().run(plan, _FakeWS(str(tmp_path)))

    assert result.simulated is False
    performed_verbs = [a.verb for a in result.performed]
    assert "write_file" in performed_verbs
    assert "merge" not in performed_verbs  # MUTATING never performed
    assert any("[gated] merge" in line for line in result.logs)
    assert (tmp_path / "a.txt").read_text() == "hi"  # the reversible write happened


@pytest.mark.asyncio
async def test_runtime_blocks_path_escape_nonfatal(tmp_path):
    from core.engine.arms.base import Action, ActionPlan, RiskTier
    from core.engine.arms.execution.runtime import ExecutionRuntime

    plan = ActionPlan(
        summary="x",
        actions=[
            Action(verb="write_file", args={"path": "../evil.txt", "content": "x"}, risk=RiskTier.REVERSIBLE),
        ],
    )
    result = await ExecutionRuntime().run(plan, _FakeWS(str(tmp_path)))
    assert result.performed == []  # nothing performed
    assert any("[blocked]" in line for line in result.logs)  # logged, did not raise
    assert not (tmp_path.parent / "evil.txt").exists()


@pytest.mark.asyncio
async def test_runtime_blocks_unknown_verb(tmp_path):
    from core.engine.arms.base import Action, ActionPlan, RiskTier
    from core.engine.arms.execution.runtime import ExecutionRuntime

    plan = ActionPlan(
        summary="x",
        actions=[
            Action(verb="frobnicate", args={}, risk=RiskTier.REVERSIBLE),
        ],
    )
    result = await ExecutionRuntime().run(plan, _FakeWS(str(tmp_path)))
    assert result.performed == []
    assert any("unknown verb" in line for line in result.logs)


@pytest.mark.asyncio
async def test_run_tests_pass_and_fail(tmp_path):
    from core.engine.arms.execution.runtime import ExecutionRuntime

    rt = ExecutionRuntime()
    ok, _ = await rt.run_tests(["true"], _FakeWS(str(tmp_path)))
    assert ok is True
    bad, _ = await rt.run_tests(["false"], _FakeWS(str(tmp_path)))
    assert bad is False


@pytest.mark.asyncio
async def test_scaffold_dispatch_writes_real_file_and_verifies(tmp_path, monkeypatch):
    import os

    from core.engine.arms.dispatch import dispatch_solution
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.scaffold_arm import ScaffoldArm  # noqa: F401 — ensures registration
    from core.engine.solution import Solution

    repo = str(tmp_path / "repo")
    _init_tmp_repo(repo)
    # Force workspaces to be created in the tmp repo (not the real ace repo).
    orig_create = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig_create(cls, label, repo))
    )

    sol = Solution(intent="scaffold a file", domain_hint="scaffold")
    out = await dispatch_solution(sol)
    assert out is not None
    domain, result, verdict = out

    assert domain == "scaffold"
    assert result.simulated is False  # REAL execution
    assert verdict.passed is True
    assert result.workspace is not None
    assert os.path.exists(os.path.join(result.workspace.path, "scaffold.txt"))  # real file in worktree
    assert not os.path.exists(os.path.join(repo, "scaffold.txt"))  # NOT in main tree

    result.workspace.discard()
