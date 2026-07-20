"""load_loop_context — the L1 read that makes composition decision-informed.

Contract: NEVER raises, NEVER blocks past its deadline, returns {} on any
failure. The composer must stay safe to call in unit tests with no DB.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.orchestration.loop_context import _gather_context, load_loop_context


@pytest.mark.unit
async def test_returns_empty_dict_when_db_unavailable():
    with patch(
        "core.engine.orchestration.loop_context._gather_context",
        AsyncMock(side_effect=ConnectionError("no db")),
    ):
        result = await load_loop_context("product:platform", {"discipline": "ux", "thought": "x"})
    assert result == {}


@pytest.mark.unit
async def test_returns_empty_dict_on_timeout():
    async def slow(*a, **k):
        await asyncio.sleep(10)

    with patch("core.engine.orchestration.loop_context._gather_context", slow):
        result = await load_loop_context("product:platform", {"discipline": "ux", "thought": "x"}, deadline_s=0.05)
    assert result == {}


@pytest.mark.unit
async def test_shapes_context_from_gathered_rows():
    gathered = {
        "prior_decisions": [{"title": "Use SurrealDB", "rationale": "graph-native", "decision_type": "architecture"}],
        "calibration": [{"archetype": "analyst", "calibration_score": 0.82, "sample_count": 7}],
    }
    with patch(
        "core.engine.orchestration.loop_context._gather_context",
        AsyncMock(return_value=gathered),
    ):
        result = await load_loop_context("product:platform", {"discipline": "ux", "thought": "x"})
    assert result["prior_decisions"][0]["title"] == "Use SurrealDB"
    assert result["calibration"]["analyst"]["score"] == 0.82
    assert result["calibration"]["analyst"]["samples"] == 7


@pytest.mark.unit
async def test_recency_fallback_when_similarity_returns_empty():
    """When find_similar_decisions returns [], _gather_context falls back to
    list_decisions so the ledger always rides into composition.

    Proves the Amendment: Jaccard-vs-title nearly always misses free-form
    thoughts; recency is the honest fallback.
    """
    fallback_row = {
        "title": "Adopt SurrealDB as primary store",
        "rationale": "graph-native queries",
        "decision_type": "architecture",
        "outcome": "accepted",
    }

    with (
        patch(
            "core.engine.orchestration.loop_context.find_similar_decisions",
            AsyncMock(return_value=[]),
        ),
        patch(
            "core.engine.orchestration.loop_context.list_decisions",
            AsyncMock(return_value=[fallback_row]),
        ),
        patch("core.engine.orchestration.loop_context.pool") as mock_pool,
    ):
        # Minimal mock so the async-with pool.connection() doesn't error;
        # _gather_context only uses pool for the calibration query.
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[])  # no calibration rows
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        gathered = await _gather_context(
            "product:platform",
            {"discipline": "architecture", "thought": "how should we store things"},
        )

    assert gathered["prior_decisions"] == [fallback_row]
