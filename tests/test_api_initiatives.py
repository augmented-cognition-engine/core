# tests/test_api_initiatives.py
"""API tests for initiative endpoints."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_user():
    return {"sub": "user:test", "product": "product:test"}


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[[]])
    return db


@pytest.fixture
def mock_pool(mock_db):
    p = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    p.connection = MagicMock(return_value=ctx)
    p.init = AsyncMock()
    p.close = AsyncMock()
    return p


@pytest.fixture
def app_with_mocks(mock_user, mock_pool, mock_db):
    """Create an app with mocked auth and DB."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Patch the pool in the initiatives module
    import core.engine.api.initiatives as init_mod

    original_pool = init_mod.pool
    init_mod.pool = mock_pool

    yield app, mock_db

    app.dependency_overrides.clear()
    init_mod.pool = original_pool


@pytest.mark.asyncio
async def test_create_initiative(app_with_mocks):
    """POST /initiatives creates initiative."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "initiative:abc",
                    "title": "Test Initiative",
                    "status": "planning",
                    "total_cost": 0.0,
                    "priority": "high",
                }
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/initiatives",
            json={
                "title": "Test Initiative",
                "description": "A test",
                "workspace_id": "workspace:test",
                "priority": "high",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "planning"


@pytest.mark.asyncio
async def test_list_initiatives(app_with_mocks):
    """GET /initiatives lists initiatives."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {"id": "initiative:1", "title": "Init 1", "status": "active"},
                {"id": "initiative:2", "title": "Init 2", "status": "planning"},
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/initiatives?product=product:test")
        assert resp.status_code == 200
        data = resp.json()
        assert "initiatives" in data


@pytest.mark.asyncio
async def test_activate_initiative(app_with_mocks):
    """POST /initiatives/{id}/activate transitions to active."""
    app, mock_db = app_with_mocks

    # First call is SELECT (returns ready initiative), second is UPDATE
    call_count = 0

    async def side_effect(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [[{"id": "initiative:abc", "status": "ready"}]]
        return [[]]

    mock_db.query = AsyncMock(side_effect=side_effect)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/initiatives/initiative:abc/activate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"


@pytest.mark.asyncio
async def test_approve_milestone(app_with_mocks):
    """POST /milestones/{id}/approve approves a milestone."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "milestone:ms1",
                    "status": "approved",
                }
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/milestones/milestone:ms1/approve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "approved"


@pytest.mark.asyncio
async def test_reject_milestone(app_with_mocks):
    """POST /milestones/{id}/reject rejects with feedback."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "milestone:ms1",
                    "status": "active",
                }
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/milestones/milestone:ms1/reject",
            json={
                "feedback": "Missing tests",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "rejected"


@pytest.mark.asyncio
async def test_list_milestones(app_with_mocks):
    """GET /initiatives/{id}/milestones lists milestones with work items."""
    app, mock_db = app_with_mocks

    call_count = 0

    async def side_effect(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: milestones
            return [[{"id": "milestone:ms1", "title": "M1", "sequence": 1, "status": "active"}]]
        # Subsequent: work items
        return [[]]

    mock_db.query = AsyncMock(side_effect=side_effect)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/initiatives/initiative:abc/milestones?product=product:test")
        assert resp.status_code == 200
        data = resp.json()
        assert "milestones" in data


@pytest.mark.asyncio
async def test_patch_initiative_status(app_with_mocks):
    """PATCH /initiatives/{id} updates status."""
    app, mock_db = app_with_mocks
    # patch_initiative makes 3 sequential queries:
    # 1. resolve caller's tenant from product
    # 2. verify initiative belongs to that tenant
    # 3. UPDATE ... RETURN AFTER
    mock_db.query = AsyncMock(
        side_effect=[
            [[{"tenant": "tenant:test"}]],
            [[{"id": "initiative:abc"}]],
            [[{"id": "initiative:abc", "title": "Test Initiative", "status": "active"}]],
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/initiatives/initiative:abc",
            json={"status": "active"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "active"


@pytest.mark.asyncio
async def test_patch_initiative_invalid_status(app_with_mocks):
    """PATCH /initiatives/{id} rejects invalid status values."""
    app, mock_db = app_with_mocks

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/initiatives/initiative:abc",
            json={"status": "invalid_status"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_initiative_no_fields(app_with_mocks):
    """PATCH /initiatives/{id} with no fields returns 422."""
    app, mock_db = app_with_mocks

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/initiatives/initiative:abc",
            json={},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_initiative_not_found(app_with_mocks):
    """PATCH /initiatives/{id} returns 404 when initiative not found."""
    app, mock_db = app_with_mocks
    # Tenant resolves OK; initiative check returns empty (not found)
    mock_db.query = AsyncMock(
        side_effect=[
            [[{"tenant": "tenant:test"}]],
            [[]],
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/initiatives/initiative:missing",
            json={"status": "active"},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_initiatives_returns_list(app_with_mocks):
    """GET /initiatives returns a list (at minimum empty)."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(return_value=[[]])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/initiatives")
        assert resp.status_code == 200
        data = resp.json()
        assert "initiatives" in data
        assert isinstance(data["initiatives"], list)


@pytest.mark.asyncio
async def test_get_initiatives_all_products(app_with_mocks):
    """GET /initiatives?all_products=true returns a tenant-wide list."""
    app, mock_db = app_with_mocks

    call_count = 0

    async def side_effect(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Tenant lookup
            return [[{"tenant": "tenant:default"}]]
        if call_count == 2:
            # Products lookup
            return [[{"id": "product:test", "name": "Test Product"}]]
        # Initiatives query
        return [[{"id": "initiative:1", "title": "Init 1", "status": "active", "product": "product:test"}]]

    mock_db.query = AsyncMock(side_effect=side_effect)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/initiatives?all_products=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "initiatives" in data
        assert isinstance(data["initiatives"], list)
        assert data["initiatives"][0]["product_name"] == "Test Product"


@pytest.mark.asyncio
async def test_decompose_rejects_initiative_without_spec(app_with_mocks):
    """POST /initiatives/{id}/decompose must 400 when initiative has no linked spec.

    Regression for the lazy fast-path: the prior behavior flipped status to
    'ready' with placeholder plan_data even when no real decomposition could
    happen. Same class as the qualify bug — a status that implies content
    landing without the content actually existing.

    The initiative must stay in 'planning'; no UPDATE should fire.
    """
    from unittest.mock import patch

    app, mock_db = app_with_mocks
    tracker_mock = AsyncMock()
    tracker_mock.get_initiative = AsyncMock(
        return_value={
            "id": "initiative:no_spec",
            "title": "An initiative without a spec",
            "status": "planning",
            # spec_id / source_spec deliberately absent
        }
    )

    with patch("core.engine.pm.tracker.InitiativeTracker", return_value=tracker_mock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/initiatives/initiative:no_spec/decompose")

    assert resp.status_code == 400
    assert "no linked spec" in resp.json()["detail"].lower()
    # No mutation against the DB: the guard runs BEFORE any UPDATE.
    update_queries = [c.args[0] for c in mock_db.query.call_args_list if c.args and "UPDATE" in c.args[0]]
    assert not update_queries, f"expected no UPDATE on rejection, got: {update_queries}"
