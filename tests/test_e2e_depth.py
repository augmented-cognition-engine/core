from __future__ import annotations

import os
import subprocess

import pytest


def _seed_repo(root):
    os.makedirs(root, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "t"], check=True)
    with open(os.path.join(root, ".gitignore"), "w") as fh:
        fh.write(".worktrees/\n")
    with open(os.path.join(root, "seed.txt"), "w") as fh:
        fh.write("seed\n")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "seed"], check=True)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_depth_varies_bugfix_vs_new_capability(db_pool, tmp_path, monkeypatch, no_adversarial_review):
    """A bug-fix profile skips ground_scan/explore; a new-capability profile runs them.
    Both build a real file via ace_build (stubbed brain) + ship via promote."""
    from core.engine.arms.code_arm import CodeArm
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.promotion import promote
    from core.engine.arms.registry import route
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.mcp.tools import ace_build
    from core.engine.solution import Solution

    PID = "product:platform"
    arm = next(a for a in route(Solution(intent="code", domain_hint="code")) if isinstance(a, CodeArm))

    ran = {"phases": []}

    async def codegen(i, r, c):
        return (
            [{"path": "out.py", "content": "def g():\n    return 7\n"}],
            ["python", "-c", "import out; assert out.g()==7"],
            ["import works"],
        )

    async def critic(c, ws):
        return True, []

    async def loader(i, product_id="product:platform"):
        return {}

    async def reasoner(i, c, product_id="product:platform"):
        return "r"

    monkeypatch.setattr(arm, "_codegen", codegen)
    monkeypatch.setattr(arm, "_critic", critic)
    monkeypatch.setattr(arm, "_load", loader)
    monkeypatch.setattr(arm, "_reason", reasoner)

    async def gs(s, p, ctx):
        ran["phases"].append("ground_scan")
        ctx["scan"] = {}
        return ctx

    async def ex(s, p, ctx):
        ran["phases"].append("explore")
        ctx["approach"] = "a"
        return ctx

    monkeypatch.setitem(arm.phase, "ground_scan", gs)
    monkeypatch.setitem(arm.phase, "explore", ex)

    repo = str(tmp_path / "repo")
    _seed_repo(repo)
    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )

    # Patch dispatch_solution's route() call so our pre-patched arm is always used
    import core.engine.arms.dispatch as _dispatch

    monkeypatch.setattr(_dispatch, "route", lambda solution: [arm])

    async def run_one(obj, profile):
        ran["phases"] = []

        async def classifier(solution, conversation, overrides):
            return profile

        monkeypatch.setattr(arm, "_classifier", classifier)

        async with pool.connection() as db:
            await db.query("DELETE agent_spec WHERE objective = $o", {"o": obj})
            created = parse_rows(
                await db.query(
                    "CREATE agent_spec SET product=$p, objective=$o, source='strategy_ingest', "
                    "acceptance_criteria=[], status='approved' RETURN id",
                    {"p": parse_record_id(PID), "o": obj},
                )
            )
        sid = str(created[0]["id"])
        out = await ace_build(sid, product_id=PID)
        assert out["built"] is True, out
        promoted = await promote(sid, product_id=PID, gate_cmd=["true"])
        assert promoted["promoted"] is True, promoted
        async with pool.connection() as db:
            await db.query("DELETE agent_spec WHERE objective=$o", {"o": obj})
            await db.query("DELETE action_outcome WHERE spec=$s", {"s": parse_record_id(sid)})
        return list(ran["phases"])

    bug = WorkProfile(scope="none", novelty="fix", risk="isolated", verify_depth="smoke")
    cap = WorkProfile(scope="module", novelty="extend", risk="connected", verify_depth="unit")

    bug_phases = await run_one("E2E_DEPTH bugfix", bug)
    cap_phases = await run_one("E2E_DEPTH newcap", cap)

    assert bug_phases == [], f"bug-fix should skip scan/explore, got {bug_phases}"
    assert "ground_scan" in cap_phases and "explore" in cap_phases, (
        f"new-capability should scan+explore, got {cap_phases}"
    )
