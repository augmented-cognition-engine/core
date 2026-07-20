"""A forgotten insight is no longer returned by ace_search (single-substrate)."""

import pytest

from core.engine.capture.atomic_write import atomic_capture_write
from core.engine.capture.forget import forget_insight
from core.engine.embedding.base import get_embedder
from core.engine.mcp.tools import ace_search

_TEST_PRODUCT = "product:test_forgetsearch_55504"


@pytest.fixture(autouse=True)
async def _cleanup(db_pool):
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE insight WHERE product = <record>$p", {"p": _TEST_PRODUCT})
        await db.query("DELETE forget_log WHERE product = <record>$p", {"p": _TEST_PRODUCT})


@pytest.mark.asyncio
async def test_forgotten_insight_not_in_search(db_pool):
    embedder = get_embedder()
    if embedder.dimensions == 0:
        pytest.skip("no real embedder")
    content = "forget-search-target-unique-55504 about idempotent retries"
    vec = (await embedder.embed([content]))[0]
    iid = await atomic_capture_write(
        db_pool,
        insight_fields={
            "product": _TEST_PRODUCT,
            "content": content,
            "insight_type": "fact",
            "tier": "domain",
            "clearance": "open",
            "confidence": 0.95,
            "source_domain": "test",
            "domain_path": "test",
            "domain": None,
            "subdomain": None,
            "specialty": None,
            "tags": [],
        },
        embedding=vec,
        specialty_slug=None,
        observation_ids=[],
    )
    before = await ace_search("idempotent retries", product_id=_TEST_PRODUCT)
    assert any("55504" in r.get("content", "") for r in before["results"])

    await forget_insight(db_pool, iid, product_id=_TEST_PRODUCT, reason="e2e", actor="tester", confirm=True)

    after = await ace_search("idempotent retries", product_id=_TEST_PRODUCT)
    assert not any("55504" in r.get("content", "") for r in after["results"])
