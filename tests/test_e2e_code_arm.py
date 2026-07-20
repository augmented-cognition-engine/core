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
async def test_code_arm_full_loop_stubbed_llm(db_pool, tmp_path, monkeypatch, no_adversarial_review):
    """ace_build a code spec → CodeArm (stubbed brain) builds real file + test → built →
    promote → shipped. Proves the wiring + worktree + gate end to end, deterministically."""
    import core.engine.arms.code_planner as cp
    from core.engine.arms.code_arm import CodeArm
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.promotion import promote
    from core.engine.arms.registry import route
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.mcp.tools import ace_build
    from core.engine.solution import Solution

    PID = "product:platform"
    OBJ = "E2E_CODE add code module helper"

    # Stub the brain callables at the module level so every CodeArm instance
    # (including the one dispatch_solution creates via route()) uses them.
    async def loader(intent, product_id="product:platform"):
        return {}

    async def reasoner(intent, context, product_id="product:platform"):
        return "cover: import works"

    async def codegen(intent, reasoning, context):
        return (
            [{"path": "helper.py", "content": "def helper():\n    return 42\n"}],
            ["python", "-c", "import helper; assert helper.helper() == 42"],
            ["import works"],
        )

    async def critic(concerns, ws):
        return True, []

    monkeypatch.setattr(cp, "default_loader", loader)
    monkeypatch.setattr(cp, "default_reasoner", reasoner)
    monkeypatch.setattr(cp, "default_codegen", codegen)
    monkeypatch.setattr(cp, "default_critic", critic)

    # Verify the registry returns a CodeArm for domain_hint="code"
    arm = next((a for a in route(Solution(intent="code", domain_hint="code")) if isinstance(a, CodeArm)), None)
    assert arm is not None, "CodeArm must be registered and route for domain_hint='code'"

    async with pool.connection() as db:
        await db.query("DELETE agent_spec WHERE objective = $o", {"o": OBJ})
        await db.query("DELETE action_outcome WHERE intent CONTAINS 'E2E_CODE'")
        created = parse_rows(
            await db.query(
                "CREATE agent_spec SET product=$p, objective=$o, source='strategy_ingest', "
                "acceptance_criteria=[], status='approved' RETURN id",
                {"p": parse_record_id(PID), "o": OBJ},
            )
        )
    spec_id = str(created[0]["id"])

    repo = str(tmp_path / "repo")
    _seed_repo(repo)
    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )

    out = await ace_build(spec_id, product_id=PID)
    assert out["built"] is True, f"build failed: {out}"

    promoted = await promote(spec_id, product_id=PID, gate_cmd=["true"])
    assert promoted["promoted"] is True, f"promote failed: {promoted}"
    assert os.path.exists(os.path.join(repo, "helper.py"))  # the arm's real code shipped to base

    async with pool.connection() as db:
        s = parse_rows(await db.query("SELECT status FROM agent_spec WHERE id=$s", {"s": parse_record_id(spec_id)}))
        await db.query("DELETE agent_spec WHERE objective=$o", {"o": OBJ})
        await db.query("DELETE action_outcome WHERE spec=$s", {"s": parse_record_id(spec_id)})
    assert s and s[0]["status"] == "shipped"
