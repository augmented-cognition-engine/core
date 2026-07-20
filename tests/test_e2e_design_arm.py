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
async def test_design_arm_composes_gates_ships(db_pool, tmp_path, monkeypatch, no_adversarial_review):
    from core.engine.arms.design_arm import DesignArm
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.promotion import promote
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.mcp.tools import ace_build

    PID = "product:platform"

    arm = DesignArm()

    async def classifier(s, c, o):
        return WorkProfile(scope="nearby", novelty="extend", risk="isolated", verify_depth="smoke")

    async def loader(i, product_id="product:platform"):
        return {"catalog": "Card, Stack, Button, EmptyState, AmbientWorking"}

    async def reasoner(i, c, product_id="product:platform"):
        return "compose Card + Stack + Button; AmbientWorking on load"

    state = {"attempt": 0}

    async def codegen(i, r, c):
        # First attempt plants a violation (inline hex); repair produces a clean surface.
        state["attempt"] += 1
        if state["attempt"] == 1:
            content = (
                "import { Card } from '../design/components'\n"
                "export const Panel = () => <Card style={{ color: '#ff0000' }} />\n"
            )
        else:
            content = (
                "import { Card, Stack, Button } from '../design/components'\n"
                "export const Panel = () => (<Card><Stack><Button>Save</Button></Stack></Card>)\n"
            )
        return ([{"path": "core/ui/canvas/src/app/Panel.tsx", "content": content}], None, ["composed from primitives"])

    monkeypatch.setattr(arm, "_classifier", classifier)
    monkeypatch.setattr(arm, "_load", loader)
    monkeypatch.setattr(arm, "_reason", reasoner)
    monkeypatch.setattr(arm, "_codegen", codegen)

    # Critic: use the REAL mechanical scan, stub only the LLM non-mechanical pass to "clean".
    # The stub must be ASYNC — the critic does `await get_llm().complete_json(...)`; a sync stub
    # would raise on await and be swallowed, so the LLM tier would never actually run.
    class _ELLM:
        async def complete_json(self, prompt):
            return {"uncovered": []}

    import core.engine.arms.design_planner as dp

    monkeypatch.setattr(dp, "get_llm", lambda: _ELLM())
    monkeypatch.setattr(arm, "_critic", dp.default_critic)

    repo = str(tmp_path / "repo")
    _seed_repo(repo)
    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )

    import core.engine.arms.dispatch as _dispatch

    monkeypatch.setattr(_dispatch, "route", lambda solution: [arm])

    obj = "E2E_DESIGN compose a settings panel"
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
    assert out["built"] is True, out  # repair turned the planted violation clean
    assert state["attempt"] >= 2  # proves the repair loop fired

    promoted = await promote(sid, product_id=PID, gate_cmd=["true"])
    assert promoted["promoted"] is True, promoted

    async with pool.connection() as db:
        await db.query("DELETE agent_spec WHERE objective=$o", {"o": obj})
        await db.query("DELETE action_outcome WHERE spec=$s", {"s": parse_record_id(sid)})
