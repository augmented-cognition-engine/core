import pytest

from core.engine.product.uncertainty import (
    answer_query,
    get_open_queries,
    query_uncertainty,
)


@pytest.mark.asyncio
async def test_query_uncertainty_creates_record(db_pool):
    pid = "product:test_uq"
    q = await query_uncertainty(
        pool=db_pool,
        product_id=pid,
        scope="ambition",
        question="What's your demo target?",
        fallback_action="default_safe",
    )
    assert q.scope == "ambition"
    assert q.status == "open"

    async with db_pool.connection() as db:
        await db.query("DELETE uncertainty_queries WHERE product = <record>$pid", {"pid": pid})


@pytest.mark.asyncio
async def test_get_open_queries_returns_unanswered(db_pool):
    pid = "product:test_uq2"
    await query_uncertainty(
        pool=db_pool,
        product_id=pid,
        scope="state",
        question="Q1?",
        fallback_action="pause",
    )
    await query_uncertainty(
        pool=db_pool,
        product_id=pid,
        scope="state",
        question="Q2?",
        fallback_action="pause",
    )
    open_qs = await get_open_queries(db_pool, pid)
    assert len(open_qs) == 2

    async with db_pool.connection() as db:
        await db.query("DELETE uncertainty_queries WHERE product = <record>$pid", {"pid": pid})


@pytest.mark.asyncio
async def test_answer_query_closes_it(db_pool):
    pid = "product:test_uq3"
    q = await query_uncertainty(
        pool=db_pool,
        product_id=pid,
        scope="state",
        question="Owner of data layer?",
        fallback_action="pause",
    )
    await answer_query(db_pool, q.id, "the data team")
    open_qs = await get_open_queries(db_pool, pid)
    assert len(open_qs) == 0

    async with db_pool.connection() as db:
        await db.query("DELETE uncertainty_queries WHERE product = <record>$pid", {"pid": pid})
