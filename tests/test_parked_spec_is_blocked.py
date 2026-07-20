"""A parked spec must NOT go back in the queue, and a zombie run must not stay 'running' forever.

Two holes that only bite once something runs unattended:

  1. build_spec resets a non-passing build's spec to 'approved' — i.e. straight back into the
     buildable queue. For a FAILED build that is right (it can be retried). For a PARKED build it
     is an infinite loop: the session picks it up, parks again on the same dead model, requeues,
     picks it up... forever, burning tokens and producing nothing. Parked → BLOCKED.

  2. A process killed mid-build leaves its arm_run at 'running' with nobody to close it. Nothing
     ever reconciles those, so get_open_runs fills with zombies and the "needs a human" signal
     degrades into noise — the exact way a good instrument turns into a lying one.
"""

from __future__ import annotations

import pytest


class _FakeDB:
    def __init__(self, spec_rows):
        self.queries: list[tuple[str, dict]] = []
        self._spec_rows = spec_rows

    async def query(self, q, params=None):
        self.queries.append((q.strip(), params or {}))
        if "SELECT objective" in q:
            return self._spec_rows
        return []

    def status_writes(self) -> list[str]:
        return [p.get("st", "") or q for q, p in self.queries if "SET status" in q]


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


class _Verdict:
    def __init__(self, passed, reason="", parked=False, diagnosis=""):
        self.passed = passed
        self.reason = reason
        self.parked = parked
        self.diagnosis = diagnosis


@pytest.mark.asyncio
async def test_a_parked_build_blocks_the_spec_instead_of_requeueing_it(monkeypatch):
    import core.engine.arms.builder as builder

    db = _FakeDB([{"objective": "add the widget", "status": "approved"}])

    async def _dispatch(sol, product_id="product:platform"):
        return ("code", object(), _Verdict(False, "env dead", parked=True, diagnosis="model unreachable"))

    monkeypatch.setattr("core.engine.arms.dispatch.dispatch_solution", _dispatch)

    out = await builder.build_spec("agent_spec:x", pool=_FakePool(db))

    assert out["built"] is False
    assert out["parked"] is True, "the caller (the session loop) has to be able to SEE this"
    assert "unreachable" in out["diagnosis"]

    writes = [p.get("st") for q, p in db.queries if "SET status=$st" in q]
    assert "blocked" in writes, "a parked spec must be BLOCKED, not handed back to the build queue"
    assert "approved" not in writes, "requeueing a parked spec is an infinite park-retry loop"


@pytest.mark.asyncio
async def test_a_genuinely_failed_build_still_requeues_the_spec(monkeypatch):
    """The guard must not over-fire: a failed build is retryable and belongs back in the queue."""
    import core.engine.arms.builder as builder

    db = _FakeDB([{"objective": "add the widget", "status": "approved"}])

    async def _dispatch(sol, product_id="product:platform"):
        return ("code", object(), _Verdict(False, "tests red"))

    monkeypatch.setattr("core.engine.arms.dispatch.dispatch_solution", _dispatch)

    out = await builder.build_spec("agent_spec:x", pool=_FakePool(db))

    assert out["built"] is False
    assert out.get("parked") is not True
    writes = [p.get("st") for q, p in db.queries if "SET status=$st" in q]
    assert "approved" in writes


@pytest.mark.asyncio
async def test_reconcile_closes_zombie_runs_as_parked():
    from core.engine.arms.run_ledger import reconcile_stale_runs

    db = _FakeDB([])
    n = await reconcile_stale_runs(product_id="product:platform", pool=_FakePool(db))

    sql, params = db.queries[0]
    assert "status = 'running'" in sql, "only runs nobody closed"
    assert "started_at <" in sql, "and only OLD ones — a build in flight right now is not a zombie"
    assert params["status"] == "parked"
    assert "died" in params["diagnosis"].lower() or "interrupt" in params["diagnosis"].lower()
    assert isinstance(n, int)


@pytest.mark.asyncio
async def test_reconcile_is_fail_safe():
    from core.engine.arms.run_ledger import reconcile_stale_runs

    class _Dead:
        def connection(self):
            raise RuntimeError("db gone")

    assert await reconcile_stale_runs(product_id="p:1", pool=_Dead()) == 0
