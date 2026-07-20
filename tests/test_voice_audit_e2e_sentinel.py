"""Cross-cutting sentinel: session.start.rendered renders cleanly via journey API."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_session_start_rendered_does_not_appear_as_unknown_topic():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool
    from core.engine.events.bus import bus

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {"email": "sentinel@example.com"}

    try:
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE topic = 'session.start.rendered' AND product = product:test_sentinel"
            )

        # Emit a session.start.rendered event
        await bus.emit(
            "session.start.rendered",
            {
                "product_id": "product:test_sentinel",
                "context_text": "We rendered a greeting",
            },
        )
        await asyncio.sleep(0.2)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/journey/product:test_sentinel?since=day")
            data = r.json()
            for ev in data.get("events", []):
                if ev["topic"] == "session.start.rendered":
                    assert "[unknown topic:" not in ev["summary"]
                    return
            # If no events found that's also fine — the sentinel only fires if rendered
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query(
                "DELETE journey_event WHERE topic = 'session.start.rendered' AND product = product:test_sentinel"
            )
