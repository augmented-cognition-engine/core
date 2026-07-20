"""The arm run ledger — a long build must be durable, not in-memory.

Mirrors the reasoning ledger (cognition/run_ledger.py): a run row + an append-only,
seq-ordered event log, every write fail-safe and timeout-bounded. Without this, a
process killed mid-execute leaves NO trace — the first durable record of a build was
the outcome row at the very end.
"""

from __future__ import annotations

import pytest


def _only(arm):
    """Route to exactly this arm. dispatch now selects via router.choose_arm (the classifier), not
    the old keyword route() — patching route() here would be inert and the test would silently
    verify nothing."""

    async def _choose(solution, llm=None, producer_only=True):
        return arm

    return _choose


class _FakeDB:
    def __init__(self, rows=None, raises=None):
        self.queries: list[tuple[str, dict]] = []
        self._rows = rows if rows is not None else [{"id": "arm_run:abc"}]
        self._raises = raises

    async def query(self, q, params=None):
        self.queries.append((q.strip(), params or {}))
        if self._raises:
            raise self._raises
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
async def test_create_run_writes_a_running_row_and_returns_its_id():
    from core.engine.arms import run_ledger

    db = _FakeDB()
    run_id = await run_ledger.create_run(
        product_id="product:platform", intent="add the widget", arm_domain="code", pool=_FakePool(db)
    )

    assert run_id == "arm_run:abc"
    sql, params = db.queries[0]
    assert "CREATE arm_run" in sql
    assert "status = 'running'" in sql, "a run is durable BEFORE it does any work"
    assert params["intent"] == "add the widget"
    assert params["arm_domain"] == "code"


@pytest.mark.asyncio
async def test_checkpoint_appends_a_seq_ordered_event():
    from core.engine.arms import run_ledger

    db = _FakeDB(rows=[{"id": "arm_run_event:1"}])
    ev = await run_ledger.checkpoint("arm_run:abc", "executed", {"actions": 3}, seq=2, pool=_FakePool(db))

    assert ev == "arm_run_event:1"
    sql, params = db.queries[0]
    assert "CREATE arm_run_event" in sql
    assert params["seq"] == 2
    assert params["phase"] == "executed"
    assert params["payload"] == {"actions": 3}


@pytest.mark.asyncio
async def test_finalize_run_records_the_terminal_state_and_attempts():
    from core.engine.arms import run_ledger

    db = _FakeDB()
    await run_ledger.finalize_run(
        run_id="arm_run:abc", status="parked", reason="llm unreachable", attempts=1, pool=_FakePool(db)
    )

    sql, params = db.queries[0]
    assert "UPDATE" in sql
    assert params["status"] == "parked"
    assert params["attempts"] == 1


@pytest.mark.asyncio
async def test_runs_needing_attention_covers_parked_and_interrupted():
    """The single read for 'what is waiting on a human': builds the environment killed (parked)
    AND builds a dead process abandoned mid-flight (still 'running'). Both need a person; neither
    was ever judged. A FAILED build is deliberately absent — that one was judged, was wrong, and
    was discarded. It is a normal outcome, not an interruption."""
    from core.engine.arms import run_ledger

    db = _FakeDB(rows=[[{"id": "arm_run:abc", "status": "parked", "intent": "add the widget"}]])
    runs = await run_ledger.get_runs_needing_attention(product_id="product:platform", pool=_FakePool(db))

    assert len(runs) == 1
    assert runs[0]["intent"] == "add the widget"
    sql, _params = db.queries[0]
    assert "'parked'" in sql and "'running'" in sql
    assert "failed" not in sql, "a failed build was judged — it is not waiting on anyone"


@pytest.mark.asyncio
async def test_every_ledger_write_is_fail_safe():
    """Bookkeeping must NEVER break the build. A dead DB degrades to None/[], never raises."""
    from core.engine.arms import run_ledger

    dead = _FakePool(_FakeDB(raises=RuntimeError("db is gone")))

    assert await run_ledger.create_run(product_id="p:1", intent="i", arm_domain="code", pool=dead) is None
    assert await run_ledger.checkpoint("arm_run:x", "planned", {}, seq=1, pool=dead) is None
    assert await run_ledger.finalize_run(run_id="arm_run:x", status="failed", reason="", attempts=1, pool=dead) is None
    assert await run_ledger.get_runs_needing_attention(product_id="p:1", pool=dead) == []


@pytest.mark.asyncio
async def test_finalize_is_a_noop_without_a_run_id():
    from core.engine.arms import run_ledger

    db = _FakeDB()
    await run_ledger.finalize_run(run_id=None, status="verified", reason="", attempts=1, pool=_FakePool(db))
    assert db.queries == [], "no run id (DB was down at create) — nothing to finalize, and no crash"


@pytest.mark.asyncio
async def test_dispatch_ledgers_the_whole_lifecycle(monkeypatch):
    """Reachability: the ledger is not an orphan module — dispatch checkpoints through it."""
    import core.engine.arms.dispatch as dispatch
    import core.engine.arms.run_ledger as ledger
    from core.engine.arms.base import Action, ActionPlan, Arm, ArmResult, AutonomyTier, RiskTier, Verdict
    from core.engine.core.config import settings
    from core.engine.solution import Solution

    monkeypatch.setattr(settings, "arm_adversarial_review", False)
    phases: list[str] = []
    final: dict = {}

    async def _create(**kw):
        return "arm_run:test"

    async def _checkpoint(run_id, phase, payload, *, seq, pool=None):
        phases.append(phase)
        return "ev"

    async def _finalize(**kw):
        final.update(kw)

    monkeypatch.setattr(ledger, "create_run", _create)
    monkeypatch.setattr(ledger, "checkpoint", _checkpoint)
    monkeypatch.setattr(ledger, "finalize_run", _finalize)

    class _OK(Arm):
        domain = "ok"
        autonomy = AutonomyTier.REVERSIBLE

        def can_handle(self, s):
            return True

        async def plan(self, s):
            return ActionPlan(summary="x", actions=[Action(verb="w", args={}, risk=RiskTier.REVERSIBLE)])

        async def execute(self, plan):
            return ArmResult(plan=plan, performed=list(plan.actions), simulated=False)

        async def verify(self, result, plan):
            return Verdict(passed=True, reason="green")

    monkeypatch.setattr(dispatch.router, "choose_arm", _only(_OK()))

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    await dispatch.dispatch_solution(Solution(intent="build"))

    assert phases == ["planned", "executed", "verified"], "each phase is durable as it completes"
    assert final["status"] == "verified"
    assert final["attempts"] == 1
