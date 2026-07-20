"""API tests for /portal/journey/{product_id}."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_journey_returns_events_for_product():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {"email": "j@example.com", "sub": "j"}

    try:
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_jrn")
            await db.query(
                "CREATE journey_event SET topic='canvas.thread.committed', "
                "product=product:test_jrn, payload={topic:'test thread'}, "
                "occurred_at=time::now() - 1h"
            )
            await db.query(
                "CREATE journey_event SET topic='gap.detected', product=product:test_jrn, "
                "payload={pillar:'security'}, occurred_at=time::now() - 30m"
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/journey/product:test_jrn?since=week")
            assert r.status_code == 200, r.text
            data = r.json()
            assert "events" in data
            assert len(data["events"]) >= 2
            for ev in data["events"]:
                assert "id" in ev
                assert "topic" in ev
                assert "occurred_at" in ev
                assert "summary" in ev
                assert "edges_in" in ev
                assert "edges_out" in ev
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_jrn")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_journey_topics_filter():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {"email": "j2@example.com"}

    try:
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_jrn2")
            await db.query(
                "CREATE journey_event SET topic='canvas.thread.committed', "
                "product=product:test_jrn2, payload={topic:'a'}, occurred_at=time::now()"
            )
            await db.query(
                "CREATE journey_event SET topic='gap.detected', "
                "product=product:test_jrn2, payload={pillar:'b'}, occurred_at=time::now()"
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/journey/product:test_jrn2?topics=gap.detected")
            data = r.json()
            assert all(e["topic"] == "gap.detected" for e in data["events"])
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_jrn2")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_journey_event_with_trace_includes_headline():
    """Boundary: events with composition_trace get a composition_headline field;
    events without get null. Pins the API contract for the composition panel."""
    from httpx import ASGITransport, AsyncClient

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "h@example.com",
        "product": "product:test_headline",
    }

    try:
        # Cleanup + seed
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE product = product:test_headline",
                {},
            )
            await db.query(
                "CREATE journey_event SET product = product:test_headline, "
                "topic = 'gap.detected', "
                "occurred_at = time::now(), "
                "payload = {summary: 'seed gap'}, "
                "composition_trace = {meta_skills: ['systems_intelligence'], "
                "frame: 'scaling-architecture', signals: {phase: 'BUILD'}}",
                {},
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/journey/product:test_headline?since=day")
            assert r.status_code == 200, r.text
            data = r.json()
            events = data.get("events", [])
            assert events, "expected at least one event"
            traced = next((e for e in events if e.get("composition_trace")), None)
            assert traced is not None, "expected an event with composition_trace"
            headline = traced.get("composition_headline")
            assert headline is not None, f"missing composition_headline on traced event: {traced}"
            assert headline.startswith("We composed "), headline
            assert "systems intelligence" in headline
            assert "your phase is BUILD" in headline
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE product = product:test_headline",
                {},
            )


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_journey_response_includes_active_discipline_when_present():
    """Boundary: if any event in the response has discipline_classified,
    response carries top-level active_discipline."""
    from httpx import ASGITransport, AsyncClient

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "ad@example.com",
        "product": "product:test_disc",
    }

    try:
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE product = product:test_disc",
                {},
            )
            await db.query(
                "CREATE journey_event SET product = product:test_disc, "
                "topic = 'gap.detected', "
                "occurred_at = time::now(), "
                "payload = {summary: 'seed for discipline'}, "
                "composition_trace = {meta_skills: ['ux_intel'], frame: 'ux-frame', "
                "signals: {discipline_classified: 'ux', phase: 'BUILD'}}",
                {},
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/journey/product:test_disc?since=day")
            assert r.status_code == 200, r.text
            data = r.json()
            ad = data.get("active_discipline")
            assert ad is not None, f"missing active_discipline: keys={list(data.keys())}"
            assert ad["discipline"] == "ux"
            assert ad["phrase"].startswith("we see you're shaping ux")
            assert "phase BUILD" in ad["phrase"]
            assert ad["source_event_id"]
            assert ad["observed_at"]
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE product = product:test_disc",
                {},
            )


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_journey_response_active_discipline_null_when_absent():
    """Empty fixture: no events with discipline_classified → null field, not missing."""
    from httpx import ASGITransport, AsyncClient

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "ad2@example.com",
        "product": "product:test_disc_empty",
    }

    try:
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE product = product:test_disc_empty",
                {},
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/journey/product:test_disc_empty?since=day")
            assert r.status_code == 200, r.text
            data = r.json()
            assert "active_discipline" in data, "field missing entirely"
            assert data["active_discipline"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_journey_response_includes_active_handoff_when_present():
    """Boundary: if any event in the response has topic handoff.recognized,
    response carries top-level active_handoff."""
    from httpx import ASGITransport, AsyncClient

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "ah@example.com",
        "product": "product:test_handoff",
    }

    try:
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE product = product:test_handoff",
                {},
            )
            await db.query(
                "CREATE journey_event SET product = product:test_handoff, "
                "topic = 'handoff.recognized', "
                "occurred_at = time::now(), "
                "payload = {suggested_external_tool: 'Claude'}",
                {},
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/journey/product:test_handoff?since=day")
            assert r.status_code == 200, r.text
            data = r.json()
            ah = data.get("active_handoff")
            assert ah is not None, f"missing active_handoff: keys={list(data.keys())}"
            assert ah["tool"] == "Claude"
            assert ah["url"] == "https://claude.ai"
            assert ah["phrase"].startswith("we recognized")
            assert ah["source_event_id"]
            assert ah["observed_at"]
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE product = product:test_handoff",
                {},
            )


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_journey_response_active_handoff_null_when_absent():
    """Empty fixture: no handoff events → null field, not missing."""
    from httpx import ASGITransport, AsyncClient

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "ah2@example.com",
        "product": "product:test_handoff_empty",
    }

    try:
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE product = product:test_handoff_empty",
                {},
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/journey/product:test_handoff_empty?since=day")
            assert r.status_code == 200, r.text
            data = r.json()
            assert "active_handoff" in data, "field missing entirely"
            assert data["active_handoff"] is None
    finally:
        app.dependency_overrides.clear()
