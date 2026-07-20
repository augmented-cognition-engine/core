"""The unattended build session — many builds, one walk away.

Everything before this made a SINGLE build durable, honest and self-repairing. This is the loop
that lets you leave: pick the next approved spec, build it in a fresh dispatch, record what
happened, decide whether to keep going.

The decisions that make it safe to leave are all about WHEN TO STOP:

  - PARKED stops the session dead. The environment is broken; every subsequent build would park
    against the same dead model, so continuing is a token furnace that produces a pile of
    identical non-results. Stop, and leave a diagnosis.
  - FAILED continues. That spec was wrong; the next one may be fine. But N failures IN A ROW
    means something systemic (a bad model, a poisoned dep, a broken repo) and the loop stops
    rather than grinding through the whole backlog producing garbage.
  - A parked spec is marked BLOCKED, never returned to 'approved'. Requeueing it would have the
    loop pick it up again, park again on the same dead environment, forever.
"""

from __future__ import annotations

import pytest


class _FakeDB:
    def __init__(self, script=None):
        self.queries: list[tuple[str, dict]] = []
        self.script = script or []
        self._i = 0

    async def query(self, q, params=None):
        self.queries.append((q.strip(), params or {}))
        if self._i < len(self.script):
            out = self.script[self._i]
            self._i += 1
            return out
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


@pytest.mark.asyncio
async def test_session_builds_specs_until_the_work_runs_out(monkeypatch):
    import core.engine.arms.session as session

    queue = ["agent_spec:a", "agent_spec:b"]
    built: list[str] = []

    async def _next_spec(product_id, pool=None, exclude=None):
        return queue.pop(0) if queue else None

    async def _build(spec_id, product_id="product:platform", pool=None):
        built.append(spec_id)
        return {"built": True, "branch": f"arm/{spec_id[-1]}"}

    monkeypatch.setattr(session, "_next_buildable_spec", _next_spec)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop_reconcile)

    out = await session.run_build_session(product_id="product:platform", max_builds=10)

    assert built == ["agent_spec:a", "agent_spec:b"]
    assert out["stopped_because"] == "no work left"
    assert len(out["built"]) == 2


async def _noop_reconcile(*a, **kw):
    return 0


@pytest.mark.asyncio
async def test_a_parked_build_stops_the_session_dead(monkeypatch):
    """The token-furnace guard: a dead model does not heal, so every further build would park
    identically. Stop and say why."""
    import core.engine.arms.session as session

    attempts: list[str] = []

    async def _next_spec(product_id, pool=None, exclude=None):
        return f"agent_spec:{len(attempts)}"  # infinite work available

    async def _build(spec_id, product_id="product:platform", pool=None):
        attempts.append(spec_id)
        return {"built": False, "parked": True, "diagnosis": "LLMError: model unreachable"}

    monkeypatch.setattr(session, "_next_buildable_spec", _next_spec)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop_reconcile)

    out = await session.run_build_session(product_id="product:platform", max_builds=50)

    assert len(attempts) == 1, "a parked build must halt the loop IMMEDIATELY — not 50 times"
    assert out["stopped_because"] == "parked"
    assert "unreachable" in out["diagnosis"]
    assert out["needs_human"] is True


@pytest.mark.asyncio
async def test_a_failed_build_does_not_stop_the_session(monkeypatch):
    """A wrong spec is not a broken engine. Move on."""
    import core.engine.arms.session as session

    results = [{"built": False, "reason": "tests red"}, {"built": True}, {"built": True}]
    seen: list[str] = []

    async def _next_spec(product_id, pool=None, exclude=None):
        return f"agent_spec:{len(seen)}" if len(seen) < 3 else None

    async def _build(spec_id, product_id="product:platform", pool=None):
        seen.append(spec_id)
        return results[len(seen) - 1]

    monkeypatch.setattr(session, "_next_buildable_spec", _next_spec)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop_reconcile)

    out = await session.run_build_session(product_id="product:platform", max_builds=10)

    assert len(seen) == 3, "one bad spec must not abort the backlog"
    assert len(out["built"]) == 2
    assert len(out["failed"]) == 1


