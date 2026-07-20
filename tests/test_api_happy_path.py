# tests/test_api_happy_path.py
"""Happy-path API tests — one per priority route. Valid JWT, mocked DB, assert status + shape."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.engine.api.main import app
from core.engine.core.auth import get_current_user


@pytest.fixture
def client():
    from core.engine.api import tasks

    mock_user = {"sub": "user:test", "product": "product:test"}
    tasks._accepting_tasks = True
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- POST /tasks ---


def test_create_task_returns_202(client):
    task_state = {"id": "task:1", "status": "pending", "product": "product:test"}

    async def update_receipt(_task_id, fields):
        task_state.update(fields)
        return task_state

    async def get_receipt(_task_id):
        return task_state

    with (
        patch("core.engine.orchestration.orchestrate", new_callable=AsyncMock) as mock_orch,
        patch(
            "core.engine.api.tasks._create_or_get_receipt",
            new=AsyncMock(return_value=(task_state, True)),
        ),
        patch("core.engine.api.tasks._update_receipt", new=update_receipt),
        patch("core.engine.api.tasks._get_task_record", new=get_receipt),
    ):
        from core.engine.orchestration.executor import OrchestrationResult

        mock_orch.return_value = OrchestrationResult(
            task_id="task:1",
            output="done",
            classification={"domain_path": "tech", "archetype": "executor", "mode": "reactive"},
            snapshot={"total_count": 2, "token_usage": {"total_tokens": 42}},
            events=[
                MagicMock(event_type="plan_created", pattern="pipeline", agent_count=2, steps=["analyst", "critic"])
            ],
            status="completed",
        )
        resp = client.post(
            "/tasks",
            json={"description": "test", "workspace_id": "workspace:test", "wait_seconds": 1},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["id"] == "task:1"
    assert data["status"] == "completed"
    assert data["reasoning_trace"]["dispatch"] == {
        "pattern": "pipeline",
        "agent_count": 2,
        "stages": ["analyst", "critic"],
    }
    assert data["reasoning_trace"]["intelligence"]["total_count"] == 2
    assert data["reasoning_trace"]["provenance"]["token_usage"]["total_tokens"] == 42


# --- GET /graph ---


def test_get_graph_returns_nodes_and_edges(client):
    with patch("core.engine.api.graph.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [[{"id": "sub:1", "slug": "engineering"}]],
                [[{"id": "syn:1", "in": "sub:1", "out": "sub:2", "strength": 0.5}]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = client.get("/graph", params={"product": "product:test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data


# --- GET /intel/context ---


def test_get_intel_context_returns_partitioned(client):
    with (
        patch("core.engine.api.intel.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.api.intel.calculate_maturation", new_callable=AsyncMock) as mock_mat,
    ):
        mock_load.return_value = {
            "insights": [
                {"content": "fact", "confidence": 0.9, "insight_type": "pattern"},
            ],
            "total_count": 1,
        }
        mock_mat.return_value = {"phase": 2, "phase_name": "forming"}
        resp = client.get("/intel/context", params={"q": "tech", "product": "product:test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain_path"] == "tech"
    assert data["maturation_level"] == "forming"
    assert data["total_count"] == 1


# --- GET /intel/search ---


def test_search_intel_returns_results(client):
    with patch("core.engine.api.intel.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"content": "test", "confidence": 0.8}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = client.get("/intel/search", params={"q": "test", "product": "product:test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "test"
    assert "results" in data
    assert "count" in data


# --- GET /briefings ---


def test_list_briefings(client):
    with patch("core.engine.api.briefings.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "b:1", "period": "weekly"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = client.get("/briefings", params={"product": "product:test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "briefings" in data


# --- GET /briefings/latest ---


def test_get_latest_briefing(client):
    with patch("core.engine.api.briefings.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "b:1",
                        "content": "briefing text",
                        "period": "weekly",
                        "metrics": {},
                        "created_at": "2026-03-22T00:00:00Z",
                    }
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = client.get("/briefings/latest", params={"product": "product:test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data


# --- GET /ideas ---


def test_list_ideas(client):
    with patch("core.engine.api.ideas.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "idea:1", "status": "captured"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = client.get("/ideas", params={"product": "product:test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "ideas" in data


# --- POST /observations ---


def test_create_observation_returns_201(client):
    with patch("core.engine.api.capture.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "obs:1"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = client.post(
            "/observations",
            json={
                "observation_type": "correction",
                "content": "Use rem not px",
                "domain_path": "design.tokens",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "captured"


# --- POST /sessions ---


def test_import_session_returns_202(client):
    with patch("core.engine.api.capture.CapturePipeline") as mock_pipe:
        mock_instance = AsyncMock()
        mock_pipe.return_value = mock_instance
        mock_instance.run = AsyncMock()
        resp = client.post("/sessions", json={"transcript": "test session data"})
    assert resp.status_code == 202
    data = resp.json()
    assert "session_id" in data


# --- GET /roi ---


def test_get_roi(client):
    with patch("core.engine.api.roi.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = client.get("/roi", params={"product": "product:test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "this_week" in data
    assert "hours_saved" in data["this_week"]
