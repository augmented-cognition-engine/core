from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_roadmap_phase_table_accepts_write(db_pool):
    """v124 applied: roadmap_phase accepts a write keyed by (product, ordinal)."""
    from core.engine.core.db import parse_record_id, parse_rows, pool

    async with pool.connection() as db:
        await db.query("DELETE roadmap_phase WHERE title = 'TEST_PHASE_SMOKE'")
        await db.query(
            "CREATE roadmap_phase SET product = $p, title = 'TEST_PHASE_SMOKE', ordinal = 99, status = 'next'",
            {"p": parse_record_id("product:platform")},
        )
        rows = parse_rows(
            await db.query("SELECT title, ordinal, status FROM roadmap_phase WHERE title = 'TEST_PHASE_SMOKE'")
        )
        await db.query("DELETE roadmap_phase WHERE title = 'TEST_PHASE_SMOKE'")

    assert rows and rows[0]["ordinal"] == 99 and rows[0]["status"] == "next"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_strategy_ingest_surfaces_in_roadmap_intent_first(db_pool):
    """Ingest a phase + shipped + draft spec → compute_roadmap ranks them above gaps,
    in the right lanes, status preserved; a superseded spec drops out."""
    from core.engine.core.db import pool
    from core.engine.product.roadmap import _tier, compute_roadmap
    from core.engine.product.strategy_ingest import ingest_phase, ingest_spec

    PID = "product:platform"
    OBJ_DONE = "E2E_TEST shipped item"
    OBJ_NEXT = "E2E_TEST draft item"

    # Clean slate for the test fixtures.
    async with pool.connection() as db:
        for obj in (OBJ_DONE, OBJ_NEXT):
            await db.query("DELETE agent_spec WHERE objective = $o", {"o": obj})
        await db.query("DELETE roadmap_phase WHERE title = 'E2E_TEST Phase'")

    # ordinal 99: avoid UPSERT-colliding with real seeded phases (ordinals 1-6).
    await ingest_phase("E2E_TEST Phase", 99, "active", "summary", "wc", None, PID)
    await ingest_spec(OBJ_DONE, "shipped", "high", 99, None, ["wc"], None, PID)
    await ingest_spec(OBJ_NEXT, "draft", "high", 99, None, ["mx"], None, PID)

    # max_items high so test fixtures aren't capped out by real seeded strategy items.
    roadmap = await compute_roadmap(PID, max_items=200)
    flat = [it for lane in roadmap.lanes.values() for it in lane]
    by_title = {it.title: it for it in flat}

    # Present + correct lanes.
    assert by_title.get(OBJ_DONE) and by_title[OBJ_DONE].lane == "done"
    assert by_title.get(OBJ_NEXT) and by_title[OBJ_NEXT].lane == "next"
    assert "E2E_TEST Phase" in by_title and by_title["E2E_TEST Phase"].lane == "now"

    # Status preserved through _assess_item enrichment (the guard fix).
    assert by_title[OBJ_DONE].spec_status == "shipped"

    # Intent-first: the phase + specs are tier > 0 (rank above kind=gap items).
    spec_phase = [it for it in flat if it.kind in ("phase", "spec") and it.title.startswith("E2E_TEST")]
    assert spec_phase and all(_tier(sp) > 0 for sp in spec_phase)

    # Supersession: mark the shipped spec superseded → it leaves the projection.
    async with pool.connection() as db:
        await db.query("UPDATE agent_spec SET status='superseded' WHERE objective=$o", {"o": OBJ_DONE})
    roadmap2 = await compute_roadmap(PID, max_items=200)
    titles2 = {it.title for lane in roadmap2.lanes.values() for it in lane}
    assert OBJ_DONE not in titles2  # superseded specs are not projected (filtered, not capped)

    # Cleanup.
    async with pool.connection() as db:
        for obj in (OBJ_DONE, OBJ_NEXT):
            await db.query("DELETE agent_spec WHERE objective = $o", {"o": obj})
        await db.query("DELETE roadmap_phase WHERE title = 'E2E_TEST Phase'")
