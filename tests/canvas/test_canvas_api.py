# tests/canvas/test_canvas_api.py
import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.api.main import app

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_create_session_endpoint(db_pool):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            "/canvas/sessions",
            json={"project_id": "product:p1", "title": "Postgres or Dynamo?"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Postgres or Dynamo?"
    assert body["id"].startswith("canvas_session:")


@pytest.mark.asyncio
async def test_request_framework_endpoint_emits_artifact(db_pool, fake_llm_trade_off):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        s = (
            await ac.post(
                "/canvas/sessions",
                json={"project_id": "product:p1", "title": "t"},
            )
        ).json()
        await ac.post(
            f"/canvas/sessions/{s['id']}/artifacts",
            json={
                "shape_kind": "sticky",
                "tldraw_shape_id": "shape:abc",
                "payload": {"text": "Need ACID for billing"},
                "x": 0,
                "y": 0,
                "author": "human",
            },
        )
        r = await ac.post(
            f"/canvas/sessions/{s['id']}/framework",
            json={
                "framework_kind": "trade_off_matrix",
                "prompt": "Postgres or Dynamo?",
                "cited_artifact_ids": [],
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert "tldraw_shape_id" in body
    assert body["tldraw_shape_id"].startswith("shape:fw_")


@pytest.mark.asyncio
async def test_decision_endpoint_lands_in_ledger(db_pool):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        s = (
            await ac.post(
                "/canvas/sessions",
                json={"project_id": "product:p1", "title": "t"},
            )
        ).json()
        r = await ac.post(
            f"/canvas/sessions/{s['id']}/decision",
            json={
                "title": "Use Postgres",
                "rationale": "ACID required",
                "cited_artifact_ids": [],
                "framework_kind": "trade_off_matrix",
            },
        )
    assert r.status_code == 200
    assert r.json()["decision_id"].startswith("decision:")


@pytest.mark.asyncio
async def test_delete_session_returns_204(db_pool):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        sess = (
            await ac.post(
                "/canvas/sessions",
                json={
                    "project_id": "product:test",
                    "title": "delete-me",
                },
            )
        ).json()
        sid = sess["id"]

        r = await ac.delete(f"/canvas/sessions/{sid}")
        assert r.status_code == 204

        r2 = await ac.get(f"/canvas/sessions/{sid}")
        assert r2.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_cascades_artifacts(db_pool):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        sess = (
            await ac.post(
                "/canvas/sessions",
                json={
                    "project_id": "product:test",
                    "title": "cascade-test",
                },
            )
        ).json()
        sid = sess["id"]

        await ac.post(
            f"/canvas/sessions/{sid}/artifacts",
            json={
                "shape_kind": "sticky",
                "tldraw_shape_id": "shape:s1",
                "payload": {"text": "hello"},
            },
        )

        await ac.delete(f"/canvas/sessions/{sid}")

        r = await ac.get(f"/canvas/sessions/{sid}")
        assert r.status_code == 404
