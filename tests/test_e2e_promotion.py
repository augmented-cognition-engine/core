from __future__ import annotations

import os
import subprocess

import pytest


def _seed_repo(root):
    os.makedirs(root, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "t"], check=True)
    with open(os.path.join(root, "f.txt"), "w") as fh:
        fh.write("seed\n")
    # .worktrees/ must be ignored so git status stays clean while arm worktrees are live
    with open(os.path.join(root, ".gitignore"), "w") as fh:
        fh.write(".worktrees/\n")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "seed"], check=True)


async def _build_spec_to_built(monkeypatch, repo):
    """Dispatch a real ScaffoldArm bound to a seeded spec → returns (spec_id, OBJ); spec 'built'.

    The arm writes scaffold.txt into the worktree but does NOT commit it — that is
    promote()'s job. promote() commits the worktree build to the arm branch before
    merging, which is the real production flow this e2e validates."""
    from core.engine.arms.dispatch import dispatch_solution
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.scaffold_arm import ScaffoldArm  # noqa: F401 — registration
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.solution import Solution

    PID = "product:platform"
    OBJ = "E2E_PROMO spec"
    async with pool.connection() as db:
        await db.query("DELETE agent_spec WHERE objective = $o", {"o": OBJ})
        await db.query("DELETE action_outcome WHERE intent CONTAINS 'E2E_PROMO'")
        created = parse_rows(
            await db.query(
                "CREATE agent_spec SET product=$p, objective=$o, source='strategy_ingest', "
                "acceptance_criteria=[], status='building' RETURN id",
                {"p": parse_record_id(PID), "o": OBJ},
            )
        )
    spec_id = str(created[0]["id"])
    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )
    sol = Solution(intent="scaffold a file", domain_hint="scaffold", spec_id=spec_id)
    _, result, verdict = await dispatch_solution(sol, product_id=PID)
    assert verdict.passed, f"arm execution failed: {verdict.reason}"

    return spec_id, OBJ


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_promote_happy_path_ships_and_merges(db_pool, tmp_path, monkeypatch, no_adversarial_review):
    from core.engine.arms.promotion import promote
    from core.engine.core.db import parse_record_id, parse_rows, pool

    repo = str(tmp_path / "repo")
    _seed_repo(repo)
    spec_id, OBJ = await _build_spec_to_built(monkeypatch, repo)
    assert not os.path.exists(os.path.join(repo, "scaffold.txt"))  # not on base yet

    out = await promote(spec_id, product_id="product:platform", gate_cmd=["true"])
    assert out["promoted"] is True
    assert os.path.exists(os.path.join(repo, "scaffold.txt"))  # merged into base
    wt = subprocess.run(["git", "-C", repo, "worktree", "list"], capture_output=True, text=True).stdout
    assert ".worktrees" not in wt  # worktree discarded

    async with pool.connection() as db:
        s = parse_rows(await db.query("SELECT status FROM agent_spec WHERE id=$s", {"s": parse_record_id(spec_id)}))
        promo = parse_rows(
            await db.query(
                "SELECT arm_domain FROM action_outcome WHERE spec=$s AND arm_domain='promotion'",
                {"s": parse_record_id(spec_id)},
            )
        )
        await db.query("DELETE agent_spec WHERE objective=$o", {"o": OBJ})
        await db.query("DELETE action_outcome WHERE spec=$s", {"s": parse_record_id(spec_id)})
    assert s and s[0]["status"] == "shipped"
    assert promo


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_promote_gate_red_reverts_and_keeps_built(db_pool, tmp_path, monkeypatch, no_adversarial_review):
    from core.engine.arms.promotion import promote
    from core.engine.core.db import parse_record_id, parse_rows, pool

    repo = str(tmp_path / "repo")
    _seed_repo(repo)
    spec_id, OBJ = await _build_spec_to_built(monkeypatch, repo)
    pre = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    out = await promote(spec_id, product_id="product:platform", gate_cmd=["false"])  # gate RED
    assert out["promoted"] is False
    now = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert now == pre  # merge reverted
    assert not os.path.exists(os.path.join(repo, "scaffold.txt"))

    async with pool.connection() as db:
        s = parse_rows(await db.query("SELECT status FROM agent_spec WHERE id=$s", {"s": parse_record_id(spec_id)}))
        ao = parse_rows(
            await db.query(
                "SELECT workspace_path, workspace_branch, workspace_repo_root, created_at FROM action_outcome "
                "WHERE spec=$s ORDER BY created_at DESC LIMIT 1",
                {"s": parse_record_id(spec_id)},
            )
        )
        await db.query("DELETE agent_spec WHERE objective=$o", {"o": OBJ})
        await db.query("DELETE action_outcome WHERE spec=$s", {"s": parse_record_id(spec_id)})
    assert s and s[0]["status"] == "built"  # stayed built (still in review)
    if ao and ao[0].get("workspace_path"):
        from core.engine.arms.execution.workspace import Workspace

        Workspace(
            path=ao[0]["workspace_path"],
            branch=ao[0].get("workspace_branch") or "",
            repo_root=ao[0]["workspace_repo_root"],
        ).discard()
