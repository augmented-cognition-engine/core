"""Tests for the composition_trace helper."""

from __future__ import annotations

import pytest


def test_build_required_fields():
    from core.engine.cognition.composition_trace import build

    t = build(meta_skills=["systems_intelligence"], frame="scaling-architecture", signals={"phase": "BUILD"})
    assert t["meta_skills"] == ["systems_intelligence"]
    assert t["frame"] == "scaling-architecture"
    assert t["signals"] == {"phase": "BUILD"}
    assert "star_trace_id" not in t or t["star_trace_id"] is None


def test_build_with_star_trace_id():
    from core.engine.cognition.composition_trace import build

    t = build(meta_skills=["a", "b"], frame="f", signals={}, star_trace_id="star_trace:xyz")
    assert t["star_trace_id"] == "star_trace:xyz"


def test_build_validates_meta_skills_nonempty():
    from core.engine.cognition.composition_trace import build

    with pytest.raises(ValueError, match="meta_skills.*non-empty"):
        build(meta_skills=[], frame="f", signals={})


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_attach_writes_trace_to_journey_event():
    from core.engine.cognition.composition_trace import attach, build
    from core.engine.core.db import parse_one, parse_record_id, parse_rows, pool

    await pool.init()
    async with pool.connection() as db:
        result = await db.query(
            "CREATE journey_event SET topic='test.attach', product=<record>$pid, "
            "payload={}, occurred_at=time::now() RETURN AFTER",
            {"pid": "product:platform"},
        )
        je_id = str(parse_one(result)["id"])

    try:
        trace = build(meta_skills=["verification_intelligence"], frame="testing", signals={"phase": "BUILD"})
        await attach(pool, je_id, trace)

        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT composition_trace FROM $jid",
                    {"jid": parse_record_id(je_id)},
                )
            )
        assert rows[0]["composition_trace"]["meta_skills"] == ["verification_intelligence"]
        assert rows[0]["composition_trace"]["frame"] == "testing"
    finally:
        async with pool.connection() as db:
            await db.query("DELETE $jid", {"jid": parse_record_id(je_id)})
