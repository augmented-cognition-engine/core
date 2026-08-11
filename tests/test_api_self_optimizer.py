# tests/test_api_self_optimizer.py
"""Tests for the self-optimizer proposals API."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user():
    return {
        "sub": "user:1",
        "product": "product:default",
        "authorities": ["cognition-review"],
    }


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


class _CanonicalService:
    def __init__(self, _store):
        pass

    async def propose(self, proposal):
        return proposal

    async def review(self, **_kwargs):
        return SimpleNamespace(
            receipt_id="cognition_review:test",
            result_revision_id="cognition_revision:test",
            result_head_id="cognition_head:test",
        )


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
@pytest.mark.parametrize(
    "proposal_id",
    (
        "foreign_table:abc",
        "self_optimizer_proposal:",
        "self_optimizer_proposal:abc/def",
        "self_optimizer_proposal:abc:def",
    ),
)
async def test_approve_rejects_unpinned_or_malformed_record_before_query(
    authed_client,
    proposal_id,
):
    mock_pool, mock_conn = _make_pool_single([])

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post(f"/self-optimizer/proposals/{proposal_id}/approve")

    assert resp.status_code == 404
    mock_conn.query.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_lookup_is_pinned_to_legacy_proposal_table(authed_client):
    mock_pool, mock_conn = _make_pool_single([])

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:missing/approve")

    assert resp.status_code == 404
    query, params = mock_conn.query.await_args.args
    assert "type::record('self_optimizer_proposal', $record_key)" in query
    assert "<record>$id" not in query
    assert params == {"record_key": "missing"}


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
    mock_pool, _ = _make_pool([proposal])

    with (
        patch("core.engine.api.self_optimizer.pool", mock_pool),
        patch("core.engine.api.self_optimizer.DurableCognitionGovernanceService", _CanonicalService),
        patch(
            "core.engine.api.self_optimizer._project_legacy_state",
            AsyncMock(return_value="updated"),
        ),
    ):
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
            "archetype_affinity": {"analyst": 0.9},
            "mode_affinity": {"deliberative": 0.8},
            "composability": {"complements": ["inversion"], "conflicts": []},
        },
    }
    mock_pool, _ = _make_pool([proposal])

    with (
        patch("core.engine.api.self_optimizer.pool", mock_pool),
        patch("core.engine.api.self_optimizer.DurableCognitionGovernanceService", _CanonicalService),
        patch(
            "core.engine.api.self_optimizer._project_legacy_state",
            AsyncMock(return_value="updated"),
        ),
    ):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:2/approve")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["type"] == "framework"
    assert data["created"] is not None
    assert data["created"]["revision_id"] == "cognition_revision:test"
    assert data["canonical_review_id"] == "cognition_review:test"


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
async def test_approve_unknown_type_is_rejected(authed_client):
    """Unknown proposal types must not become phantom approvals."""
    proposal = {
        "id": "self_optimizer_proposal:7",
        "product": "product:default",
        "type": "neither",
        "status": "pending",
        "name": "Unknown Type",
        "draft": {},
    }
    mock_pool, mock_conn = _make_pool([proposal])

    with patch("core.engine.api.self_optimizer.pool", mock_pool):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:7/approve")

    assert resp.status_code == 422
    assert "Unsupported proposal type" in resp.json()["detail"]
    assert mock_conn.query.await_count == 1


@pytest.mark.asyncio
async def test_failed_framework_materialisation_does_not_mark_proposal_approved(authed_client):
    proposal = {
        "id": "self_optimizer_proposal:8",
        "product": "product:default",
        "type": "framework",
        "status": "pending",
        "name": "Broken Framework",
        "description": "Must remain retryable",
        "draft": {"system_prompt": "Reason carefully."},
    }
    mock_pool, mock_conn = _make_pool([proposal])

    class FailedService(_CanonicalService):
        async def propose(self, proposal):
            from core.engine.cognition.governance_persistence import CognitionPersistenceError

            raise CognitionPersistenceError("canonical_persistence_failed")

    with (
        patch("core.engine.api.self_optimizer.pool", mock_pool),
        patch("core.engine.api.self_optimizer.DurableCognitionGovernanceService", FailedService),
    ):
        resp = await authed_client.post("/self-optimizer/proposals/self_optimizer_proposal:8/approve")

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "canonical_persistence_failed"}
    assert mock_conn.query.await_count == 1


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
        "draft": {
            "jobs": [{"name": "inspect", "archetype": "analyst", "mode": "procedural"}],
        },
    }
    mock_pool, _ = _make_pool([proposal])

    with (
        patch("core.engine.api.self_optimizer.pool", mock_pool),
        patch("core.engine.api.self_optimizer.DurableCognitionGovernanceService", _CanonicalService),
        patch(
            "core.engine.api.self_optimizer._project_legacy_state",
            AsyncMock(return_value="updated"),
        ),
    ):
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


@pytest.mark.asyncio
async def test_legacy_projection_update_is_pinned_to_proposal_table(monkeypatch):
    from core.engine.api import self_optimizer

    mock_pool, mock_conn = _make_pool_single([])
    monkeypatch.setattr(self_optimizer, "pool", mock_pool)

    result = await self_optimizer._project_legacy_state(
        "self_optimizer_proposal:abc",
        status="approved",
        canonical_proposal_id="cognition_proposal:abc",
        canonical_review_id="cognition_review_receipt:abc",
    )

    assert result == "updated"
    query, params = mock_conn.query.await_args.args
    assert "UPDATE ONLY type::record('self_optimizer_proposal', $record_key)" in query
    assert "<record>$id" not in query
    assert params["record_key"] == "abc"


@pytest.mark.asyncio
async def test_legacy_projection_rejects_foreign_table_before_mutation(monkeypatch):
    from core.engine.api import self_optimizer

    mock_pool, mock_conn = _make_pool_single([])
    monkeypatch.setattr(self_optimizer, "pool", mock_pool)

    with pytest.raises(self_optimizer.HTTPException) as failure:
        await self_optimizer._project_legacy_state(
            "foreign_table:abc",
            status="approved",
            canonical_proposal_id="cognition_proposal:abc",
            canonical_review_id="cognition_review_receipt:abc",
        )

    assert failure.value.status_code == 404
    mock_conn.query.assert_not_awaited()


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
