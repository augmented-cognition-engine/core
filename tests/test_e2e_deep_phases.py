# tests/test_e2e_deep_phases.py
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
async def test_greenfield_runs_architect_systemic_runs_foresight(db_pool, tmp_path, monkeypatch, no_adversarial_review):
    from core.engine.arms.code_arm import CodeArm
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.mcp.tools import ace_build

    PID = "product:platform"
    arm = CodeArm()
    ran = {"phases": []}

    async def codegen(i, r, c):
        return (
            [{"path": "out.py", "content": "def g():\n    return 7\n"}],
            ["python", "-c", "import out; assert out.g()==7"],
            ["ok"],
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

    async def arch(s, p, ctx):
        ran["phases"].append("architect")
        ctx["architecture"] = "A"
        return ctx

    async def fore(s, p, ctx):
        ran["phases"].append("foresight")
        ctx["foresight"] = "F"
        return ctx

    monkeypatch.setitem(arm.phase, "architect", arch)
    monkeypatch.setitem(arm.phase, "foresight", fore)

    repo = str(tmp_path / "repo")
    _seed_repo(repo)
    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )
    import core.engine.arms.dispatch as _dispatch

    monkeypatch.setattr(_dispatch, "route", lambda solution: [arm])

    async def run(obj, profile):
        ran["phases"] = []

        async def classifier(s, c, o):
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
        async with pool.connection() as db:
            await db.query("DELETE agent_spec WHERE objective=$o", {"o": obj})
            await db.query("DELETE action_outcome WHERE spec=$s", {"s": parse_record_id(sid)})
        return list(ran["phases"])

    green = WorkProfile(scope="repo", novelty="greenfield", risk="connected", verify_depth="unit")
    syst = WorkProfile(scope="module", novelty="modify", risk="systemic", verify_depth="full")

    green_phases = await run("E2E_DEEP greenfield", green)
    syst_phases = await run("E2E_DEEP systemic", syst)

    assert "architect" in green_phases, green_phases  # greenfield -> architect ran
    assert "foresight" not in green_phases  # not systemic -> no foresight
    assert "foresight" in syst_phases, syst_phases  # systemic -> foresight ran
    assert "architect" not in syst_phases  # not greenfield -> no architect
