"""forget_by_hash erases every insight whose content matches a hash."""

import pytest

from core.engine.capture.atomic_write import atomic_capture_write
from core.engine.capture.forget import forget_by_hash
from core.engine.capture.pattern_detector import _content_hash
from core.engine.core.db import parse_rows

_TEST_PRODUCT = "product:test_forgethash_55502"


@pytest.fixture(autouse=True)
async def _cleanup(db_pool):
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE insight WHERE product = <record>$p", {"p": _TEST_PRODUCT})
        await db.query("DELETE forget_log WHERE product = <record>$p", {"p": _TEST_PRODUCT})


async def _make(db_pool, content):
    return await atomic_capture_write(
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
            "tags": [],
        },
        embedding=None,
        specialty_slug=None,
        observation_ids=[],
    )


@pytest.mark.asyncio
async def test_forget_by_hash_erases_all_duplicates(db_pool):
    content = "duplicate-fact-unique-55502 the same captured twice"
    id1 = await _make(db_pool, content)
    id2 = await _make(db_pool, content)
    h = _content_hash(content)

    res = await forget_by_hash(
        db_pool,
        h,
        product_id=_TEST_PRODUCT,
        reason="dup erase",
        actor="tester",
        confirm=True,
    )
    assert res["erased_count"] == 2
    async with db_pool.connection() as db:
        remaining = parse_rows(
            await db.query("SELECT id FROM insight WHERE product = <record>$p", {"p": _TEST_PRODUCT})
        )
    assert remaining == []


@pytest.mark.asyncio
async def test_forget_by_hash_dry_run_lists_matches(db_pool):
    content = "dry-run-hash-unique-55502"
    await _make(db_pool, content)
    h = _content_hash(content)
    res = await forget_by_hash(db_pool, h, product_id=_TEST_PRODUCT, reason="x", actor="t")  # confirm False
    assert res["would_erase_count"] >= 1
    async with db_pool.connection() as db:
        still = parse_rows(await db.query("SELECT id FROM insight WHERE product = <record>$p", {"p": _TEST_PRODUCT}))
    assert len(still) >= 1  # nothing erased


@pytest.mark.asyncio
async def test_forget_by_hash_blank_reason_rejected(db_pool):
    with pytest.raises(ValueError):
        await forget_by_hash(
            db_pool,
            "abc123",
            product_id=_TEST_PRODUCT,
            reason="  ",
            actor="t",
            confirm=True,
        )


@pytest.mark.asyncio
async def test_forget_by_hash_reaches_non_active_status(db_pool):
    # Erasure must reach content in soft-retired rows, not just active ones.
    content = "superseded-fact-unique-55502 still holds its content"
    iid = await _make(db_pool, content)
    async with db_pool.connection() as db:
        await db.query("UPDATE <record>$id SET status = 'superseded'", {"id": iid})
    h = _content_hash(content)

    res = await forget_by_hash(
        db_pool,
        h,
        product_id=_TEST_PRODUCT,
        reason="erase superseded",
        actor="t",
        confirm=True,
    )
    assert res["erased_count"] == 1
    async with db_pool.connection() as db:
        remaining = parse_rows(
            await db.query("SELECT id FROM insight WHERE product = <record>$p", {"p": _TEST_PRODUCT})
        )
    assert remaining == []


@pytest.mark.asyncio
async def test_forget_by_hash_does_not_cross_product_scope(db_pool):
    other_product = "product:test_forgethash_other_55502"
    content = "same content in two products unique 55502"
    await _make(db_pool, content)
    await atomic_capture_write(
        db_pool,
        insight_fields={
            "product": other_product,
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
            "tags": [],
        },
        embedding=None,
        specialty_slug=None,
        observation_ids=[],
    )

    result = await forget_by_hash(
        db_pool,
        _content_hash(content),
        product_id=_TEST_PRODUCT,
        reason="scope test",
        actor="tester",
        confirm=True,
    )

    assert result["erased_count"] == 1
    async with db_pool.connection() as db:
        remaining = parse_rows(
            await db.query(
                "SELECT id FROM insight WHERE product = <record>$product",
                {"product": other_product},
            )
        )
        await db.query("DELETE insight WHERE product = <record>$product", {"product": other_product})
    assert len(remaining) == 1
