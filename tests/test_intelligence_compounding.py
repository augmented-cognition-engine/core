# tests/test_intelligence_compounding.py
"""Tests for task_class_duration tracking — ACE's compounding proof-metric.

Buckets tasks by (discipline, class_hash) so identical/near-identical task
descriptions can be trended over time. If intelligence compounds, recurring
task classes get faster. If they don't, the metric exposes the failure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def test_task_class_hash_is_stable_across_runs():
    """Same description → same hash (deterministic)."""
    from core.engine.intelligence.compounding import task_class_hash

    h1 = task_class_hash("refactor auth module to use middleware")
    h2 = task_class_hash("refactor auth module to use middleware")
    assert h1 == h2


def test_task_class_hash_ignores_case_and_whitespace():
    """Normalization: upper/lower and extra spaces don't change the bucket."""
    from core.engine.intelligence.compounding import task_class_hash

    assert task_class_hash("Refactor Auth Module") == task_class_hash("refactor  auth module")


def test_task_class_hash_differentiates_distinct_tasks():
    """Genuinely different descriptions → different hashes."""
    from core.engine.intelligence.compounding import task_class_hash

    a = task_class_hash("refactor auth module")
    b = task_class_hash("add dark mode toggle")
    assert a != b


@pytest.mark.asyncio
async def test_record_task_duration_writes_row():
    """record_task_duration must INSERT into task_class_duration with the right fields."""
    from core.engine.intelligence.compounding import record_task_duration

    captured: list[tuple[str, dict]] = []

    async def fake_query(sql, params=None):
        captured.append((sql, params or {}))
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await record_task_duration(
        db=mock_db,
        product_id="product:test",
        description="refactor auth module",
        discipline="architecture",
        duration_ms=15_000,
        token_total=4200,
    )

    assert captured
    sql, params = captured[0]
    assert "CREATE task_class_duration" in sql or "task_class_duration" in sql
    assert params.get("duration_ms") == 15_000
    assert params.get("token_total") == 4200
    assert params.get("discipline") == "architecture"
    assert params.get("class_hash")
    assert params.get("description_sample")


@pytest.mark.asyncio
async def test_record_task_duration_failure_non_fatal():
    """DB failure must not propagate — compounding metric is best-effort."""
    from core.engine.intelligence.compounding import record_task_duration

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("db gone"))

    # Must not raise
    await record_task_duration(
        db=mock_db,
        product_id="product:test",
        description="x",
        discipline="testing",
        duration_ms=1,
        token_total=1,
    )


@pytest.mark.asyncio
async def test_compounding_hook_writes_via_hookcontext():
    """Sentinel boundary: compounding_hook with live HookContext triggers a task_class_duration INSERT."""
    import time as real_time
    from unittest.mock import patch

    from core.engine.orchestration.hooks import HookContext, compounding_hook

    ctx = HookContext(
        task_id="task:abc",
        product_id="product:test",
        domain_path="architecture",
        output="ok",
        snapshot={},
        classification={"discipline": "architecture"},
        task_description="refactor auth module",
        started_at=real_time.time() - 3.0,  # simulate 3s duration
    )

    captured: list[tuple[str, dict]] = []

    class _FakeDB:
        async def query(self, sql, params=None):
            captured.append((sql, params or {}))
            return [[]]

    class _FakePool:
        def connection(self):
            class _Conn:
                async def __aenter__(self_inner):
                    return _FakeDB()

                async def __aexit__(self_inner, *a):
                    pass

            return _Conn()

    with patch("core.engine.orchestration.hooks.pool", _FakePool()):
        await compounding_hook(ctx)

    assert any("task_class_duration" in sql for sql, _ in captured)
    # Duration should be ≈ 3000ms
    inserted = captured[0][1]
    assert 2500 <= inserted.get("duration_ms", 0) <= 4000


@pytest.mark.asyncio
async def test_compounding_hook_skips_without_start_time():
    """Missing started_at or task_description → hook does nothing."""
    from core.engine.orchestration.hooks import HookContext, compounding_hook

    ctx = HookContext(
        task_id="task:abc",
        product_id="product:test",
        domain_path="architecture",
        output="",
        snapshot={},
        classification={"discipline": "architecture"},
        # no task_description, no started_at
    )

    # Must not raise; pool is not patched because it must never be reached.
    await compounding_hook(ctx)


@pytest.mark.asyncio
async def test_get_class_trajectory_returns_chronological():
    """get_class_trajectory returns duration history ordered by completed_at."""
    from core.engine.intelligence.compounding import get_class_trajectory

    rows = [
        {"duration_ms": 30_000, "token_total": 8000, "completed_at": "2026-01-01T00:00:00Z"},
        {"duration_ms": 15_000, "token_total": 4200, "completed_at": "2026-02-15T00:00:00Z"},
        {"duration_ms": 9_000, "token_total": 2500, "completed_at": "2026-04-01T00:00:00Z"},
    ]

    async def fake_query(sql, params=None):
        assert "ORDER BY completed_at" in sql
        return [rows]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    traj = await get_class_trajectory(mock_db, "product:test", "abc123")
    assert [r["duration_ms"] for r in traj] == [30_000, 15_000, 9_000]
