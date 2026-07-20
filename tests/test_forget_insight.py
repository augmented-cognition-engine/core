"""Tests for the forget erasure primitive (Phase 4)."""

import pytest

from core.engine.capture.atomic_write import atomic_capture_write
from core.engine.capture.forget import forget_insight
from core.engine.core.db import parse_one, parse_rows

_TEST_PRODUCT = "product:test_forget_55501"


@pytest.fixture(autouse=True)
async def _cleanup(db_pool):
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE insight WHERE product = <record>$p", {"p": _TEST_PRODUCT})
        await db.query("DELETE forget_log WHERE product = <record>$p", {"p": _TEST_PRODUCT})
        await db.query("DELETE observation:fedge_a_55501")
        await db.query("DELETE observation:fedge_b_55501")


async def _make_insight(db_pool, content="forget-target-unique-55501") -> str:
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
            "tags": ["test"],
        },
        embedding=None,
        specialty_slug=None,
        observation_ids=[],
    )


@pytest.mark.asyncio
async def test_dry_run_does_not_erase(db_pool):
    iid = await _make_insight(db_pool)
    res = await forget_insight(
        db_pool, iid, product_id=_TEST_PRODUCT, reason="test", actor="tester"
    )  # confirm defaults False
    assert res["would_erase"] is True
    assert res["confirmed"] is False
    async with db_pool.connection() as db:
        still = parse_one(await db.query("SELECT id FROM <record>$id", {"id": iid}))
    assert still is not None  # row still exists


@pytest.mark.asyncio
async def test_confirmed_erase_removes_row_and_writes_log(db_pool):
    iid = await _make_insight(db_pool)
    res = await forget_insight(
        db_pool,
        iid,
        product_id=_TEST_PRODUCT,
        reason="user request",
        actor="tester",
        confirm=True,
    )
    assert res["erased"] is True
    async with db_pool.connection() as db:
        gone = parse_one(await db.query("SELECT id FROM <record>$id", {"id": iid}))
        log = parse_rows(
            await db.query(
                "SELECT insight_id, content_hash, reason, actor, source FROM forget_log WHERE insight_id = $i",
                {"i": iid},
            )
        )
    assert gone is None  # row erased
    assert len(log) == 1
    assert log[0]["reason"] == "user request"
    assert log[0]["content_hash"]  # present
    # audit is content-free: no 'content' field on the log row
    assert "content" not in log[0]


@pytest.mark.asyncio
async def test_confirmed_erase_removes_edges(db_pool):
    # Create a plain insight, then build two derived_from edges (insight->observation)
    # directly. The edges must be RELATE-d with inlined record ids: a bound
    # <record>$param endpoint silently creates no edge in SurrealDB v3, so we
    # interpolate the validated insight id into the RELATE statement here.
    iid = await _make_insight(db_pool, content="forget-edges-unique-55501")
    assert iid.startswith("insight:")  # validated shape — safe to interpolate
    async with db_pool.connection() as db:
        await db.query("CREATE observation:fedge_a_55501 SET product = <record>$p", {"p": _TEST_PRODUCT})
        await db.query("CREATE observation:fedge_b_55501 SET product = <record>$p", {"p": _TEST_PRODUCT})
        await db.query(f"RELATE {iid}->derived_from->observation:fedge_a_55501 SET created_at = time::now()")
        await db.query(f"RELATE {iid}->derived_from->observation:fedge_b_55501 SET created_at = time::now()")
        before = parse_one(
            await db.query("SELECT count() AS n FROM derived_from WHERE in = <record>$id GROUP ALL", {"id": iid})
        )
    assert before and before["n"] == 2  # two derived_from edges exist

    res = await forget_insight(db_pool, iid, product_id=_TEST_PRODUCT, reason="edge test", actor="t", confirm=True)
    assert res["edges_removed"] == 2

    async with db_pool.connection() as db:
        after = parse_one(
            await db.query("SELECT count() AS n FROM derived_from WHERE in = <record>$id GROUP ALL", {"id": iid})
        )
    assert after is None or after.get("n", 0) == 0  # edges gone


@pytest.mark.asyncio
async def test_blank_reason_rejected(db_pool):
    iid = await _make_insight(db_pool)
    with pytest.raises(ValueError):
        await forget_insight(
            db_pool,
            iid,
            product_id=_TEST_PRODUCT,
            reason="   ",
            actor="tester",
            confirm=True,
        )


@pytest.mark.asyncio
async def test_forget_missing_id_is_noop(db_pool):
    res = await forget_insight(
        db_pool,
        "insight:does_not_exist_55501",
        product_id=_TEST_PRODUCT,
        reason="x",
        actor="t",
        confirm=True,
    )
    assert res["erased"] is False
    async with db_pool.connection() as db:
        log = parse_rows(await db.query("SELECT id FROM forget_log WHERE insight_id = 'insight:does_not_exist_55501'"))
    assert log == []  # no log row for a non-erasure


@pytest.mark.asyncio
async def test_forget_log_declared_append_only(db_pool):
    # The table is DECLARED append-only (FOR update NONE, FOR delete NONE). This
    # enforces for non-root/scoped connections (a branded extension's RBAC layer). ACE-core
    # connects as root, which SurrealDB lets bypass table permissions — so this
    # asserts the DECLARATION is in place (the honest guarantee), not that root
    # is blocked. App contract: no code path ever mutates forget_log.
    # SurrealDB v3: table-level PERMISSIONS appear in INFO FOR DB (tables dict),
    # not in INFO FOR TABLE (which lists only fields/indexes/events/lives).
    async with db_pool.connection() as db:
        db_info = await db.query("INFO FOR DB")
    if isinstance(db_info, list):
        db_info = db_info[0]
    table_def = (db_info.get("tables", {}) if isinstance(db_info, dict) else {}).get("forget_log", "")
    assert "update" in table_def and "delete" in table_def and "NONE" in table_def
