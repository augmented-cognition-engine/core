# tests/test_star_trace.py
"""Tests for star_trace DB helpers — write/load successful reasoning traces."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(rows=None):
    db = AsyncMock()
    db.query = AsyncMock(return_value=rows or [[]])
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


# test_write_star_trace_stores_record: writes to star_trace table
@pytest.mark.asyncio
async def test_write_star_trace_stores_record():
    pool = _make_pool()

    with patch("core.engine.core.db.pool", pool):
        from core.engine.cognition.star_trace import write_star_trace

        await write_star_trace(
            pool=pool,
            product_id="product:test",
            discipline="api_design",
            task_description="Add rate limiting",
            phase_traces=[{"phase_idx": 0, "cognitive_function": "analysis", "confidence": 0.9}],
            final_output="The rate limiter uses token bucket algorithm.",
        )

    db = pool.connection.return_value.__aenter__.return_value
    db.query.assert_called_once()
    params = db.query.call_args[0][1]
    assert params["data"]["discipline"] == "api_design"
    assert params["data"]["product"] == "product:test"
    assert len(params["data"]["phase_traces"]) == 1
    assert params["data"]["task_description"] == "Add rate limiting"


# test_write_star_trace_nonfatal: DB error does not raise
@pytest.mark.asyncio
async def test_write_star_trace_nonfatal():
    db = AsyncMock()
    db.query = AsyncMock(side_effect=RuntimeError("DB down"))
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm

    with patch("core.engine.core.db.pool", pool):
        from core.engine.cognition.star_trace import write_star_trace

        # Should not raise
        await write_star_trace(
            pool=pool,
            product_id="product:test",
            discipline="testing",
            task_description="Write tests",
            phase_traces=[],
            final_output="Tests written.",
        )


# test_load_star_traces_returns_list: returns list of trace dicts for discipline
@pytest.mark.asyncio
async def test_load_star_traces_returns_list():
    rows = [
        [
            {
                "discipline": "api_design",
                "task_description": "Add auth",
                "final_output": "JWT-based auth implemented.",
                "phase_traces": [{"phase_idx": 0, "confidence": 0.85}],
            }
        ]
    ]
    pool = _make_pool(rows)

    with patch("core.engine.core.db.pool", pool):
        from core.engine.cognition.star_trace import load_star_traces

        traces = await load_star_traces(pool, "product:test", "api_design", limit=3)

    assert len(traces) == 1
    assert traces[0]["task_description"] == "Add auth"


# test_load_star_traces_empty: no records → empty list
@pytest.mark.asyncio
async def test_load_star_traces_empty():
    pool = _make_pool([[]])

    with patch("core.engine.core.db.pool", pool):
        from core.engine.cognition.star_trace import load_star_traces

        traces = await load_star_traces(pool, "product:test", "security", limit=3)

    assert traces == []