@pytest.mark.asyncio
async def test_consecutive_failures_stop_the_session(monkeypatch):
    """Failing every single time is not bad luck — it is a broken engine grinding the backlog
    into garbage. Stop and make a human look."""
    import core.engine.arms.session as session
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "build_session_failure_ceiling", 3)
    seen: list[str] = []

    async def _next_spec(product_id, pool=None, exclude=None):
        return f"agent_spec:{len(seen)}"  # endless work

    async def _build(spec_id, product_id="product:platform", pool=None):
        seen.append(spec_id)
        return {"built": False, "reason": "tests red"}

    monkeypatch.setattr(session, "_next_buildable_spec", _next_spec)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop_reconcile)

    out = await session.run_build_session(product_id="product:platform", max_builds=100)

    assert len(seen) == 3, "stop at the ceiling, not at max_builds"
    assert out["stopped_because"] == "too many consecutive failures"
    assert out["needs_human"] is True


@pytest.mark.asyncio
async def test_a_success_resets_the_consecutive_failure_count(monkeypatch):
    import core.engine.arms.session as session
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "build_session_failure_ceiling", 3)
    outcomes = [
        {"built": False, "reason": "x"},
        {"built": False, "reason": "x"},
        {"built": True},  # resets the streak
        {"built": False, "reason": "x"},
        {"built": False, "reason": "x"},
    ]
    seen: list[str] = []

    async def _next_spec(product_id, pool=None, exclude=None):
        return f"agent_spec:{len(seen)}" if len(seen) < len(outcomes) else None

    async def _build(spec_id, product_id="product:platform", pool=None):
        seen.append(spec_id)
        return outcomes[len(seen) - 1]

    monkeypatch.setattr(session, "_next_buildable_spec", _next_spec)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop_reconcile)

    out = await session.run_build_session(product_id="product:platform", max_builds=100)

    assert len(seen) == 5, "the streak resets on success — 2 then 2 never hits a ceiling of 3"
    assert out["stopped_because"] == "no work left"


@pytest.mark.asyncio
async def test_max_builds_is_a_hard_ceiling(monkeypatch):
    import core.engine.arms.session as session

    seen: list[str] = []

    async def _next_spec(product_id, pool=None, exclude=None):
        return f"agent_spec:{len(seen)}"  # endless

    async def _build(spec_id, product_id="product:platform", pool=None):
        seen.append(spec_id)
        return {"built": True}

    monkeypatch.setattr(session, "_next_buildable_spec", _next_spec)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop_reconcile)

    out = await session.run_build_session(product_id="product:platform", max_builds=4)

    assert len(seen) == 4
    assert out["stopped_because"] == "budget exhausted"


@pytest.mark.asyncio
async def test_session_reconciles_zombie_runs_before_it_starts(monkeypatch):
    """A killed process leaves 'running' rows forever. Reconcile them, or the attention list slowly
    fills with zombies and the parked signal becomes noise."""
    import core.engine.arms.session as session

    called = {}

    async def _reconcile(product_id, pool=None):
        called["yes"] = True
        return 2

    async def _next_spec(product_id, pool=None, exclude=None):
        return None

    monkeypatch.setattr(session, "reconcile_stale_runs", _reconcile)
    monkeypatch.setattr(session, "_next_buildable_spec", _next_spec)

    out = await session.run_build_session(product_id="product:platform")

    assert called.get("yes") is True
    assert out["reconciled_zombies"] == 2


@pytest.mark.asyncio
async def test_a_broken_queue_read_is_never_reported_as_no_work_left(monkeypatch):
    """The lying instrument to avoid: if the DB read fails and we return None, the loop reads it as
    'the backlog is empty, everything is done' — a broken database reporting as a clean sweep. A
    queue we cannot read is an ERROR that needs a human, not an absence of work."""
    import core.engine.arms.session as session

    class _Dead:
        def connection(self):
            raise RuntimeError("surreal refused the connection")

    monkeypatch.setattr(session, "reconcile_stale_runs", _noop_reconcile)

    out = await session.run_build_session(product_id="product:platform", pool=_Dead())

    assert out["stopped_because"] != "no work left", "a dead DB must NEVER read as a finished backlog"
    assert out["stopped_because"] == "error"
    assert out["needs_human"] is True


@pytest.mark.asyncio
async def test_session_never_raises(monkeypatch):
    """It runs unattended. It does not get to crash."""
    import core.engine.arms.session as session

    async def _boom(*a, **kw):
        raise RuntimeError("everything is on fire")

    monkeypatch.setattr(session, "reconcile_stale_runs", _noop_reconcile)
    monkeypatch.setattr(session, "_next_buildable_spec", _boom)

    out = await session.run_build_session(product_id="product:platform")

    assert out["stopped_because"] == "error"
    assert "on fire" in out["diagnosis"]
    assert out["needs_human"] is True
