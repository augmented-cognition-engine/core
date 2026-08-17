from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.engine.graph.operational_relationships import (
    MAX_OPERATIONAL_RELATIONSHIPS,
    load_operational_relationships,
)


def _row(
    suffix: str,
    *,
    product: str = "product:test",
    predicate: str = "breaks",
    status: str = "accepted",
    eligible: bool = True,
) -> dict:
    edge_in = f"insight:{suffix}_in"
    edge_out = f"insight:{suffix}_out"
    return {
        "id": f"operational_relationship:{suffix}",
        "in": edge_in,
        "out": edge_out,
        "predicate": predicate,
        "assertion_id": f"relationship_assertion:{suffix}",
        "assertion_product": product,
        "assertion_status": status,
        "assertion_projection_eligible": eligible,
        "assertion_subject": edge_in,
        "assertion_object": edge_out,
        "assertion_predicate": predicate,
        "evidence_refs": ["evidence:z", "evidence:a"],
        "review_refs": ["review:2", "review:1"],
    }


@pytest.mark.asyncio
async def test_reader_uses_one_bounded_product_scoped_canonical_query():
    db = AsyncMock()
    db.query.return_value = [[_row("one")]]

    rows = await load_operational_relationships(
        "product:test",
        predicates=("breaks", "not_in_ontology"),
        limit=MAX_OPERATIONAL_RELATIONSHIPS + 99,
        db=db,
    )

    sql, params = db.query.await_args.args
    assert "FROM operational_relationship" in sql
    assert "source = 'cognify'" not in sql
    assert "assertion_id.status = 'accepted'" in sql
    assert "assertion_id.projection_eligible = true" in sql
    assert "ORDER BY predicate ASC, id ASC" in sql
    assert params == {
        "product": "product:test",
        "predicates": ["breaks"],
        "limit": MAX_OPERATIONAL_RELATIONSHIPS,
    }
    assert rows[0]["provenance"] == {
        "record_refs": ["operational_relationship:one", "relationship_assertion:one"],
        "evidence_refs": ["evidence:a", "evidence:z"],
        "review_refs": ["review:1", "review:2"],
        "source_family": "operational_relationship",
    }


@pytest.mark.asyncio
async def test_reader_fails_closed_on_stale_cross_product_or_mismatched_projection():
    wrong_endpoint = _row("endpoint")
    wrong_endpoint["assertion_subject"] = "insight:different"
    wrong_predicate = _row("predicate")
    wrong_predicate["assertion_predicate"] = "causes"
    db = AsyncMock()
    db.query.return_value = [
        [
            _row("stale", status="contested"),
            _row("ineligible", eligible=False),
            _row("foreign", product="product:other"),
            wrong_endpoint,
            wrong_predicate,
            _row("valid"),
        ]
    ]

    rows = await load_operational_relationships("product:test", predicates=("breaks",), db=db)

    assert [row["id"] for row in rows] == ["operational_relationship:valid"]


@pytest.mark.asyncio
async def test_reader_empty_semantic_filter_avoids_database_work():
    db = AsyncMock()

    assert await load_operational_relationships("product:test", predicates=("invented",), db=db) == []
    db.query.assert_not_awaited()


@pytest.mark.asyncio
async def test_reader_clamps_non_positive_limit_to_one():
    db = AsyncMock()
    db.query.return_value = [[_row("one")]]

    await load_operational_relationships("product:test", predicates=("breaks",), limit=0, db=db)

    assert db.query.await_args.args[1]["limit"] == 1
