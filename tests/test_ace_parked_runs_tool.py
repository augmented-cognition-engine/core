"""A parked run nobody can SEE is worth exactly nothing.

The whole point of the parked state is that an unattended build leaves behind something a human
comes back to. If no surface reads it, we have built a more honest state machine that fails
silently in a more sophisticated way — the orphan-tool failure mode, which has shipped green in
this repo before.

So: ace_parked_runs, and a test that asserts it is REGISTERED, not merely defined.
"""

from __future__ import annotations

import pytest


class _FakeDB:
    def __init__(self, rows):
        self.queries: list[tuple[str, dict]] = []
        self._rows = rows

    async def query(self, q, params=None):
        self.queries.append((q.strip(), params or {}))
        return self._rows


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


@pytest.mark.asyncio
async def test_parked_runs_reports_what_needs_a_human():
    from core.engine.mcp.tools import ace_parked_runs

    rows = [
        [
            {
                "id": "arm_run:abc",
                "intent": "add the widget",
                "arm_domain": "code",
                "status": "parked",
                "diagnosis": "LLMError: model unreachable. The workspace is preserved.",
                "attempts": 1,
            }
        ]
    ]
    out = await ace_parked_runs(product_id="product:platform", pool=_FakePool(_FakeDB(rows)))

    assert out["count"] == 1
    run = out["runs"][0]
    assert run["intent"] == "add the widget"
    assert "unreachable" in run["diagnosis"], "the diagnosis is the whole payload — what must a human FIX"


@pytest.mark.asyncio
async def test_parked_runs_also_surfaces_interrupted_builds():
    """A killed process leaves a 'running' row nobody finalized. That needs a human too — it is
    just a park the engine never got the chance to write."""
    from core.engine.mcp.tools import ace_parked_runs

    rows = [[{"id": "arm_run:x", "intent": "big refactor", "arm_domain": "code", "status": "running"}]]
    out = await ace_parked_runs(product_id="product:platform", pool=_FakePool(_FakeDB(rows)))

    assert out["count"] == 1
    assert out["runs"][0]["status"] == "running"


@pytest.mark.asyncio
async def test_parked_runs_is_empty_when_nothing_needs_attention():
    from core.engine.mcp.tools import ace_parked_runs

    out = await ace_parked_runs(product_id="product:platform", pool=_FakePool(_FakeDB([[]])))
    assert out == {"runs": [], "count": 0}


@pytest.mark.asyncio
async def test_parked_runs_is_fail_safe():
    from core.engine.mcp.tools import ace_parked_runs

    class _Dead:
        def connection(self):
            raise RuntimeError("db is gone")

    out = await ace_parked_runs(product_id="product:platform", pool=_Dead())
    assert out == {"runs": [], "count": 0}, "a status read must never raise into the caller"


@pytest.mark.asyncio
async def test_parked_runs_reads_through_the_ledger(monkeypatch):
    """The tool must not hand-write arm_run SQL. One module owns that schema — otherwise the query
    drifts in two places and the read quietly stops matching what dispatch writes."""
    import core.engine.arms.run_ledger as ledger
    from core.engine.mcp.tools import ace_parked_runs

    called = {}

    async def _fake(*, product_id, limit=50, pool=None):
        called["product_id"] = product_id
        return [{"id": "arm_run:z", "intent": "i", "arm_domain": "code", "status": "parked"}]

    monkeypatch.setattr(ledger, "get_runs_needing_attention", _fake)

    out = await ace_parked_runs(product_id="product:platform")

    assert called["product_id"] == "product:platform", "the tool must delegate to the ledger"
    assert out["count"] == 1


def test_parked_runs_is_actually_registered_on_the_mcp_server():
    """The bug that has shipped green in this repo more than once: a tool that exists, is tested,
    and is never registered — so it is unreachable in production. Assert the wiring, not the code."""
    import inspect

    import core.engine.mcp.server as server

    src = inspect.getsource(server)
    assert "async def ace_parked_runs" in src, "the tool must be defined on the server"
    # The decorated definition must sit under an @mcp.tool(...) registration.
    idx = src.index("async def ace_parked_runs")
    preceding = src[:idx].rstrip().splitlines()[-1]
    assert "@mcp.tool" in preceding, "ace_parked_runs must be REGISTERED with @mcp.tool, not just defined"
