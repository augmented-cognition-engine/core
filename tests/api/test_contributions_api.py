"""E2E API test for /portal/contributions/{product_id}."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_contributions_get_returns_metrics_and_headline():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "c@example.com",
        "product": "product:test_contrib",
    }

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/contributions/product:test_contrib")
            assert r.status_code == 200, r.text
            data = r.json()
            assert {
                "prs_reviewed",
                "gaps_caught",
                "you_shipped",
                "we_let_go",
                "effectiveness",
                "tasks_completed",
                "cost_saved_usd",
            }.issubset(set(data["metrics"].keys()))
            assert "headline" in data
            assert "we" in data["headline"].lower()
            assert data["window_days"] == 30
            assert set(data["deep_links"].keys()) == set(data["metrics"].keys())
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_contributions_404s_on_cross_tenant():
    """verify_product_access guard rejects mismatched product_id with 404."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "c@example.com",
        "product": "product:tenant_a",
    }

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/portal/contributions/product:tenant_b")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
