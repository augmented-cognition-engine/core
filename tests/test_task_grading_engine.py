"""Task-grading sentinel engine — cross-model grade recent ungraded tasks to un-starve calibration.

Gated on a configured cross-model peer (same-family grading doesn't un-starve anything); off the hot
path; non-fatal per task. See docs/superpowers/specs/2026-06-23-calibration-consumer-cross-model-grades-design.md.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import core.engine.core.config as cfg


class _FakeGrader:
    def __init__(self, scores=None, raise_on=None):
        self._scores = scores or {}
        self._raise_on = raise_on or set()
        self.calls = []

    async def evaluate(self, task, rubric, artifact):
        self.calls.append((task, artifact))
        if task in self._raise_on:
            raise RuntimeError("grader boom")
        return {"score": self._scores.get(task, 0.8), "met_count": 3, "total": 4}


def _mock_pool(select_rows):
    """Build a patched pool whose SELECT returns select_rows and records UPDATEs into `updates`."""
    updates = []
    mock_pool = MagicMock()
    mock_conn = MagicMock()

    async def mock_query(query_str, params=None):
        if query_str.strip().startswith("UPDATE") or "UPDATE <record>$tid" in query_str:
            updates.append(params)
            return [[]]
        if "FROM task" in query_str:
            return [select_rows]
        return [[]]

    mock_conn.query = mock_query
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, updates


def _fires_on(cron: str) -> set[str]:
    """The days a cron ACTUALLY fires, in APScheduler's reading of it.

    Asserting the cron STRING is the weak form and it is how this bug lived: the old
    assertion here was `== "0 5 * * 0"  # Sunday 5 AM`, which passed for months while the
    engine ran on MONDAY. APScheduler reads day-of-week 0=mon..6=sun, not the standard
    crontab 0=sun, and does not translate. Assert the behaviour, not the literal.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apscheduler.triggers.cron import CronTrigger

    tz = ZoneInfo("UTC")
    trigger = CronTrigger.from_crontab(cron, timezone=tz)
    days, prev = set(), datetime(2026, 7, 12, tzinfo=tz)  # a Sunday
    for _ in range(7):
        nxt = trigger.get_next_fire_time(None, prev)
        days.add(nxt.strftime("%A"))
        prev = nxt.replace(hour=23, minute=59)
    return days


def test_engine_registered():
    from core.engine.sentinel.engines.task_grading_engine import run_task_grading  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "task_grading" in engine_registry
    assert _fires_on(engine_registry["task_grading"]["cron"]) == {"Saturday"}


@pytest.mark.asyncio
async def test_engine_skips_when_no_peer(monkeypatch):
    """No cross-model peer → no-op. Same-family grading wouldn't un-starve calibration, so don't grade."""
    from core.engine.sentinel.engines import task_grading_engine as eng

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", None, raising=False)
    make_grader_spy = patch.object(eng, "make_grader")
    pool_spy = patch.object(eng, "pool")
    with make_grader_spy as mg, pool_spy as mp:
        result = await eng.run_task_grading("product:test")
    assert result == {"graded": 0, "reason": "no_cross_model_peer"}
    mg.assert_not_called()
    mp.connection.assert_not_called()


@pytest.mark.asyncio
async def test_engine_grades_and_writes_score(monkeypatch):
    """Peer configured → grade each selected task and UPDATE grader_score + grader_source."""
    from core.engine.sentinel.engines import task_grading_engine as eng

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", "http://localhost:11434", raising=False)
    monkeypatch.setattr(cfg.settings, "cross_model_grader_model", "qwen2.5-coder:14b", raising=False)

    rows = [
        {"id": "task:a", "description": "do A", "output": "result A"},
        {"id": "task:b", "description": "do B", "output": "result B"},
    ]
    mock_pool, updates = _mock_pool(rows)
    fake = _FakeGrader(scores={"do A": 0.8, "do B": 0.4})

    with patch.object(eng, "pool", mock_pool), patch.object(eng, "make_grader", return_value=fake):
        result = await eng.run_task_grading("product:test")

    assert result["graded"] == 2
    assert result["source"] == "cross_model:qwen2.5-coder:14b"
    assert len(updates) == 2
    by_tid = {u["tid"]: u for u in updates}
    assert by_tid["task:a"]["score"] == 0.8
    assert by_tid["task:b"]["score"] == 0.4
    assert all(u["source"] == "cross_model:qwen2.5-coder:14b" for u in updates)


