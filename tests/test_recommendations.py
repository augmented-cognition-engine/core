# tests/test_recommendations.py
"""Tests for the recommendation engine and API."""

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
    return _make_pool([return_value] * 50)


# ---------------------------------------------------------------------------
# Auth guard tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recommendations_requires_auth(client):
    resp = await client.get("/recommendations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dismiss_requires_auth(client):
    resp = await client.post("/recommendations/rec_abc/dismiss")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_execute_requires_auth(client):
    resp = await client.post("/recommendations/rec_abc/execute")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /recommendations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recommendations_returns_list(authed_client):
    """When generate_recommendations returns recs, API wraps them."""
    fake_recs = [
        {
            "id": "rec_abc",
            "type": "risk",
            "title": "db.py is fragile",
            "description": "High churn",
            "action": "review",
            "action_prompt": "Review db.py",
            "severity": "high",
            "source": "graph_analysis",
            "related_files": ["core/engine/core/db.py"],
        }
    ]

    with patch("core.engine.graph.recommendations.generate_recommendations", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = fake_recs
        resp = await authed_client.get("/recommendations?graph_id=default&limit=8")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["recommendations"][0]["id"] == "rec_abc"
    assert data["recommendations"][0]["type"] == "risk"


@pytest.mark.asyncio
async def test_get_recommendations_empty(authed_client):
    """When no recommendations, returns empty list."""
    with patch("core.engine.graph.recommendations.generate_recommendations", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = []
        resp = await authed_client.get("/recommendations")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["recommendations"] == []


@pytest.mark.asyncio
async def test_get_recommendations_handles_error(authed_client):
    """When generator raises, API returns empty list gracefully."""
    with patch("core.engine.graph.recommendations.generate_recommendations", new_callable=AsyncMock) as mock_gen:
        mock_gen.side_effect = Exception("DB down")
        resp = await authed_client.get("/recommendations")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


# ---------------------------------------------------------------------------
# POST /recommendations/{id}/dismiss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismiss_recommendation(authed_client):
    with patch("core.engine.graph.recommendations.dismiss") as mock_dismiss:
        resp = await authed_client.post("/recommendations/rec_xyz/dismiss")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "rec_xyz"
    assert data["status"] == "dismissed"
    mock_dismiss.assert_called_once_with("rec_xyz")


# ---------------------------------------------------------------------------
# POST /recommendations/{id}/execute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_recommendation_creates_task(authed_client):
    fake_recs = [
        {
            "id": "rec_abc",
            "type": "risk",
            "title": "Fix db.py",
            "description": "High churn",
            "action": "fix",
            "action_prompt": "Review and fix db.py error handling",
            "severity": "high",
            "source": "graph_analysis",
            "related_files": ["core/engine/core/db.py"],
        }
    ]
    mock_pool, _ = _make_pool_single({"id": "task_queue:created123"})

    with (
        patch("core.engine.graph.recommendations.generate_recommendations", new_callable=AsyncMock) as mock_gen,
        patch("core.engine.api.recommendations.pool", mock_pool),
    ):
        mock_gen.return_value = fake_recs
        resp = await authed_client.post("/recommendations/rec_abc/execute?graph_id=default")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "rec_abc"
    assert data["status"] == "executing"
    assert "task_id" in data


@pytest.mark.asyncio
async def test_execute_recommendation_not_found(authed_client):
    with patch("core.engine.graph.recommendations.generate_recommendations", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = []
        resp = await authed_client.post("/recommendations/rec_nonexistent/execute?graph_id=default")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Recommendation engine unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_fragile_code_detection():
    """Fragile code analyzer detects high-churn files with many dependents."""
    from core.engine.graph.recommendations import _analyze_fragile_code, clear_cache

    clear_cache()

    fragile_files = [
        {"path": "core/engine/core/db.py", "change_frequency": 8, "name": "db.py"},
    ]
    dep_count = {"cnt": 20}

    mock_pool, _ = _make_pool([fragile_files, dep_count])

    with patch("core.engine.graph.recommendations.pool", mock_pool):
        recs = await _analyze_fragile_code("default")

    assert len(recs) >= 1
    assert recs[0]["type"] == "risk"
    assert recs[0]["severity"] == "high"
    assert "db.py" in recs[0]["title"]


@pytest.mark.asyncio
async def test_engine_fragile_code_empty():
    """No fragile files means no recommendations."""
    from core.engine.graph.recommendations import _analyze_fragile_code

    mock_pool, _ = _make_pool_single([])

    with patch("core.engine.graph.recommendations.pool", mock_pool):
        recs = await _analyze_fragile_code("default")

    assert recs == []


@pytest.mark.asyncio
async def test_engine_code_quality_large_modules():
    """Code quality analyzer flags large modules."""
    from core.engine.graph.recommendations import _analyze_code_quality

    large_modules = [
        {"file_path": "core/engine/api/main.py", "func_count": 25},
    ]

    mock_pool, _ = _make_pool(
        [
            large_modules,  # large module query
            [],  # circular deps query
            [],  # untested files query
            [],  # test files query
        ]
    )

    with patch("core.engine.graph.recommendations.pool", mock_pool):
        recs = await _analyze_code_quality("default")

    assert len(recs) >= 1
    assert recs[0]["type"] == "improvement"
    assert "splitting" in recs[0]["title"].lower() or "split" in recs[0]["description"].lower()


@pytest.mark.asyncio
async def test_engine_stale_decisions():
    """Stale decision analyzer detects old decisions."""
    from core.engine.graph.recommendations import _analyze_stale_decisions

    old_decisions = [
        {
            "id": "graph_decision:abc",
            "title": "Use SurrealDB",
            "description": "Chose SurrealDB for graph storage",
            "timestamp": "2025-01-01T00:00:00Z",
            "related_files": ["core/engine/core/db.py"],
        },
    ]

    mock_pool, _ = _make_pool_single(old_decisions)

    with patch("core.engine.graph.recommendations.pool", mock_pool):
        recs = await _analyze_stale_decisions("default")

    assert len(recs) == 1
    assert recs[0]["type"] == "suggestion"
    assert "Use SurrealDB" in recs[0]["title"]


@pytest.mark.asyncio
async def test_engine_self_optimizer_proposals():
    """Self-optimizer analyzer converts proposals to recommendations."""
    from core.engine.graph.recommendations import _analyze_self_optimizer_proposals

    proposals = [
        {
            "id": "self_optimizer_proposal:1",
            "name": "Add retry logic",
            "description": "Several API calls lack retry handling",
            "type": "improvement",
            "status": "pending",
        }
    ]

    mock_pool, _ = _make_pool_single(proposals)

    with patch("core.engine.graph.recommendations.pool", mock_pool):
        recs = await _analyze_self_optimizer_proposals("default")

    assert len(recs) == 1
    assert recs[0]["type"] == "improvement"
    assert "retry" in recs[0]["title"].lower()


@pytest.mark.asyncio
async def test_engine_caching():
    """Recommendations are cached for 1 hour."""
    from core.engine.graph.recommendations import (
        _get_cached,
        _set_cached,
        clear_cache,
    )

    clear_cache()
    assert _get_cached("default") is None

    fake_recs = [{"id": "rec_1", "type": "risk", "title": "test"}]
    _set_cached("default", fake_recs)

    cached = _get_cached("default")
    assert cached is not None
    assert len(cached) == 1
    assert cached[0]["id"] == "rec_1"

    clear_cache("default")
    assert _get_cached("default") is None


@pytest.mark.asyncio
async def test_engine_dismiss_filters():
    """Dismissed recommendations are filtered from results."""
    from core.engine.graph.recommendations import (
        _dismissed,
        clear_cache,
        dismiss,
        is_dismissed,
    )

    clear_cache()
    _dismissed.clear()

    assert not is_dismissed("rec_1")
    dismiss("rec_1")
    assert is_dismissed("rec_1")

    _dismissed.clear()


@pytest.mark.asyncio
async def test_rec_id_deterministic():
    """Recommendation IDs are deterministic for the same seed."""
    from core.engine.graph.recommendations import _rec_id

    id1 = _rec_id("fragile:engine/core/db.py")
    id2 = _rec_id("fragile:engine/core/db.py")
    id3 = _rec_id("fragile:engine/api/main.py")

    assert id1 == id2
    assert id1 != id3
    assert id1.startswith("rec_")


@pytest.mark.asyncio
async def test_generate_recommendations_full_pipeline():
    """Full pipeline runs all analyzers and returns combined results."""
    from core.engine.graph.recommendations import clear_cache, generate_recommendations

    clear_cache()

    # Mock all analyzers to return one rec each
    async def mock_fragile(_gid):
        return [{"id": "rec_1", "type": "risk", "title": "fragile", "related_files": []}]

    async def mock_quality(_gid):
        return [{"id": "rec_2", "type": "improvement", "title": "quality", "related_files": []}]

    async def mock_stale(_gid):
        return [{"id": "rec_3", "type": "suggestion", "title": "stale", "related_files": []}]

    async def mock_proposals(_gid):
        return [{"id": "rec_4", "type": "improvement", "title": "proposal", "related_files": []}]

    async def mock_llm(_gid, existing_recs=None):
        return [{"id": "rec_5", "type": "suggestion", "title": "llm", "related_files": []}]

    with (
        patch("core.engine.graph.recommendations._analyze_fragile_code", side_effect=mock_fragile),
        patch("core.engine.graph.recommendations._analyze_code_quality", side_effect=mock_quality),
        patch("core.engine.graph.recommendations._analyze_stale_decisions", side_effect=mock_stale),
        patch("core.engine.graph.recommendations._analyze_self_optimizer_proposals", side_effect=mock_proposals),
        patch("core.engine.graph.recommendations._analyze_with_llm", side_effect=mock_llm),
    ):
        recs = await generate_recommendations("default", limit=8)

    assert len(recs) == 5
    ids = {r["id"] for r in recs}
    assert ids == {"rec_1", "rec_2", "rec_3", "rec_4", "rec_5"}

    clear_cache()


@pytest.mark.asyncio
async def test_generate_recommendations_respects_limit():
    """generate_recommendations respects the limit parameter."""
    from core.engine.graph.recommendations import clear_cache, generate_recommendations

    clear_cache()

    async def mock_fragile(_gid):
        return [{"id": f"rec_{i}", "type": "risk", "title": f"rec {i}", "related_files": []} for i in range(10)]

    async def mock_empty(_gid):
        return []

    async def mock_llm(_gid, existing_recs=None):
        return []

    with (
        patch("core.engine.graph.recommendations._analyze_fragile_code", side_effect=mock_fragile),
        patch("core.engine.graph.recommendations._analyze_code_quality", side_effect=mock_empty),
        patch("core.engine.graph.recommendations._analyze_stale_decisions", side_effect=mock_empty),
        patch("core.engine.graph.recommendations._analyze_self_optimizer_proposals", side_effect=mock_empty),
        patch("core.engine.graph.recommendations._analyze_with_llm", side_effect=mock_llm),
    ):
        recs = await generate_recommendations("default", limit=3)

    assert len(recs) == 3

    clear_cache()


@pytest.mark.asyncio
async def test_generate_recommendations_handles_analyzer_failure():
    """If an analyzer raises, others still run."""
    from core.engine.graph.recommendations import clear_cache, generate_recommendations

    clear_cache()

    async def mock_failing(_gid):
        raise RuntimeError("DB error")

    async def mock_quality(_gid):
        return [{"id": "rec_ok", "type": "improvement", "title": "ok", "related_files": []}]

    async def mock_empty(_gid):
        return []

    async def mock_llm(_gid, existing_recs=None):
        return []

    with (
        patch("core.engine.graph.recommendations._analyze_fragile_code", side_effect=mock_failing),
        patch("core.engine.graph.recommendations._analyze_code_quality", side_effect=mock_quality),
        patch("core.engine.graph.recommendations._analyze_stale_decisions", side_effect=mock_empty),
        patch("core.engine.graph.recommendations._analyze_self_optimizer_proposals", side_effect=mock_empty),
        patch("core.engine.graph.recommendations._analyze_with_llm", side_effect=mock_llm),
    ):
        recs = await generate_recommendations("default", limit=8)

    assert len(recs) == 1
    assert recs[0]["id"] == "rec_ok"

    clear_cache()
