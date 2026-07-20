# tests/test_api_self_optimizer.py
"""Tests for the self-optimizer proposals API."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user():
    return {"sub": "user:1", "product": "product:default"}


@pytest.fixture
async def client():
    from core.engine.api.main import app

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def authed_client(mock_user):
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


def _make_pool(side_effects):
    """Build a mock pool whose connection().query returns side_effects in sequence."""
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(side_effect=side_effects)
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def _make_pool_single(return_value):
    """Pool that always returns the same value."""
    return _make_pool([return_value] * 10)


# ---------------------------------------------------------------------------
# Auth guards — unauthenticated requests must return 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_proposals_requires_auth(client):
    resp = await client.get("/self-optimizer/proposals")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_approve_proposal_requires_auth(client):
    resp = await client.post("/self-optimizer/proposals/self_optimizer_proposal:abc/approve")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dismiss_proposal_requires_auth(client):
    resp = await client.post("/self-optimizer/proposals/self_optimizer_proposal:abc/dismiss")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /self-optimizer/proposals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_proposals_returns_list(authed_client):
    fake_proposals = [
        {
            "id": "self_optimizer_proposal:1",
            "product": "product:default",
            "type": "skill",
            "status": "pending",
            "name": "Research Skill",
        },
        {
            "id": "self_optimizer_proposal:2",
            "product": "product:default",
            "type": "framework",
            "status": "pending",
            "name": "Clarity Framework",
        },
    ]
    mock_pool, mock_conn = _make_pool_single(fake_proposals)

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.get("/self-optimizer/proposals")

    assert resp.status_code == 200
    data = resp.json()
    assert "proposals" in data
    assert len(data["proposals"]) == 2


@pytest.mark.asyncio
async def test_list_proposals_empty(authed_client):
    mock_pool, _ = _make_pool_single([])

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.get("/self-optimizer/proposals")

    assert resp.status_code == 200
    assert resp.json() == {"proposals": []}


@pytest.mark.asyncio
async def test_list_proposals_filter_by_status(authed_client):
    mock_pool, mock_conn = _make_pool_single([])

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.get("/self-optimizer/proposals?status=approved")

    assert resp.status_code == 200
    call_args = mock_conn.query.call_args
    assert call_args[0][1].get("status") == "approved"


@pytest.mark.asyncio
async def test_list_proposals_filter_by_type(authed_client):
    mock_pool, mock_conn = _make_pool_single([])

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.get("/self-optimizer/proposals?type=skill")

    assert resp.status_code == 200
    call_args = mock_conn.query.call_args
    assert call_args[0][1].get("type") == "skill"


@pytest.mark.asyncio
async def test_list_proposals_filter_by_status_and_type(authed_client):
    mock_pool, mock_conn = _make_pool_single([])

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.get("/self-optimizer/proposals?status=pending&type=framework")

    assert resp.status_code == 200
    params = mock_conn.query.call_args[0][1]
    assert params.get("status") == "pending"
    assert params.get("type") == "framework"


# ---------------------------------------------------------------------------
# POST /self-optimizer/proposals/{id}/approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_not_found(authed_client):
    mock_pool, _ = _make_pool_single([])

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:missing/approve")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_skill_proposal(authed_client):
    proposal = {
        "id": "self_optimizer_proposal:1",
        "product": "product:default",
        "type": "skill",
        "status": "pending",
        "name": "Research Synthesis",
        "description": "Synthesise research insights",
        "draft": {
            "jobs": [{"name": "synthesise", "archetype": "analyst", "mode": "proactive"}],
            "activation_signals": [],
        },
    }
    created_skill = {"id": "skill:abc", "slug": "research-synthesis", "name": "Research Synthesis"}

    mock_pool, _ = _make_pool(
        [
            proposal,  # fetch proposal (ONLY query -> single dict)
            [{}],  # UPDATE approved
            [created_skill],  # CREATE skill
        ]
    )

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:1/approve")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["type"] == "skill"
    assert data["created"] is not None


@pytest.mark.asyncio
async def test_approve_framework_proposal(authed_client):
    proposal = {
        "id": "self_optimizer_proposal:2",
        "product": "product:default",
        "type": "framework",
        "status": "pending",
        "name": "Clarity Lens",
        "description": "Think clearly about ambiguous problems",
        "draft": {
            "system_prompt": "Always reason from first principles.",
            "activation_signals": [],
            "family": "epistemic",
        },
    }
    created_fw = {"id": "framework:xyz", "slug": "clarity-lens", "name": "Clarity Lens"}

    mock_pool, _ = _make_pool(
        [
            proposal,
            [{}],
            [created_fw],
        ]
    )

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:2/approve")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["type"] == "framework"
    assert data["created"] is not None


@pytest.mark.asyncio
async def test_approve_already_approved_returns_409(authed_client):
    proposal = {
        "id": "self_optimizer_proposal:3",
        "product": "product:default",
        "type": "skill",
        "status": "approved",
        "name": "Already Done",
        "draft": {},
    }
    mock_pool, _ = _make_pool_single(proposal)

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:3/approve")

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_approve_dismissed_returns_409(authed_client):
    proposal = {
        "id": "self_optimizer_proposal:6",
        "product": "product:default",
        "type": "skill",
        "status": "dismissed",
        "name": "Was Dismissed",
        "draft": {},
    }
    mock_pool, _ = _make_pool_single(proposal)

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:6/approve")

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_approve_unknown_type_still_marks_approved(authed_client):
    """A proposal with type='neither' should be approved with created=None."""
    proposal = {
        "id": "self_optimizer_proposal:7",
        "product": "product:default",
        "type": "neither",
        "status": "pending",
        "name": "Unknown Type",
        "draft": {},
    }
    mock_pool, _ = _make_pool(
        [
            proposal,
            [{}],
        ]
    )

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:7/approve")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["created"] is None


# ---------------------------------------------------------------------------
# POST /self-optimizer/proposals/{id}/dismiss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismiss_proposal(authed_client):
    proposal = {
        "id": "self_optimizer_proposal:4",
        "product": "product:default",
        "type": "skill",
        "status": "pending",
        "name": "Unwanted Skill",
        "draft": {},
    }
    mock_pool, _ = _make_pool(
        [
            proposal,  # fetch
            [{}],  # UPDATE dismiss
        ]
    )

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:4/dismiss")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "dismissed"
    assert data["proposal_id"] == "self_optimizer_proposal:4"


@pytest.mark.asyncio
async def test_dismiss_not_found(authed_client):
    mock_pool, _ = _make_pool_single([])

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:missing/dismiss")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_already_dismissed_returns_409(authed_client):
    proposal = {
        "id": "self_optimizer_proposal:5",
        "product": "product:default",
        "type": "skill",
        "status": "dismissed",
        "name": "Already Dismissed",
        "draft": {},
    }
    mock_pool, _ = _make_pool_single(proposal)

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:5/dismiss")

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# _slugify helper
# ---------------------------------------------------------------------------


def test_slugify_basic():
    from core.engine.api.self_optimizer import _slugify

    assert _slugify("Research Synthesis") == "research-synthesis"
    assert _slugify("  Multi   Word  ") == "multi-word"
    assert _slugify("Café & Boulangerie!") == "caf-boulangerie"
    assert _slugify("") == "proposal"
    assert _slugify("Already-Slugged") == "already-slugged"
