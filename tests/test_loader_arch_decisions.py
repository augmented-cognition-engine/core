"""Tests for cross-session architectural memory (_load_arch_decisions)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ARCH_ROWS = [
    {
        "id": "decision:1",
        "title": "Use SurrealDB as primary store",
        "decision_type": "architecture",
        "rationale": "Schema flexibility + graph queries in one engine",
        "outcome": "accepted",
        "discipline_hint": "data",
    },
    {
        "id": "decision:2",
        "title": "Judge-executor separation for reasoning loop",
        "decision_type": "trade_off",
        "rationale": "Same model reviewing its own output creates blind spots",
        "outcome": "accepted",
        "discipline_hint": "coding",
    },
]


def _make_pool(rows_by_table: dict):
    async def fake_query(q, params=None):
        for table, rows in rows_by_table.items():
            if table in q:
                return [rows]
        return [[]]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn
    return mock_pool


@pytest.mark.asyncio
async def test_arch_decisions_returned_in_loaded():
    """load_intelligence includes arch_decisions with architecture + trade_off rows."""
    pool = _make_pool({"decision": _ARCH_ROWS})
    with patch("core.engine.orchestrator.loader.pool", pool):
        from core.engine.orchestrator.loader import load_intelligence

        result = await load_intelligence(
            discipline="coding",
            product_id="product:test",
            mode="reactive",
        )

    assert "arch_decisions" in result
    assert len(result["arch_decisions"]) == 2
    types = {d["decision_type"] for d in result["arch_decisions"]}
    assert types == {"architecture", "trade_off"}


@pytest.mark.asyncio
async def test_arch_decisions_empty_when_no_data():
    """arch_decisions is [] when no architecture/trade_off decisions exist."""
    pool = _make_pool({})
    with patch("core.engine.orchestrator.loader.pool", pool):
        from core.engine.orchestrator.loader import load_intelligence

        result = await load_intelligence(
            discipline="design",
            product_id="product:test",
            mode="reactive",
        )

    assert result["arch_decisions"] == []


@pytest.mark.asyncio
async def test_arch_decisions_non_fatal_on_error():
    """arch_decisions degrades to [] on DB error — never blocks the load."""

    async def failing_query(q, params=None):
        if "decision" in q and "architecture" in q:
            raise RuntimeError("db unavailable")
        return [[]]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(side_effect=failing_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.orchestrator.loader.pool", mock_pool):
        from core.engine.orchestrator.loader import load_intelligence

        result = await load_intelligence(
            discipline="architecture",
            product_id="product:test",
            mode="reactive",
        )

    assert result["arch_decisions"] == []


@pytest.mark.asyncio
async def test_arch_decisions_no_discipline_filter():
    """_load_arch_decisions returns decisions from any discipline, not just current one."""
    pool = _make_pool({"decision": _ARCH_ROWS})
    with patch("core.engine.orchestrator.loader.pool", pool):
        from core.engine.orchestrator.loader import _load_arch_decisions

        rows = await _load_arch_decisions("product:test")

    discipline_hints = {r["discipline_hint"] for r in rows}
    assert "data" in discipline_hints
    assert "coding" in discipline_hints
