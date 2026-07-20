# tests/test_e2e_data_arm.py
from __future__ import annotations

import os
import subprocess

import pytest


def _seed_repo(root):
    os.makedirs(root, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "t"], check=True)
    # seed an existing schema so the arm's migration is "additive on an existing repo"
    os.makedirs(os.path.join(root, "core", "schema"), exist_ok=True)
    with open(os.path.join(root, "core", "schema", "v001_base.surql"), "w") as fh:
        fh.write("DEFINE TABLE agent_spec SCHEMALESS;\n")
    with open(os.path.join(root, ".gitignore"), "w") as fh:
        fh.write(".worktrees/\n")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "seed"], check=True)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_data_arm_writes_gates_ships(db_pool, tmp_path, monkeypatch, no_adversarial_review):
    from core.engine.arms.data_arm import DataArm
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.promotion import promote
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.mcp.tools import ace_build

    PID = "product:platform"
    arm = DataArm()

    async def classifier(s, c, o):
        return WorkProfile(scope="nearby", novelty="extend", risk="isolated", verify_depth="smoke")

    async def loader(i, product_id="product:platform"):
        return {"next_version": 2, "tables": ["agent_spec"]}

    async def reasoner(i, c, product_id="product:platform"):
        return "additive new table widget"

    state = {"attempt": 0}

    async def codegen(i, r, c):
        state["attempt"] += 1
        if state["attempt"] == 1:
            # planted v126 violation: required field, no default, on the EXISTING agent_spec table
            content = "DEFINE FIELD org ON agent_spec TYPE string;\n"
            path = "core/schema/v002_org.surql"
        else:
            content = "DEFINE TABLE widget SCHEMALESS;\nDEFINE FIELD name ON widget TYPE string;\n"
            path = "core/schema/v002_widget.surql"
        return ([{"path": path, "content": content}], None, ["additive"])

    class _DLLM:
        async def complete_json(self, prompt):
            return {"uncovered": []}

    monkeypatch.setattr(arm, "_classifier", classifier)
    monkeypatch.setattr(arm, "_load", loader)
    monkeypatch.setattr(arm, "_reason", reasoner)
    monkeypatch.setattr(arm, "_codegen", codegen)

    import core.engine.arms.data_planner as dp

    monkeypatch.setattr(dp, "get_llm", lambda: _DLLM())
    monkeypatch.setattr(arm, "_critic", dp.default_critic)

    repo = str(tmp_path / "repo")
    _seed_repo(repo)
    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )

    import core.engine.arms.dispatch as _dispatch

    monkeypatch.setattr(_dispatch, "route", lambda solution: [arm])

    obj = "E2E_DATA add a widget table"
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
    assert out["built"] is True, out  # repair turned the planted v126 violation into a clean additive table
    assert state["attempt"] >= 2  # the safety gate fired the repair loop

    promoted = await promote(sid, product_id=PID, gate_cmd=["true"])
    assert promoted["promoted"] is True, promoted

    # I4 / C1: the repair OVERWROTE the original file (didn't write a 2nd file at the same version),
    # so exactly ONE v002 migration merged — no discarded attempt shipping its v126 bug.
    import glob

    v002 = glob.glob(os.path.join(repo, "core", "schema", "v002*.surql"))
    assert len(v002) == 1, f"expected exactly one v002 migration (no leftover), got {v002}"
    with open(v002[0], encoding="utf-8") as fh:
        merged = fh.read()
    assert "DEFINE FIELD org ON agent_spec" not in merged, "the row-dropping v126 migration must NOT ship"

    async with pool.connection() as db:
        await db.query("DELETE agent_spec WHERE objective=$o", {"o": obj})
        await db.query("DELETE action_outcome WHERE spec=$s", {"s": parse_record_id(sid)})
