"""End-to-end: an atomically-captured insight is retrievable via ace_search.

This guards the REAL loop. ace_search (core/engine/mcp/tools.py) is the canonical
hybrid BM25 + native-vector (vector::similarity::cosine) search over insight rows.
The atomic capture write (Phase 1 / A+) is what now populates insight.embedding at
write time, so a freshly captured insight is immediately surfaced by ace_search.
"""

import pytest

from core.engine.capture.atomic_write import atomic_capture_write
from core.engine.embedding.base import get_embedder
from core.engine.mcp.tools import ace_search

_TEST_PRODUCT = "product:test_acesearch_84620"


@pytest.fixture(autouse=True)
async def _cleanup_test_rows(db_pool):
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE insight WHERE product = <record>$product", {"product": _TEST_PRODUCT})


@pytest.mark.asyncio
async def test_captured_insight_is_retrievable_via_ace_search(db_pool):
    embedder = get_embedder()
    if embedder.dimensions == 0:
        pytest.skip("no real embedder available (noop)")

    content = "ace-search-target-unique-84620 exponential backoff for webhook retries"
    vec = (await embedder.embed([content]))[0]

    await atomic_capture_write(
        db_pool,
        insight_fields={
            "product": _TEST_PRODUCT,
            "content": content,
            "insight_type": "fact",
            "tier": "domain",
            "clearance": "open",
            "confidence": 0.9,
            "source_domain": "test",
            "domain_path": "test",
            "domain": None,
            "subdomain": None,
            "specialty": None,
            "tags": ["test"],
        },
        embedding=vec,
        specialty_slug=None,
        observation_ids=[],
    )

    result = await ace_search("webhook retries backoff", product_id=_TEST_PRODUCT)
    assert any("84620" in r.get("content", "") for r in result["results"])
