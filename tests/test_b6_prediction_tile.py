# tests/test_b6_prediction_tile.py
"""B.6 — Prediction Tile: bridge fires attach_prediction; REST endpoint returns prediction."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_bridge_fires_attach_prediction_as_background_task(monkeypatch):
    """bridge_decision_to_ledger schedules attach_prediction for canvas decisions."""
    attached = []

    async def fake_create_decision(**kwargs):
        return {"id": "decision:b6_test"}

    async def fake_attach_prediction(**kwargs):
        attached.append(kwargs)

    monkeypatch.setattr("core.engine.canvas.ledger_bridge.create_decision", fake_create_decision)

    # Patch at the module level that the bridge imports from at runtime
    with patch("core.engine.foresight.forecaster.attach_prediction", new=AsyncMock(side_effect=fake_attach_prediction)):
        from unittest.mock import MagicMock

        from core.engine.canvas.ledger_bridge import bridge_decision_to_ledger

        # Patch pool so the UPDATE query doesn't hit a real DB
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn

        monkeypatch.setattr("core.engine.canvas.ledger_bridge.pool", mock_pool)

        decision_id = await bridge_decision_to_ledger(
            session_id="canvas_session:b6",
            product_id="product:p1",
            title="Use Postgres",
            rationale="ACID required",
            cited_artifact_ids=[],
        )
        assert decision_id == "decision:b6_test"

        # Give the background task time to run
        await asyncio.sleep(0.1)

    assert len(attached) == 1, "attach_prediction must be called exactly once"
    assert attached[0]["decision_id"] == "decision:b6_test"
    assert attached[0]["decision_content"] == "ACID required"
    assert attached[0]["product_id"] == "product:p1"


@pytest.mark.asyncio
async def test_bridge_attach_prediction_failure_does_not_propagate(monkeypatch):
    """Background attach_prediction failure must not raise or affect the returned decision_id."""

    async def fake_create_decision(**kwargs):
        return {"id": "decision:b6_safe"}

    async def exploding_attach(**kwargs):
        raise RuntimeError("LLM call failed")

    monkeypatch.setattr("core.engine.canvas.ledger_bridge.create_decision", fake_create_decision)

    with patch("core.engine.foresight.forecaster.attach_prediction", new=AsyncMock(side_effect=exploding_attach)):
        from unittest.mock import MagicMock

        from core.engine.canvas.ledger_bridge import bridge_decision_to_ledger

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        monkeypatch.setattr("core.engine.canvas.ledger_bridge.pool", mock_pool)

        decision_id = await bridge_decision_to_ledger(
            session_id="canvas_session:safe",
            product_id="product:p1",
            title="Safe decision",
            rationale="stays safe",
            cited_artifact_ids=[],
        )
        await asyncio.sleep(0.1)

    # The bridge must return normally even if attach_prediction explodes
    assert decision_id == "decision:b6_safe"


@pytest.mark.asyncio
async def test_get_decision_prediction_endpoint_returns_404_when_missing():
    """GET /canvas/decisions/{id}/prediction returns 404 when no prediction exists."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi.testclient import TestClient

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    # Empty result — parse_one returns None
    mock_conn.query = AsyncMock(return_value=[[]])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    # pool is imported locally inside the endpoint as `from engine.core.db import pool as _pool`
    with patch("core.engine.core.db.pool", mock_pool):
        from fastapi import FastAPI

        from core.engine.api.canvas import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        response = client.get("/decisions/decision:missing/prediction")

    assert response.status_code == 404
