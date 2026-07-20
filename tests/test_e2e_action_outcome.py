from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_action_outcome_table_and_built_status(db_pool):
    """v126 applied: action_outcome accepts a write; agent_spec.status accepts 'built'."""
    from core.engine.core.db import parse_record_id, parse_rows, pool

    async with pool.connection() as db:
        await db.query("DELETE action_outcome WHERE intent = 'SMOKE_AO'")
        await db.query(
            "CREATE action_outcome SET product=$p, arm_domain='scaffold', intent='SMOKE_AO', "
            "passed=true, reason='ok', performed_verbs=['write_file']",
            {"p": parse_record_id("product:platform")},
        )
        rows = parse_rows(await db.query("SELECT intent, passed FROM action_outcome WHERE intent = 'SMOKE_AO'"))
        await db.query("DELETE agent_spec WHERE objective = 'SMOKE_AO_SPEC'")
        await db.query(
            "CREATE agent_spec SET product=$p, objective='SMOKE_AO_SPEC', source='test', "
            "acceptance_criteria=[], status='built'",
            {"p": parse_record_id("product:platform")},
        )
        srows = parse_rows(await db.query("SELECT status FROM agent_spec WHERE objective = 'SMOKE_AO_SPEC'"))
        await db.query("DELETE action_outcome WHERE intent = 'SMOKE_AO'")
        await db.query("DELETE agent_spec WHERE objective = 'SMOKE_AO_SPEC'")

    assert rows and rows[0]["passed"] is True
    assert srows and srows[0]["status"] == "built"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_loop_closes_built_spec_in_review_lane(db_pool, tmp_path, monkeypatch, no_adversarial_review):
    """Dispatch a passing arm bound to a real spec → action_outcome persisted +
    spec advanced to 'built' + roadmap places it in the review lane with its branch."""
    import os
    import subprocess

    from core.engine.arms.dispatch import dispatch_solution
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.scaffold_arm import ScaffoldArm  # noqa: F401 — registration
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.product.roadmap import compute_roadmap
    from core.engine.solution import Solution

    PID = "product:platform"
    OBJ = "E2E_AO Graph community summaries"

    # Seed a strategy-ingest spec in 'building'.
    async with pool.connection() as db:
        await db.query("DELETE agent_spec WHERE objective = $o", {"o": OBJ})
        await db.query("DELETE action_outcome WHERE intent CONTAINS 'E2E_AO'")
        created = parse_rows(
            await db.query(
                "CREATE agent_spec SET product=$p, objective=$o, source='strategy_ingest', "
                "acceptance_criteria=[], status='building' RETURN id",
                {"p": parse_record_id(PID), "o": OBJ},
            )
        )
    spec_id = str(created[0]["id"])

    # Real arm execution in a tmp repo.
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

    sol = Solution(intent="scaffold a file", domain_hint="scaffold", spec_id=spec_id)
    domain, result, verdict = await dispatch_solution(sol, product_id=PID)
    assert verdict.passed is True

    # (a) action_outcome persisted for this spec, passed=true
    async with pool.connection() as db:
        ao = parse_rows(
            await db.query(
                "SELECT passed, workspace_branch FROM action_outcome WHERE spec = $s", {"s": parse_record_id(spec_id)}
            )
        )
        spec_now = parse_rows(
            await db.query("SELECT status FROM agent_spec WHERE id = $s", {"s": parse_record_id(spec_id)})
        )
    assert ao and ao[0]["passed"] is True
    assert spec_now and spec_now[0]["status"] == "built"  # (b) spec advanced

    # (c) roadmap places it in review with its branch
    roadmap = await compute_roadmap(PID, max_items=200)
    review = [it for it in roadmap.lanes.get("review", []) if it.title == OBJ]
    assert review, "built spec should be in the review lane"
    assert "arm/" in review[0].rationale  # shows the worktree branch

    # cleanup
    if result.workspace is not None:
        result.workspace.discard()
    async with pool.connection() as db:
        await db.query("DELETE agent_spec WHERE objective = $o", {"o": OBJ})
        await db.query("DELETE action_outcome WHERE spec = $s", {"s": parse_record_id(spec_id)})
