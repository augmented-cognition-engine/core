"""Tests for the append-only reasoning_event log (evolve run_ledger).

run_ledger now emits immutable events alongside the mutable reasoning_run row: run_started (live at
create_run), one phase event per phase + run_complete/run_failed at finalize_run — each with a
monotonic seq. Fail-safe: event emission never blocks the run-row writes. See
docs/superpowers/specs/2026-06-22-reasoning-event-log-design.md.
"""

from __future__ import annotations

import pytest


class _RecDB:
    """Records every query; returns an id-bearing row for CREATEs so run ids resolve."""

    def __init__(self, fail_on: str | None = None):
        self.queries: list = []  # (sql, params)
        self._fail_on = fail_on  # substring; raise when a query contains it

    async def query(self, sql, params=None):
        self.queries.append((sql, params))
        if self._fail_on and self._fail_on in sql:
            raise RuntimeError("boom")
        u = sql.strip().upper()
        if u.startswith("CREATE REASONING_RUN"):
            return [{"id": "reasoning_run:r1"}]
        if u.startswith("CREATE REASONING_EVENT"):
            return [{"id": "reasoning_event:e1"}]
        if u.startswith("SELECT"):
            return []
        return []


class _RecPool:
    def __init__(self, db):
        self._db = db

    def connection(self):
        db = self._db

        class _Ctx:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def _patch_pool(monkeypatch, db):
    import core.engine.core.db as dbmod

    monkeypatch.setattr(dbmod, "pool", _RecPool(db))


def _events(db):
    return [(s, p) for (s, p) in db.queries if "reasoning_event" in s.lower()]


@pytest.mark.asyncio
async def test_append_event_creates_row(monkeypatch):
    from core.engine.cognition import run_ledger

    db = _RecDB()
    _patch_pool(monkeypatch, db)
    eid = await run_ledger.append_event("reasoning_run:r1", "phase", {"fn": "explore"}, seq=2)

    assert eid == "reasoning_event:e1"
    ev = _events(db)
    assert len(ev) == 1
    sql, params = ev[0]
    assert "CREATE reasoning_event" in sql
    assert params.get("seq") == 2
    assert params.get("event_type") == "phase"


@pytest.mark.asyncio
async def test_append_event_non_fatal(monkeypatch):
    from core.engine.cognition import run_ledger

    db = _RecDB(fail_on="reasoning_event")
    _patch_pool(monkeypatch, db)
    eid = await run_ledger.append_event("reasoning_run:r1", "phase", {}, seq=1)
    assert eid is None  # raised internally, swallowed


@pytest.mark.asyncio
async def test_create_run_emits_run_started_seq0(monkeypatch):
    from core.engine.cognition import run_ledger

    db = _RecDB()
    _patch_pool(monkeypatch, db)
    rid = await run_ledger.create_run(
        product_id="product:platform", thought="why is X slow", meta_skills=["m"], depth=2, discipline="perf"
    )

    assert rid == "reasoning_run:r1"
    ev = _events(db)
    assert len(ev) == 1, "create_run must emit exactly one run_started event"
    _, params = ev[0]
    assert params.get("event_type") == "run_started"
    assert params.get("seq") == 0


@pytest.mark.asyncio
async def test_finalize_emits_phase_events_then_complete(monkeypatch):
    from core.engine.cognition import run_ledger

    db = _RecDB()
    _patch_pool(monkeypatch, db)
    phases = [{"cognitive_function": "explore"}, {"cognitive_function": "synthesize"}]
    await run_ledger.finalize_run(
        run_id="reasoning_run:r1", conclusion="done", phases=phases, trace=[], status="complete"
    )

    ev = _events(db)
    types = [p.get("event_type") for _, p in ev]
    seqs = [p.get("seq") for _, p in ev]
    assert types == ["phase", "phase", "run_complete"]
    assert seqs == [1, 2, 3], "seq must be monotonic: phases then terminal"


@pytest.mark.asyncio
async def test_finalize_failed_emits_run_failed(monkeypatch):
    from core.engine.cognition import run_ledger

    db = _RecDB()
    _patch_pool(monkeypatch, db)
    await run_ledger.finalize_run(run_id="reasoning_run:r1", conclusion="", phases=[], trace=[], status="failed")
    types = [p.get("event_type") for _, p in _events(db)]
    assert types == ["run_failed"]


@pytest.mark.asyncio
async def test_finalize_event_failure_doesnt_block_run_update(monkeypatch):
    """If event emission fails, the primary reasoning_run UPDATE must still happen."""
    from core.engine.cognition import run_ledger

    db = _RecDB(fail_on="reasoning_event")
    _patch_pool(monkeypatch, db)
    await run_ledger.finalize_run(
        run_id="reasoning_run:r1", conclusion="c", phases=[{"x": 1}], trace=[], status="complete"
    )
    updates = [s for s, _ in db.queries if s.strip().upper().startswith("UPDATE")]
    assert updates, "the reasoning_run UPDATE must run even when event emit raises"


@pytest.mark.asyncio
async def test_get_run_events_orders_by_seq(monkeypatch):
    from core.engine.cognition import run_ledger

    db = _RecDB()
    _patch_pool(monkeypatch, db)
    await run_ledger.get_run_events("reasoning_run:r1")
    sel = [s for s, _ in db.queries if s.strip().upper().startswith("SELECT")]
    assert sel and "reasoning_event" in sel[0].lower()
    assert "seq" in sel[0].lower() and "order by seq" in sel[0].lower()
