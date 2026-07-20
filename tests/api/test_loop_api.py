"""API tests for /portal/loop/{product_id} — loop visibility timeline.

Cohort B #5 (Loop Visibility Timeline). Mirrors the test pattern in
tests/api/test_journey_api.py: TestClient against the real ASGI app, real
SurrealDB pool, dependency override for auth.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_loop_empty_product_returns_empty_iterations():
    """Empty product → 200 with iterations=[] plus window/generated_at/product_id."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "loop1@example.com",
        "product": "product:test_loop_empty",
    }

    try:
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_loop_empty")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/loop/product:test_loop_empty?window=day")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["iterations"] == []
            assert data["window"] == "day"
            assert "generated_at" in data and data["generated_at"]
            assert data["product_id"] == "product:test_loop_empty"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_loop_seeded_product_clusters_into_two_iterations():
    """3 events: two within ~30s of each other and a third ~5 min later
    cluster into 2 iteration cards (first has 2 event_ids, second has 1).

    Phrases pass audit_partner_voice and never carry the [unknown topic:
    fallback string."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool
    from core.engine.voice.audit import audit_partner_voice

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "loop2@example.com",
        "product": "product:test_loop_seed",
    }

    try:
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_loop_seed")
            # Two events ~30s apart (one cluster), one ~5min later (separate cluster).
            await db.query(
                "CREATE journey_event SET topic='capture', "
                "product=product:test_loop_seed, payload={summary:'a'}, "
                "occurred_at=time::now() - 10m"
            )
            await db.query(
                "CREATE journey_event SET topic='gap.detected', "
                "product=product:test_loop_seed, payload={summary:'b'}, "
                "occurred_at=time::now() - 10m + 30s"
            )
            await db.query(
                "CREATE journey_event SET topic='capture', "
                "product=product:test_loop_seed, payload={summary:'c'}, "
                "occurred_at=time::now() - 5m"
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/loop/product:test_loop_seed?window=day")
            assert r.status_code == 200, r.text
            data = r.json()
            iters = data["iterations"]
            assert len(iters) == 2, f"expected 2 iteration cards, got: {iters}"

            first, second = iters[0], iters[1]
            # ASC ordering — earlier cluster has 2 events, later has 1.
            assert len(first["event_ids"]) == 2, first
            assert first["event_count"] == 2
            assert len(second["event_ids"]) == 1, second
            assert second["event_count"] == 1

            for it in iters:
                assert it["phrase"], "iteration missing phrase"
                assert "[unknown topic:" not in it["phrase"], it["phrase"]
                # Partner-voice audit returns AuditResult dataclass, .violations
                # is the issue list — empty list = clean.
                result = audit_partner_voice(it["phrase"])
                assert result.violations == [], f"voice violations in {it['phrase']!r}: {result.violations}"
                assert it["topic_summary"]
                assert it["started_at"]
                assert it["ended_at"]
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_loop_seed")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_loop_window_param_validation():
    """?window=week accepted (200); ?window=garbage rejected (422)."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "loop3@example.com",
        "product": "product:test_loop_win",
    }

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r_ok = await client.get("/portal/loop/product:test_loop_win?window=week")
            assert r_ok.status_code == 200, r_ok.text
            assert r_ok.json()["window"] == "week"

            r_bad = await client.get("/portal/loop/product:test_loop_win?window=garbage")
            assert r_bad.status_code == 422, r_bad.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_loop_requires_auth():
    """Missing token → 401."""
    from core.engine.api.main import app
    from core.engine.core.db import pool

    await pool.init()
    # No dependency override — real auth path runs and rejects missing bearer.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/portal/loop/product:test_loop_auth?window=day")
        assert r.status_code == 401, r.text
