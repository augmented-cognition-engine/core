# tests/test_api_conflicts.py
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from core.engine.api.main import app

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_conflicts_requires_auth(client):
    resp = await client.get("/conflicts?product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_resolve_conflict_requires_auth(client):
    resp = await client.post(
        "/conflicts/conflict:test/resolve",
        json={"resolution_type": "keep_b", "resolution": "test"},
    )
    assert resp.status_code == 401


def test_valid_resolution_types():
    from core.engine.api.conflicts import VALID_RESOLUTION_TYPES

    assert "keep_a" in VALID_RESOLUTION_TYPES
    assert "keep_b" in VALID_RESOLUTION_TYPES
    assert "keep_both" in VALID_RESOLUTION_TYPES
    assert "merge" in VALID_RESOLUTION_TYPES
    assert len(VALID_RESOLUTION_TYPES) == 4


def test_conflict_scope_rejects_cross_product_access():
    from core.engine.api.conflicts import _scoped_product

    with pytest.raises(HTTPException) as exc:
        _scoped_product("product:other", {"sub": "user:test", "product": "product:test"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_conflict_list_surfaces_claims_provenance_and_required_action():
    from core.engine.api import conflicts as api

    db = AsyncMock()
    db.query = AsyncMock(
        side_effect=[
            [
                {
                    "id": "conflict:c1",
                    "insight_a": "insight:a",
                    "insight_b": "insight:b",
                    "explanation": "The supported version differs",
                    "status": "pending",
                    "detected_by": "conflict_detector",
                }
            ],
            {
                "id": "insight:a",
                "product": "product:test",
                "content": "Version 18 is current",
                "confidence": 0.8,
                "status": "contested",
                "source_domain": "human_capture",
                "source_observations": ["observation:a"],
            },
            {
                "id": "insight:b",
                "product": "product:test",
                "content": "Version 19 is current",
                "confidence": 0.9,
                "status": "contested",
                "source_domain": "tool_research",
                "source_observations": ["observation:b"],
            },
        ]
    )

    class FakePool:
        @asynccontextmanager
        async def connection(self):
            yield db

    with patch.object(api, "pool", new=FakePool()):
        result = await api.list_conflicts(
            product=None,
            status="pending",
            limit=50,
            user={"sub": "user:test", "product": "product:test"},
        )

    conflict = result["conflicts"][0]
    assert conflict["product"] == "product:test"
    assert conflict["attention"] == {
        "required": True,
        "code": "contested_truth",
        "operational_state": "quarantined",
        "resolution_endpoint": "/conflicts/conflict:c1/resolve",
        "allowed_actions": ["keep_a", "keep_b", "keep_both", "merge"],
    }
    assert [claim["status"] for claim in conflict["claims"]] == ["contested", "contested"]
    assert conflict["claims"][0]["provenance"]["source_observations"] == ["observation:a"]


@pytest.mark.asyncio
async def test_conflict_resolution_is_product_scoped_and_reactivates_only_selected_claim():
    from core.engine.api import conflicts as api

    db = AsyncMock()
    db.query = AsyncMock(
        side_effect=[
            {
                "id": "conflict:c1",
                "product": "product:test",
                "status": "pending",
                "insight_a": "insight:a",
                "insight_b": "insight:b",
            },
            [],
            [],
            [],
            {"id": "conflict:c1", "product": "product:test", "status": "resolved"},
        ]
    )

    class FakePool:
        @asynccontextmanager
        async def connection(self):
            yield db

    with patch.object(api, "pool", new=FakePool()):
        result = await api.resolve_conflict(
            "conflict:c1",
            api.ConflictResolveRequest(resolution_type="keep_a", resolution="A has authoritative provenance"),
            user={"sub": "user:test", "product": "product:test"},
        )

    assert result["status"] == "resolved"
    first_query = db.query.call_args_list[0]
    assert "product = <record>$product" in first_query.args[0]
    assert first_query.args[1]["product"] == "product:test"
    update_queries = [call.args[0] for call in db.query.call_args_list]
    assert any("status = 'active'" in query for query in update_queries)
    assert any("status = 'superseded'" in query for query in update_queries)