@pytest.mark.asyncio
async def test_engine_per_task_failure_is_non_fatal(monkeypatch):
    """A grader failure on one task must not abort the batch; the others still get written."""
    from core.engine.sentinel.engines import task_grading_engine as eng

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", "http://localhost:11434", raising=False)
    rows = [
        {"id": "task:a", "description": "do A", "output": "result A"},
        {"id": "task:b", "description": "do B", "output": "result B"},
        {"id": "task:c", "description": "do C", "output": "result C"},
    ]
    mock_pool, updates = _mock_pool(rows)
    fake = _FakeGrader(scores={"do A": 0.9, "do C": 0.7}, raise_on={"do B"})

    with patch.object(eng, "pool", mock_pool), patch.object(eng, "make_grader", return_value=fake):
        result = await eng.run_task_grading("product:test")

    assert result["graded"] == 2  # A and C; B raised and was skipped
    assert {u["tid"] for u in updates} == {"task:a", "task:c"}


@pytest.mark.asyncio
async def test_engine_skips_errored_grade(monkeypatch):
    """evaluate() returns {"score": 0.0, "error": ...} on failure (never raises). The engine must NOT
    persist that 0.0 (a sentinel, not a real failed outcome) nor count it — it would poison the curve."""
    from core.engine.sentinel.engines import task_grading_engine as eng

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", "http://localhost:11434", raising=False)
    rows = [
        {"id": "task:ok", "description": "do A", "output": "result A"},
        {"id": "task:err", "description": "do B", "output": "result B"},
    ]
    mock_pool, updates = _mock_pool(rows)

    class _MixedGrader:
        async def evaluate(self, task, rubric, artifact):
            if task == "do B":
                return {"score": 0.0, "met_count": 0, "total": 4, "error": "peer unreachable"}
            return {"score": 0.9, "met_count": 4, "total": 4}

    with patch.object(eng, "pool", mock_pool), patch.object(eng, "make_grader", return_value=_MixedGrader()):
        result = await eng.run_task_grading("product:test")

    assert result["graded"] == 1, "only the clean grade counts; the errored one is skipped"
    assert {u["tid"] for u in updates} == {"task:ok"}, "the errored grade must not be persisted"


@pytest.mark.asyncio
async def test_engine_uses_fail_closed_grader(monkeypatch):
    """The engine must request a FAIL-CLOSED grader (allow_fallback=False) so a down peer never gets
    silently Claude-graded and mislabeled cross_model."""
    from core.engine.sentinel.engines import task_grading_engine as eng

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", "http://localhost:11434", raising=False)
    captured = {}

    def fake_make_grader(allow_fallback=True):
        captured["allow_fallback"] = allow_fallback
        return _FakeGrader()

    mock_pool, _ = _mock_pool([])
    with patch.object(eng, "pool", mock_pool), patch.object(eng, "make_grader", fake_make_grader):
        await eng.run_task_grading("product:test")

    assert captured["allow_fallback"] is False


@pytest.mark.asyncio
async def test_engine_selects_only_ungraded_unfed_tasks(monkeypatch):
    """The selection predicate must exclude already-graded, human-judged, and output-less tasks."""
    from core.engine.sentinel.engines import task_grading_engine as eng

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", "http://localhost:11434", raising=False)
    captured = {}

    mock_pool = MagicMock()
    mock_conn = MagicMock()

    async def mock_query(query_str, params=None):
        if "FROM task" in query_str:
            captured["select"] = query_str
            return [[]]
        return [[]]

    mock_conn.query = mock_query
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(eng, "pool", mock_pool), patch.object(eng, "make_grader", return_value=_FakeGrader()):
        result = await eng.run_task_grading("product:test")

    sel = captured["select"]
    assert "feedback_human IS NONE" in sel
    assert "grader_score IS NONE" in sel
    assert "output IS NOT NONE" in sel
    assert result == {"graded": 0, "reason": "no_ungraded_tasks"}


@pytest.mark.asyncio
async def test_engine_rejects_bad_budget(monkeypatch):
    from core.engine.core.exceptions import ValidationError
    from core.engine.sentinel.engines import task_grading_engine as eng

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", "http://localhost:11434", raising=False)
    with pytest.raises(ValidationError):
        await eng.run_task_grading("product:test", budget=0)
    with pytest.raises(ValidationError):
        await eng.run_task_grading("bad_id", budget=10)
