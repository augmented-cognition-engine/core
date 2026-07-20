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
    with open(os.path.join(root, "f.txt"), "w") as fh:
        fh.write("seed\n")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "seed"], check=True)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_ace_build_then_promote_full_loop(db_pool, tmp_path, monkeypatch, no_adversarial_review):
    """An approved spec → ace_build → built/review → promote → shipped, from tool calls."""
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.scaffold_arm import ScaffoldArm  # noqa: F401 — registration
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.mcp.tools import ace_build

    PID = "product:platform"
    OBJ = "E2E_BUILD scaffold a demo file"  # contains 'scaffold' → routes to ScaffoldArm

    async with pool.connection() as db:
        await db.query("DELETE agent_spec WHERE objective = $o", {"o": OBJ})
        await db.query("DELETE action_outcome WHERE intent CONTAINS 'E2E_BUILD'")
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

    # 1) ace_build → spec built, in review
    out = await ace_build(spec_id, product_id=PID)
    assert out["built"] is True, f"build failed: {out}"
    async with pool.connection() as db:
        s = parse_rows(await db.query("SELECT status FROM agent_spec WHERE id=$s", {"s": parse_record_id(spec_id)}))
    assert s and s[0]["status"] == "built"

    # 2) promote (stub gate green) → shipped + merged
    from core.engine.arms.promotion import promote

    promoted = await promote(spec_id, product_id=PID, gate_cmd=["true"])
    assert promoted["promoted"] is True, f"promote failed: {promoted}"
    assert os.path.exists(os.path.join(repo, "scaffold.txt"))  # real work shipped to base

    async with pool.connection() as db:
        s2 = parse_rows(await db.query("SELECT status FROM agent_spec WHERE id=$s", {"s": parse_record_id(spec_id)}))
        await db.query("DELETE agent_spec WHERE objective=$o", {"o": OBJ})
        await db.query("DELETE action_outcome WHERE spec=$s", {"s": parse_record_id(spec_id)})
    assert s2 and s2[0]["status"] == "shipped"
