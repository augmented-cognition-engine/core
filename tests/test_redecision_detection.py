# tests/test_redecision_detection.py
"""Tests for re-decision detection — if we're making the same call twice, memory failed.

When a new decision's title/rationale is similar to an existing decision, surface
the prior decision so the caller can confirm it still applies (or explicitly
supersede it). Uses word-set Jaccard for the first pass — cheap, no LLM, no
embedder required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def test_jaccard_identical_strings_is_one():
    from core.engine.product.decisions import _jaccard_similarity

    assert _jaccard_similarity("use Postgres for billing", "use Postgres for billing") == pytest.approx(1.0)


def test_jaccard_disjoint_is_zero():
    from core.engine.product.decisions import _jaccard_similarity

    assert _jaccard_similarity("alpha beta", "gamma delta") == 0.0


def test_jaccard_partial_overlap():
    from core.engine.product.decisions import _jaccard_similarity

    # {use, postgres, for, billing} vs {migrate, to, postgres, for, billing}
    # intersection 3 / union 6 = 0.5
    assert _jaccard_similarity("use Postgres for billing", "migrate to Postgres for billing") == pytest.approx(0.5)


def test_jaccard_ignores_stop_tokens_case_whitespace():
    from core.engine.product.decisions import _jaccard_similarity

    assert _jaccard_similarity("Use Postgres", "use  POSTGRES") == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_find_similar_decisions_returns_above_threshold():
    from core.engine.product.decisions import find_similar_decisions

    existing = [
        {"id": "decision:1", "title": "use Postgres for billing", "rationale": "acid"},
        {"id": "decision:2", "title": "choose React for UI", "rationale": "ecosystem"},
    ]

    async def fake_query(sql, params=None):
        return [existing]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    hits = await find_similar_decisions(
        db=mock_db,
        product_id="product:test",
        title="use Postgres for billing engine",
        threshold=0.5,
    )
    ids = [h["id"] for h in hits]
    assert "decision:1" in ids
    assert "decision:2" not in ids


@pytest.mark.asyncio
async def test_find_similar_decisions_empty_below_threshold():
    from core.engine.product.decisions import find_similar_decisions

    async def fake_query(sql, params=None):
        return [[{"id": "decision:x", "title": "something totally different", "rationale": "x"}]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    hits = await find_similar_decisions(
        db=mock_db,
        product_id="product:test",
        title="pick blue as primary brand color",
        threshold=0.5,
    )
    assert hits == []


@pytest.mark.asyncio
async def test_create_decision_surfaces_similar_prior_in_result():
    """Sentinel boundary: when a prior similar decision exists, create_decision's return includes similar_prior."""
    from unittest.mock import MagicMock

    from core.engine.product.decisions import create_decision

    existing_prior = {
        "id": "decision:existing",
        "title": "use Postgres for billing",
        "rationale": "acid",
        "created_at": "2026-01-01T00:00:00Z",
    }
    new_decision = {"id": "decision:new", "title": "use Postgres for billing engine"}

    async def fake_query(sql, params=None):
        if "SELECT id, title, rationale, created_at FROM decision" in sql:
            return [[existing_prior]]
        if "CREATE decision SET" in sql:
            return [[new_decision]]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    result = await create_decision(
        title="use Postgres for billing engine",
        decision_type="architecture",
        rationale="acid",
        product_id="product:test",
        pool=mock_pool,
    )

    assert "similar_prior" in result
    assert any(p["id"] == "decision:existing" for p in result["similar_prior"])


@pytest.mark.asyncio
async def test_find_similar_decisions_failure_non_fatal():
    from core.engine.product.decisions import find_similar_decisions

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("db gone"))

    hits = await find_similar_decisions(db=mock_db, product_id="product:test", title="anything")
    assert hits == []
