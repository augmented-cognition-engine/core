from __future__ import annotations


class _DB:
    def __init__(self, status):
        self.status = status
        self.updates = []

    async def query(self, q, params=None):
        u = q.strip().upper()
        if u.startswith("SELECT"):
            return [{"objective": "scaffold a file", "status": self.status}]
        if u.startswith("UPDATE"):
            self.updates.append((q, params or {}))
            return []
        return []


class _Pool:
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


def test_build_spec_refuses_shipped():
    import asyncio

    from core.engine.arms.builder import build_spec

    out = asyncio.run(build_spec("agent_spec:abc", "product:platform", pool=_Pool(_DB("shipped"))))
    assert out["built"] is False
    assert "shipped" in out["reason"]


def test_build_spec_refuses_built_pending_review():
    import asyncio

    from core.engine.arms.builder import build_spec

    out = asyncio.run(build_spec("agent_spec:abc", "product:platform", pool=_Pool(_DB("built"))))
    assert out["built"] is False
    assert "review" in out["reason"].lower()


def test_build_spec_no_arm_resets_status(monkeypatch):
    import asyncio

    from core.engine.arms.builder import build_spec

    async def fake_dispatch(sol, product_id="product:platform"):
        return None  # no arm handled it

    monkeypatch.setattr("core.engine.arms.dispatch.dispatch_solution", fake_dispatch)

    db = _DB("approved")
    out = asyncio.run(build_spec("agent_spec:abc", "product:platform", pool=_Pool(db)))
    assert out["built"] is False and "no arm" in out["reason"].lower()
    set_to = [p.get("st") for (q, p) in db.updates if "st" in p]
    assert "approved" in set_to


def test_build_spec_pass_sets_building_and_returns_built(monkeypatch):
    import asyncio

    from core.engine.arms.base import ActionPlan, ArmResult, Verdict
    from core.engine.arms.builder import build_spec

    async def fake_dispatch(sol, product_id="product:platform"):
        assert sol.spec_id == "agent_spec:abc"
        assert "scaffold" in sol.intent
        return ("scaffold", ArmResult(plan=ActionPlan(summary="x")), Verdict(passed=True, reason="ok"))

    monkeypatch.setattr("core.engine.arms.dispatch.dispatch_solution", fake_dispatch)

    db = _DB("approved")
    out = asyncio.run(build_spec("agent_spec:abc", "product:platform", pool=_Pool(db)))
    assert out["built"] is True
    assert any("building" in q.lower() for (q, p) in db.updates)


def test_ace_build_tool_delegates(monkeypatch):
    import asyncio

    import core.engine.mcp.tools as tools

    async def fake_build(spec_id, product_id="product:platform", pool=None):
        return {"built": True, "branch": "arm/scaffold-9f2", "reason": "built — in review"}

    monkeypatch.setattr("core.engine.arms.builder.build_spec", fake_build)

    out = asyncio.run(tools.ace_build("agent_spec:abc"))
    assert out["built"] is True
    assert out["branch"] == "arm/scaffold-9f2"
