"""A spec stuck in 'building' with nothing building it is work that is silently LOST.

The zombie-run fix had a twin I missed, and production had a live example of it:

    build_spec() sets status='building' BEFORE dispatch. If the process dies mid-build,
    reconcile_stale_runs parks the arm_run — but NOTHING releases the spec. It stays
    'building' forever. The session only picks 'approved', and build_spec refuses a
    'building' spec ("already building"). The spec can never be built again.

Nobody gets an error. Nothing appears in a failure list. The work simply stops existing, which
is the worst possible failure mode for something meant to run unattended.

The release target is 'approved', NOT 'blocked', and that distinction is the whole design: a
crashed process is not a broken environment. Releasing it lets the loop RETRY once — and if the
environment really is dead, that retry parks and blocks it. Self-correcting, and it terminates.
"""

from __future__ import annotations

import pytest


class _FakeDB:
    def __init__(self, stranded=None, running_runs=None):
        self.queries: list[tuple[str, dict]] = []
        self._stranded = stranded if stranded is not None else []
        self._running = running_runs if running_runs is not None else []

    async def query(self, q, params=None):
        self.queries.append((q.strip(), params or {}))
        if "FROM agent_spec" in q:
            return [self._stranded]
        if "FROM arm_run" in q:
            return [self._running]
        return [[]]


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
async def test_a_spec_stuck_in_building_with_no_live_run_is_released():
    """The production case: a spec 'building' since forever, with no arm_run to explain it."""
    from core.engine.arms.run_ledger import reconcile_stranded_specs

    db = _FakeDB(stranded=[{"id": "agent_spec:ghost", "updated_at": None}], running_runs=[])
    n = await reconcile_stranded_specs(product_id="product:platform", pool=_FakePool(db))

    assert n == 1
    writes = [(q, p) for q, p in db.queries if "SET status" in q]
    assert writes, "the stranded spec must be released"
    assert writes[0][1]["st"] == "approved", (
        "released to APPROVED, not blocked — a crashed process is not a broken environment. If the "
        "environment IS dead, the retry will park and block it. Blocking here would strand real work."
    )


@pytest.mark.asyncio
async def test_a_spec_with_a_LIVE_run_is_never_touched():
    """The race that would otherwise cause a double build: another ACE process is building it RIGHT
    NOW. Releasing that spec would hand the same work to a second builder."""
    from core.engine.arms.run_ledger import reconcile_stranded_specs

    db = _FakeDB(
        stranded=[{"id": "agent_spec:live", "updated_at": None}],
        running_runs=[{"id": "arm_run:1", "spec": "agent_spec:live"}],  # someone IS building it
    )
    n = await reconcile_stranded_specs(product_id="product:platform", pool=_FakePool(db))

    assert n == 0, "a spec with a live run is IN FLIGHT — releasing it would double-build the work"
    assert not [q for q, _p in db.queries if "SET status" in q]


@pytest.mark.asyncio
async def test_reconcile_is_fail_safe():
    from core.engine.arms.run_ledger import reconcile_stranded_specs

    class _Dead:
        def connection(self):
            raise RuntimeError("db gone")

    assert await reconcile_stranded_specs(product_id="p:1", pool=_Dead()) == 0


@pytest.mark.asyncio
async def test_build_spec_stamps_updated_at_so_the_race_window_is_closable(monkeypatch):
    """Without a timestamp on the 'building' transition there is no way to tell 'crashed an hour ago'
    from 'started 3 milliseconds ago', and reconciliation cannot be made safe."""
    import core.engine.arms.builder as builder

    class _DB:
        def __init__(self):
            self.queries = []

        async def query(self, q, params=None):
            self.queries.append((q.strip(), params or {}))
            if "SELECT objective" in q:
                return [[{"objective": "x", "status": "approved"}]]
            return []

    db = _DB()

    async def _dispatch(sol, product_id="product:platform"):
        return None  # no arm handles it — build_spec restores the prior status and returns

    monkeypatch.setattr("core.engine.arms.dispatch.dispatch_solution", _dispatch)

    await builder.build_spec("agent_spec:x", pool=_FakePool(db))

    building = [q for q, _p in db.queries if "building" in q]
    assert building, "build_spec must mark the spec building"
    assert "updated_at" in building[0], "and must stamp WHEN — reconciliation depends on it"


@pytest.mark.asyncio
async def test_the_session_reconciles_stranded_specs_before_it_builds(monkeypatch):
    """Reachability: an unreached reconciler is a stranded spec that stays stranded."""
    import core.engine.arms.session as session

    called = {}

    async def _stranded(product_id, pool=None):
        called["yes"] = True
        return 1

    async def _runs(product_id, pool=None):
        return 0

    async def _no_work(product_id, pool=None):
        return None

    monkeypatch.setattr(session, "reconcile_stranded_specs", _stranded)
    monkeypatch.setattr(session, "reconcile_stale_runs", _runs)
    monkeypatch.setattr(session, "_next_buildable_spec", _no_work)

    out = await session.run_build_session(product_id="product:platform")

    assert called.get("yes") is True, "the session must release stranded specs — else work stays lost"
    assert out["released_specs"] == 1
