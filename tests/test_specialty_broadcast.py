# tests/test_specialty_broadcast.py
"""Tests for cross-product specialty broadcast.

When a specialty reaches EXPERT phase on product A, its top insights should
propagate to other products in the same ecosystem. Each copied insight carries
a source_product tag so provenance is preserved.

The sentinel: specialty matures once → other connected products inherit the
learning without re-earning it. This is what makes the ecosystem layer worth
having.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_find_connected_products_returns_others_in_ecosystem():
    """Given a product, return every other product sharing any ecosystem with it."""
    from core.engine.intelligence.specialty_broadcast import find_connected_products

    async def fake_query(sql, params=None):
        # Simulate ecosystem join returning product:b and product:c when asked for product:a
        return [[{"id": "product:b"}, {"id": "product:c"}]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    connected = await find_connected_products(mock_db, "product:a")
    assert set(connected) == {"product:b", "product:c"}


@pytest.mark.asyncio
async def test_find_connected_products_excludes_source():
    """The source product must never appear in its own connected-product list."""
    from core.engine.intelligence.specialty_broadcast import find_connected_products

    async def fake_query(sql, params=None):
        # Malformed DB response including the source itself — helper must filter
        return [[{"id": "product:a"}, {"id": "product:b"}]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    connected = await find_connected_products(mock_db, "product:a")
    assert "product:a" not in connected
    assert "product:b" in connected


@pytest.mark.asyncio
async def test_broadcast_specialty_inserts_each_insight_in_each_connected_product():
    from core.engine.intelligence.specialty_broadcast import broadcast_specialty

    insights = [
        {"id": "insight:src1", "content": "use get_llm()", "confidence": 0.95, "tier": "specialty"},
        {"id": "insight:src2", "content": "SurrealDB v3 <record>", "confidence": 0.9, "tier": "specialty"},
    ]
    captured_creates: list[dict] = []

    async def fake_query(sql, params=None):
        if "SELECT" in sql.upper() and "ecosystem" in sql:
            return [[{"id": "product:b"}]]
        if "CREATE insight" in sql:
            captured_creates.append(params or {})
            return [[{"id": "insight:new"}]]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    count = await broadcast_specialty(
        db=mock_db,
        source_product_id="product:a",
        specialty_slug="surrealdb_patterns",
        insights=insights,
    )

    # 2 insights × 1 connected product = 2 CREATE calls
    assert count == 2
    assert len(captured_creates) == 2
    # Every copied insight must tag the source_product for provenance
    for params in captured_creates:
        assert params.get("source_product") == "product:a"


@pytest.mark.asyncio
async def test_broadcast_specialty_noop_when_no_connected():
    """If the product has no ecosystem peers, broadcast is a no-op."""
    from core.engine.intelligence.specialty_broadcast import broadcast_specialty

    async def fake_query(sql, params=None):
        if "SELECT" in sql.upper() and "ecosystem" in sql:
            return [[]]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    count = await broadcast_specialty(
        db=mock_db,
        source_product_id="product:solo",
        specialty_slug="any",
        insights=[{"id": "insight:x", "content": "x", "confidence": 0.9}],
    )
    assert count == 0


@pytest.mark.asyncio
async def test_broadcast_specialty_failure_non_fatal():
    """DB error during broadcast must not propagate."""
    from core.engine.intelligence.specialty_broadcast import broadcast_specialty

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("boom"))

    count = await broadcast_specialty(
        db=mock_db,
        source_product_id="product:a",
        specialty_slug="any",
        insights=[{"id": "insight:x", "content": "x", "confidence": 0.9}],
    )
    assert count == 0


@pytest.mark.asyncio
async def test_broadcast_specialty_skips_low_confidence_insights():
    """Only high-confidence insights (>= 0.8) should broadcast — bar is high by design."""
    from core.engine.intelligence.specialty_broadcast import broadcast_specialty

    captured: list[dict] = []

    async def fake_query(sql, params=None):
        if "SELECT" in sql.upper() and "ecosystem" in sql:
            return [[{"id": "product:b"}]]
        if "CREATE insight" in sql:
            captured.append(params or {})
            return [[{"id": "insight:new"}]]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    insights = [
        {"id": "insight:good", "content": "high conf", "confidence": 0.92},
        {"id": "insight:bad", "content": "low conf", "confidence": 0.5},
    ]

    count = await broadcast_specialty(
        db=mock_db,
        source_product_id="product:a",
        specialty_slug="any",
        insights=insights,
    )
    assert count == 1
    assert captured[0].get("content") == "high conf"
