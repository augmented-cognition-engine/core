# tests/test_report_assembler.py
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_pool(side_effect_list):
    db = AsyncMock()
    db.query = AsyncMock(side_effect=side_effect_list)
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.mark.asyncio
async def test_assembler_returns_health_by_discipline():
    """Health scores are averaged per discipline and sorted worst-first."""
    quality_rows = [
        [
            {"discipline": "security", "score": 0.1, "gaps": ["no auth"], "capability": "cap:1"},
            {"discipline": "security", "score": 0.3, "gaps": ["no rate limit"], "capability": "cap:2"},
            {"discipline": "testing", "score": 0.8, "gaps": [], "capability": "cap:3"},
        ]
    ]
    # assemble queries: quality, capabilities, decisions, initiatives
    pool = _make_pool([quality_rows, [[]], [[]], [[]]])

    from core.engine.reports.assembler import DataAssembler

    a = DataAssembler(pool)
    result = await a.assemble("product:test", "audit", client_name="Acme", consultant_name="Ed")

    health = result["health_by_discipline"]
    disciplines = {d["discipline"]: d for d in health}
    assert "security" in disciplines
    assert disciplines["security"]["avg_score"] == pytest.approx(0.2)
    assert disciplines["security"]["gap_count"] == 2
    assert disciplines["testing"]["gap_count"] == 0
    assert result["client_name"] == "Acme"
    assert result["report_type"] == "audit"
    # worst-first sort order
    assert health[0]["discipline"] == "security"  # avg 0.2 — worst
    assert health[1]["discipline"] == "testing"  # avg 0.8 — best


@pytest.mark.asyncio
async def test_assembler_top_risks_sorted_by_score():
    """top_risks contains worst-scoring items, ordered worst-first, max 7."""
    rows = [
        [
            {"discipline": "security", "score": 0.05, "gaps": ["no auth"], "capability": "cap:1"},
            {"discipline": "testing", "score": 0.45, "gaps": ["no coverage"], "capability": "cap:2"},
            {"discipline": "performance", "score": 0.9, "gaps": [], "capability": "cap:3"},
        ]
    ]
    pool = _make_pool([rows, [[]], [[]], [[]]])

    from core.engine.reports.assembler import DataAssembler

    a = DataAssembler(pool)
    result = await a.assemble("product:test", "audit")

    risks = result["top_risks"]
    # score 0.9 is not a risk (>= 0.7)
    assert all(r["score"] < 0.7 for r in risks)
    # sorted worst-first
    assert risks[0]["score"] <= risks[-1]["score"]
    assert risks[0]["severity"] == "critical"  # score 0.05
    assert risks[1]["severity"] == "high"  # score 0.45


@pytest.mark.asyncio
async def test_assembler_empty_product_returns_safe_defaults():
    """Empty DB → returns valid structure with empty lists, no crash."""
    pool = _make_pool([[[]], [[]], [[]], [[]]])

    from core.engine.reports.assembler import DataAssembler

    a = DataAssembler(pool)
    result = await a.assemble("product:test", "audit")

    assert result["health_by_discipline"] == []
    assert result["top_risks"] == []
    assert result["capabilities"] == []


@pytest.mark.asyncio
async def test_assembler_top_risks_capped_at_seven():
    """More than 7 risks → only 7 returned (worst-first)."""
    rows = [
        [
            {"discipline": "security", "score": 0.05 + i * 0.05, "gaps": [], "capability": f"cap:{i}"}
            for i in range(9)  # 9 rows, all score < 0.7, all qualify as risks
        ]
    ]
    pool = _make_pool([rows, [[]], [[]], [[]]])

    from core.engine.reports.assembler import DataAssembler

    a = DataAssembler(pool)
    result = await a.assemble("product:test", "audit")

    assert len(result["top_risks"]) == 7
    # Sorted worst-first (lowest score first)
    scores = [r["score"] for r in result["top_risks"]]
    assert scores == sorted(scores)


@pytest.mark.asyncio
async def test_assembler_gaps_none_does_not_crash():
    """gaps=None from DB (SurrealDB null) must not raise TypeError."""
    rows = [
        [
            {"discipline": "security", "score": 0.1, "gaps": None, "capability": "cap:1"},
        ]
    ]
    pool = _make_pool([rows, [[]], [[]], [[]]])

    from core.engine.reports.assembler import DataAssembler

    a = DataAssembler(pool)
    result = await a.assemble("product:test", "audit")

    # Must not crash; gaps should be empty list in output
    assert len(result["top_risks"]) == 1
    assert result["top_risks"][0]["gaps"] == []
