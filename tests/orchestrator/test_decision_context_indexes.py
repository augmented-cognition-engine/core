"""Every decision-context tier query must use the (product, created_at) index.

THE BUG THIS PINS
-----------------
All three tier loaders have the same shape:

    SELECT … FROM decision WHERE product = $product [ AND … ] ORDER BY created_at DESC LIMIT n

The `ORDER BY created_at` made SurrealDB's planner prefer `idx_decision_recency` — an
index on created_at ALONE — and then filter each row by product as it walked. So a tier
query degenerated into a BACKWARD SCAN OF THE ENTIRE `decision` TABLE, stopping only when
it had collected enough rows for the requested product.

Which means the cost is inverted: the FEWER decisions a product has, the more of the table
gets scanned. A product with none at all scans every row and finds nothing.

    product:platform  (16,930 decisions)   recency 28ms · discipline 296ms
    a product with 0 decisions             recency 297ms · discipline 306ms

Against budgets of 50ms and 80ms. So the discipline tier was timing out on the MAIN
product on every single call, and every tier timed out for any new product — which is
cold start, precisely when a partner has least context and can least afford to lose more.

None of it failed loudly. `load_decision_context` catches a tier timeout, records the tier
in `degraded_tiers` and returns what it has, so the caller gets a plausible, quieter
answer and no error. It gets worse as the table grows, which is to say it gets worse the
longer ACE is used.

`idx_decision_product_created` (product, created_at) has existed since v097 and serves both
the equality and the ordering. The planner simply never chose it. `WITH INDEX` says so.

WHY THIS TEST IS NOT A TIMING TEST
----------------------------------
A timing assertion on a live DB is a flake generator, and the ORIGINAL symptom here was
already written off as one ("recency tier flakes under load"). It was not flaky — it was
a real full scan, and calling it flaky is what let it live. So this asserts the PLAN, which
is deterministic: the query must be served by the composite index.
"""

from __future__ import annotations

import json

import pytest

from core.engine.orchestrator.context import (
    _CAPS_NOT_NONE_FILTER,
    _CONFIDENCE_FILTER,
    _OUTCOME_FILTER,
    _TIER_INDEX,
)

pytestmark = pytest.mark.e2e

_COLS = "SELECT id, created_at FROM decision"
_EMPTY_PRODUCT = "product:idx_probe_no_such_product"

TIER_QUERIES = {
    "recency": "",
    "discipline": " AND discipline_hint = <string>$disc",
    "capability": " AND affected_capabilities CONTAINSANY $slugs" + _CAPS_NOT_NONE_FILTER,
}


def _sql(extra: str, *, with_index: bool) -> str:
    idx = f" WITH INDEX {_TIER_INDEX}" if with_index else ""
    return (
        _COLS
        + idx
        + " WHERE product = <record>$product"
        + extra
        + _OUTCOME_FILTER
        + _CONFIDENCE_FILTER
        + " ORDER BY created_at DESC LIMIT 5"
    )


def _index_in_plan(plan) -> str | None:
    """The index name SurrealDB's planner actually chose, from an EXPLAIN."""
    blob = json.dumps(plan, default=str)
    marker = '"index": "'
    return blob.split(marker)[1].split('"')[0] if marker in blob else None


@pytest.mark.parametrize("tier,extra", sorted(TIER_QUERIES.items()))
async def test_each_tier_query_is_served_by_the_composite_index(db_pool, tier, extra):
    """Without the hint the planner picks idx_decision_recency (created_at alone) and
    backward-scans the whole table filtering by product."""
    async with db_pool.connection() as db:
        plan = await db.query(
            _sql(extra, with_index=True) + " EXPLAIN",
            {"product": _EMPTY_PRODUCT, "min_conf": 0.0, "disc": "general", "slugs": ["auth"]},
        )

    chosen = _index_in_plan(plan)
    assert chosen != "idx_decision_recency", (
        f"the {tier} tier is being served by idx_decision_recency (created_at ONLY). That "
        f"index cannot satisfy `product = …`, so SurrealDB walks the table backward and "
        f"filters — a full scan whenever the product is sparse or new."
    )


async def test_the_tier_queries_actually_carry_the_hint(db_pool):
    """A source-level check, because the fix lives in a string the plan test above cannot
    see. If someone rewrites a tier query and drops WITH INDEX, the plan silently reverts
    to a full scan and only a timing test — which we deliberately do not have — would catch it.
    """
    import inspect

    from core.engine.orchestrator import context

    for loader in (
        context._load_recency_tier,
        context._load_discipline_tier,
        context._load_capability_tier,
    ):
        src = inspect.getsource(loader)
        # The loaders interpolate the constant (`f" WITH INDEX {_TIER_INDEX}"`), so the
        # source carries the NAME, not the value.
        assert "WITH INDEX" in src and "_TIER_INDEX" in src, (
            f"{loader.__name__} no longer pins {_TIER_INDEX}. Without it the planner falls "
            f"back to the created_at index and the query becomes a full table scan — "
            f"degrading silently into degraded_tiers, never into an error."
        )
