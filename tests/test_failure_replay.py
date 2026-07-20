# tests/test_failure_replay.py
"""Tests for failure replay / counterfactual detection.

The counterfactual: when a task fails with gap patterns similar to a prior
failure_memory entry, the intelligence didn't prevent the repeat — that's a
measurable learning failure.

This module detects repeat-failure patterns. True end-to-end replay (re-running
the LLM with memory injected) is a future enhancement — the measurable signal
is "did the system already know?" which is what this detector answers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def test_gap_overlap_identical_is_one():
    from core.engine.intelligence.failure_replay import _gap_overlap

    assert _gap_overlap(["no input validation"], ["no input validation"]) == pytest.approx(1.0)


def test_gap_overlap_disjoint_is_zero():
    from core.engine.intelligence.failure_replay import _gap_overlap

    assert _gap_overlap(["missing auth"], ["weird typo"]) == 0.0


def test_gap_overlap_case_insensitive():
    from core.engine.intelligence.failure_replay import _gap_overlap

    assert _gap_overlap(["No Input Validation"], ["no input validation"]) == pytest.approx(1.0)


def test_gap_overlap_empty_lists_is_zero():
    from core.engine.intelligence.failure_replay import _gap_overlap

    assert _gap_overlap([], []) == 0.0
    assert _gap_overlap(["x"], []) == 0.0


@pytest.mark.asyncio
async def test_detect_repeat_failures_returns_high_overlap_priors():
    from core.engine.intelligence.failure_replay import detect_repeat_failures

    existing = [
        {"id": "fm:1", "gaps": ["no input validation", "weak auth"], "task_summary": "prior"},
        {"id": "fm:2", "gaps": ["completely different thing"], "task_summary": "other"},
    ]

    async def fake_query(sql, params=None):
        return [existing]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    repeats = await detect_repeat_failures(
        db=mock_db,
        product_id="product:test",
        discipline="security",
        gaps=["no input validation", "weak auth"],
    )
    ids = [r["id"] for r in repeats]
    assert "fm:1" in ids
    assert "fm:2" not in ids


@pytest.mark.asyncio
async def test_detect_repeat_failures_below_threshold_empty():
    from core.engine.intelligence.failure_replay import detect_repeat_failures

    async def fake_query(sql, params=None):
        return [[{"id": "fm:x", "gaps": ["unrelated"], "task_summary": "other"}]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    repeats = await detect_repeat_failures(
        db=mock_db,
        product_id="product:test",
        discipline="security",
        gaps=["nothing in common"],
    )
    assert repeats == []


@pytest.mark.asyncio
async def test_detect_repeat_failures_db_error_non_fatal():
    from core.engine.intelligence.failure_replay import detect_repeat_failures

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("db gone"))

    repeats = await detect_repeat_failures(db=mock_db, product_id="product:test", discipline="security", gaps=["x"])
    assert repeats == []


@pytest.mark.asyncio
async def test_write_failure_memory_end_to_end_flags_repeat():
    """Sentinel boundary: _write_failure_memory integrates detect_repeat_failures + record_repeat_failure."""
    from unittest.mock import patch

    from core.engine.orchestration.executor import _write_failure_memory

    prior = {
        "id": "failure_memory:prior",
        "task_summary": "prior",
        "gaps": ["no input validation", "weak auth"],
    }
    new_row = {"id": "failure_memory:new"}

    calls: list[tuple[str, dict]] = []

    async def fake_query(sql, params=None):
        calls.append((sql, params or {}))
        if "SELECT id, task_summary, gaps, created_at" in sql:
            return [[prior]]
        if "CREATE failure_memory" in sql:
            return [[new_row]]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    class _FakePool:
        def connection(self):
            class _Conn:
                async def __aenter__(self_inner):
                    return mock_db

                async def __aexit__(self_inner, *a):
                    pass

            return _Conn()

    emitted: list[tuple[str, dict]] = []

    class _FakeBus:
        async def emit(self, event, payload):
            emitted.append((event, payload))

    with patch("core.engine.core.db.pool", _FakePool()):
        with patch("core.engine.events.bus.bus", _FakeBus()):
            await _write_failure_memory(
                product_id="product:test",
                discipline="security",
                task_summary="new run",
                gaps=["no input validation", "weak auth"],
                verdict="gaps_found",
            )

    # CREATE must carry is_repeat=true
    create_calls = [(s, p) for s, p in calls if "CREATE failure_memory" in s]
    assert create_calls
    assert create_calls[0][1].get("is_repeat") is True

    # Event must be emitted
    assert any(ev == "failure.repeat_detected" for ev, _ in emitted)


@pytest.mark.asyncio
async def test_record_repeat_flag_emits_event():
    """When a repeat is detected the caller should emit failure.repeat_detected."""
    from core.engine.intelligence.failure_replay import record_repeat_failure

    emitted: list[tuple[str, dict]] = []

    class _FakeBus:
        async def emit(self, event, payload):
            emitted.append((event, payload))

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    await record_repeat_failure(
        db=mock_db,
        bus=_FakeBus(),
        product_id="product:test",
        new_failure_id="failure_memory:new",
        repeat_of_ids=["failure_memory:prior"],
    )

    assert emitted
    event, payload = emitted[0]
    assert event == "failure.repeat_detected"
    assert payload["product_id"] == "product:test"
    assert payload["new_failure_id"] == "failure_memory:new"
    assert "failure_memory:prior" in payload["repeat_of"]
