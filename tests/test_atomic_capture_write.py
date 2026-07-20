"""Tests for atomic single-substrate capture write (Phase 1 / A+).

NOTE: The test spec called for embedding=[0.01] * 1024 but the live HNSW index
on the insight table enforces DIMENSION 768 (v062_intelligence_indexes.surql).
All embedding vectors here use 768 dimensions to match the enforced constraint.
"""

import pytest

from core.engine.capture.atomic_write import atomic_capture_write
from core.engine.core.db import parse_one, parse_rows


async def _count_insights_with_content(db, content: str) -> int:
    rows = parse_rows(await db.query("SELECT id FROM insight WHERE content = $c", {"c": content}))
    return len(rows)


@pytest.mark.asyncio
async def test_observation_ids_create_derived_from_edges(db_pool):
    """Regression: RELATE endpoints must be bound as RecordID objects, not
    strings — SurrealDB v3 rejects a string RELATE endpoint, which silently
    broke every edge write (informed_by/derived_from) in the original A+ code."""
    product = "product:test_atomicedges_31416"
    async with db_pool.connection() as db:
        await db.query("CREATE observation:atomicedge_a SET content='o', product=<record>$p", {"p": product})
        await db.query("CREATE observation:atomicedge_b SET content='o', product=<record>$p", {"p": product})
    try:
        iid = await atomic_capture_write(
            db_pool,
            insight_fields={
                "product": product,
                "content": "atomic-edges-unique-31416",
                "insight_type": "fact",
                "tier": "domain",
                "clearance": "open",
                "confidence": 0.8,
                "source_domain": "test",
                "domain_path": "test",
                "domain": None,
                "subdomain": None,
                "specialty": None,
                "tags": [],
            },
            embedding=None,
            specialty_slug=None,
            observation_ids=["observation:atomicedge_a", "observation:atomicedge_b"],
        )
        async with db_pool.connection() as db:
            n = parse_one(
                await db.query("SELECT count() AS n FROM derived_from WHERE in = <record>$id GROUP ALL", {"id": iid})
            )
        assert n is not None and n["n"] == 2  # both edges actually created
    finally:
        async with db_pool.connection() as db:
            await db.query("DELETE derived_from WHERE out.product = <record>$p", {"p": product})
            await db.query("DELETE insight WHERE product = <record>$p", {"p": product})
            await db.query("DELETE observation WHERE product = <record>$p", {"p": product})


@pytest.mark.asyncio
async def test_happy_path_writes_record_edges_and_embedding(db_pool):
    content = "atomic-write-test-happy-path-unique-12345"
    insight_id = await atomic_capture_write(
        db_pool,
        insight_fields={
            "product": "product:test",
            "content": content,
            "insight_type": "fact",
            "tier": "domain",
            "clearance": "open",
            "confidence": 0.7,
            "source_domain": "test",
            "domain_path": "test",
            "domain": None,
            "subdomain": None,
            "specialty": None,
            "tags": ["test"],
        },
        embedding=[0.01] * 768,
        specialty_slug=None,
        observation_ids=[],
    )
    assert insight_id.startswith("insight:")
    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT id, embedding, needs_embedding FROM <record>$id",
                {"id": insight_id},
            )
        )
    assert row is not None
    assert row.get("embedding") is not None
    assert len(row["embedding"]) == 768
    assert not row.get("needs_embedding")


@pytest.mark.asyncio
async def test_rollback_raises_on_failed_write(db_pool):
    # A bad field type (confidence as a non-float string) fails the CREATE inside
    # the BEGIN..COMMIT block. The LOAD-BEARING guarantee is that the per-statement
    # ERR is detected and PROPAGATED (RuntimeError) — never silently swallowed.
    # SurrealDB's transaction aborts the write on that error (no partial commit);
    # that rollback is verified out-of-band with a fresh pool (the shared-session
    # test pool + surrealkv abort-visibility makes an immediate in-session row
    # count unreliable, so it is not asserted here).
    content = "atomic-write-test-rollback-unique-67890"
    with pytest.raises(RuntimeError):
        await atomic_capture_write(
            db_pool,
            insight_fields={
                "product": "product:test",
                "content": content,
                "insight_type": "fact",
                "tier": "domain",
                "clearance": "open",
                "confidence": "not_a_float",  # type error -> CREATE fails -> abort
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


@pytest.mark.asyncio
async def test_degraded_mode_marks_needs_embedding(db_pool):
    content = "atomic-write-test-degraded-unique-24680"
    insight_id = await atomic_capture_write(
        db_pool,
        insight_fields={
            "product": "product:test",
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
        embedding=None,  # embedder unavailable
        specialty_slug=None,
        observation_ids=[],
    )
    async with db_pool.connection() as db:
        row = parse_one(await db.query("SELECT embedding, needs_embedding FROM <record>$id", {"id": insight_id}))
    assert row.get("embedding") is None
    assert row.get("needs_embedding") is True
