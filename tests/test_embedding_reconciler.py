import pytest

from core.engine.capture.atomic_write import atomic_capture_write
from core.engine.core.db import parse_one
from core.engine.embedding.base import get_embedder
from core.engine.sentinel.engines.embedding_reconciler import reconcile_missing_embeddings

_TEST_PRODUCT = "product:test_reconciler_97531"


@pytest.fixture(autouse=True)
async def _cleanup_test_rows(db_pool):
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE insight WHERE product = <record>$product", {"product": _TEST_PRODUCT})


@pytest.mark.asyncio
async def test_reconciler_backfills_embedding(db_pool):
    if get_embedder().dimensions == 0:
        pytest.skip("no real embedder available (noop) — reconciler cannot backfill")

    content = "reconciler-target-unique-97531"
    insight_id = await atomic_capture_write(
        db_pool,
        insight_fields={
            "product": _TEST_PRODUCT,
            "content": content,
            "insight_type": "fact",
            "tier": "domain",
            "clearance": "open",
            "confidence": 0.5,
            "source_domain": "test",
            "domain_path": "test",
            "domain": None,
            "subdomain": None,
            "specialty": None,
            "tags": [],
        },
        embedding=None,
        specialty_slug=None,
        observation_ids=[],
    )
    async with db_pool.connection() as db:
        pre = parse_one(await db.query("SELECT needs_embedding FROM <record>$id", {"id": insight_id}))
    assert pre.get("needs_embedding") is True

    n = await reconcile_missing_embeddings(limit=200)
    assert n >= 1

    async with db_pool.connection() as db:
        row = parse_one(await db.query("SELECT embedding, needs_embedding FROM <record>$id", {"id": insight_id}))
    assert row.get("embedding") is not None
    assert not row.get("needs_embedding")


@pytest.mark.asyncio
async def test_reconciler_catches_unflagged_sentinel_style_insight(db_pool):
    """Insights written by paths that never embed (sentinel write_engine_insight,
    consolidator, seed_generator, …) have embedding=NONE but needs_embedding
    UNSET. The reconciler must still embed them (path-agnostic), or they stay
    invisible to ace_search forever."""
    if get_embedder().dimensions == 0:
        pytest.skip("no real embedder available (noop)")

    content = "sentinel-style-unflagged-unique-97531 about retries"
    async with db_pool.connection() as db:
        # write directly, the way write_engine_insight does: NO embedding, NO needs_embedding flag
        created = parse_one(
            await db.query(
                "CREATE ONLY insight SET product = <record>$p, content = $c, insight_type = 'fact', "
                "tier = 'domain', source_domain = 'sentinel', confidence = 0.7, tags = [], "
                "status = 'active', created_at = time::now(), updated_at = time::now(), "
                "last_confirmed = time::now() RETURN id",
                {"p": _TEST_PRODUCT, "c": content},
            )
        )
        iid = str(created["id"])
        pre = parse_one(await db.query("SELECT embedding, needs_embedding FROM <record>$id", {"id": iid}))
    assert pre.get("embedding") is None and pre.get("needs_embedding") is None  # truly unflagged

    await reconcile_missing_embeddings(limit=200)

    async with db_pool.connection() as db:
        row = parse_one(await db.query("SELECT embedding FROM <record>$id", {"id": iid}))
    assert row.get("embedding") is not None  # reconciler embedded it despite no flag
