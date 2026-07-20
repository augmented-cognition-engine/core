"""API tests for /portal/voice-audit/{product_id}."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_voice_audit_get_returns_thresholds():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool
    from core.engine.voice.audit import VOICE_AUDIT_AMBIENT_THRESHOLD, VOICE_AUDIT_TEASER_THRESHOLD

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {"email": "va@example.com"}

    try:
        # Seed at least one row so latest is non-null
        async with pool.connection() as db:
            await db.query("DELETE voice_audit_run WHERE product = product:test_va")
            await db.query(
                "CREATE voice_audit_run SET product = product:test_va, "
                "surface_scores = {briefing: {score: 1.0, total: 5}}, "
                "violations = [], overall_score = 1.0, trigger = 'manual', "
                "ran_at = time::now()"
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/voice-audit/product:test_va")
            assert r.status_code == 200, r.text
            data = r.json()
            assert "latest" in data
            assert "history" in data
            assert "thresholds" in data
            assert data["thresholds"]["ambient"] == VOICE_AUDIT_AMBIENT_THRESHOLD
            assert data["thresholds"]["teaser"] == VOICE_AUDIT_TEASER_THRESHOLD
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE voice_audit_run WHERE product = product:test_va")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_voice_audit_post_run_creates_row():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import parse_rows, pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {"email": "va2@example.com"}

    try:
        async with pool.connection() as db:
            await db.query("DELETE voice_audit_run WHERE product = product:test_va2")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/portal/voice-audit/product:test_va2/run")
            assert r.status_code == 200, r.text
            summary = r.json()
            assert "overall_score" in summary

        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT trigger FROM voice_audit_run WHERE product = product:test_va2"))
        assert any(r["trigger"] == "manual" for r in rows)
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE voice_audit_run WHERE product = product:test_va2")
