from __future__ import annotations

import pytest


def test_solution_spec_id_defaults_none():
    from core.engine.solution import Solution

    s = Solution(intent="build the thing")
    assert s.spec_id is None  # backward-compatible default

    s2 = Solution(intent="build", spec_id="agent_spec:abc")
    assert s2.spec_id == "agent_spec:abc"


def test_review_lane_and_built_mapping():
    from core.engine.product.roadmap import _lane_for_strategy_item
    from core.engine.product.roadmap_models import LANES

    assert "review" in LANES
    # review sits right after now.
    assert LANES.index("review") == LANES.index("now") + 1
    assert _lane_for_strategy_item("spec", "built") == "review"
    # existing mappings unchanged:
    assert _lane_for_strategy_item("spec", "shipped") == "done"
    assert _lane_for_strategy_item("spec", "building") == "now"


class _FakeDB:
    def __init__(self):
        self.queries = []

    async def query(self, q, params=None):
        self.queries.append((q.strip(), params or {}))
        return []


class _FakePool:
    def __init__(self, db):
        self._db = db

    def connection(self):
        db = self._db

        class Ctx:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *a):
                return False

        return Ctx()


class _WS:
    branch = "arm/scaffold-9f2"

    def diff(self):
        return "+10 -2 diff body"


def _result(performed_verbs, ws=None):
    from core.engine.arms.base import Action, ActionPlan, ArmResult, RiskTier

    actions = [Action(verb=v, args={}, risk=RiskTier.REVERSIBLE) for v in performed_verbs]
    return ArmResult(plan=ActionPlan(summary="x"), performed=actions, simulated=False, logs=[], workspace=ws)


def test_capture_writes_outcome_and_advances_on_pass():
    import asyncio

    from core.engine.arms.base import Verdict
    from core.engine.arms.outcome import capture_outcome
    from core.engine.solution import Solution

    db = _FakeDB()
    pool = _FakePool(db)
    sol = Solution(intent="build cross-encoder rerank", spec_id="agent_spec:abc")
    asyncio.run(
        capture_outcome(
            sol,
            "scaffold",
            _result(["write_file"], _WS()),
            Verdict(passed=True, reason="ok"),
            "product:platform",
            pool=pool,
        )
    )

    verbs = [q[0].split()[0].upper() for q in db.queries]
    assert "CREATE" in verbs  # action_outcome written
    assert "UPDATE" in verbs  # spec advanced (passed + spec_id)
    create_q = next(q for q in db.queries if q[0].upper().startswith("CREATE"))
    assert create_q[1]["passed"] is True
    assert create_q[1]["branch"] == "arm/scaffold-9f2"


def test_capture_no_advance_on_fail_or_missing_spec():
    import asyncio

    from core.engine.arms.base import Verdict
    from core.engine.arms.outcome import capture_outcome
    from core.engine.solution import Solution

    # failed verdict (with spec_id) → outcome written, NO status advance
    db = _FakeDB()
    pool = _FakePool(db)
    sol = Solution(intent="x", spec_id="agent_spec:abc")
    asyncio.run(
        capture_outcome(
            sol,
            "scaffold",
            _result(["write_file"], _WS()),
            Verdict(passed=False, reason="nope"),
            "product:platform",
            pool=pool,
        )
    )
    assert any(q[0].upper().startswith("CREATE") for q in db.queries)
    assert not any(q[0].upper().startswith("UPDATE") for q in db.queries)

    # passed but no spec_id → outcome written, NO advance
    db2 = _FakeDB()
    pool2 = _FakePool(db2)
    sol2 = Solution(intent="x")  # spec_id None
    asyncio.run(
        capture_outcome(
            sol2, "scaffold", _result(["write_file"]), Verdict(passed=True, reason="ok"), "product:platform", pool=pool2
        )
    )
    assert any(q[0].upper().startswith("CREATE") for q in db2.queries)
    assert not any(q[0].upper().startswith("UPDATE") for q in db2.queries)


@pytest.mark.asyncio
async def test_dispatch_calls_capture_before_discard(monkeypatch, tmp_path):
    import core.engine.arms.dispatch as d
    from core.engine.solution import Solution

    captured = {}

    async def fake_capture(solution, arm_domain, result, verdict, product_id="product:platform", pool=None, **kw):
        captured["domain"] = arm_domain
        captured["passed"] = verdict.passed
        captured["spec_id"] = solution.spec_id
        captured["attempts"] = kw.get("attempts")

    monkeypatch.setattr(d, "capture_outcome", fake_capture)

    # Redirect Workspace.create to a tmp repo (so the real arm runs without touching the real repo).
    import os
    import subprocess

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
    from core.engine.arms.scaffold_arm import ScaffoldArm  # noqa: F401 — registration

    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )

    sol = Solution(intent="scaffold a file", domain_hint="scaffold", spec_id="agent_spec:abc")
    out = await d.dispatch_solution(sol)
    assert out is not None
    domain, result, verdict = out
    assert captured["domain"] == "scaffold"  # capture_outcome was called
    assert captured["passed"] is True
    assert captured["spec_id"] == "agent_spec:abc"
    if result.workspace is not None:
        result.workspace.discard()


@pytest.mark.asyncio
async def test_built_spec_rationale_includes_branch(monkeypatch):
    from core.engine.product import roadmap as rm

    class DB:
        async def query(self, q, params=None):
            u = q.upper()
            if "FROM ROADMAP_PHASE" in u:
                return []
            if "FROM AGENT_SPEC" in u:
                return [
                    {
                        "id": "agent_spec:abc",
                        "objective": "Graph community summaries",
                        "status": "built",
                        "priority": "high",
                        "source_ref": ["wc"],
                    }
                ]
            if "FROM ACTION_OUTCOME" in u:
                return [
                    {
                        "workspace_branch": "arm/scaffold-9f2",
                        "diff_summary": "+84 -3",
                        "created_at": "2026-06-20T00:00:00Z",
                    }
                ]
            return []

    items = await rm._project_strategy_items(DB(), "product:platform")
    built = [i for i in items if i.spec_status == "built"]
    assert built, "expected a built spec item"
    assert built[0].lane == "review"
    assert "arm/scaffold-9f2" in built[0].rationale  # shows what to approve
