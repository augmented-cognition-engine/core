# tests/canvas/test_e2e_real_data.py
import os

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.api.main import app

pytestmark = pytest.mark.e2e

REAL_LLM = os.getenv("ACE_TEST_REAL_LLM") == "1"


@pytest.mark.skipif(not REAL_LLM, reason="set ACE_TEST_REAL_LLM=1 to run")
@pytest.mark.asyncio
async def test_full_pipeline_real_llm(db_pool):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        s = (
            await ac.post(
                "/canvas/sessions",
                json={"project_id": "product:p_smoke", "title": "Postgres or Dynamo?"},
            )
        ).json()
        await ac.post(
            f"/canvas/sessions/{s['id']}/artifacts",
            json={
                "shape_kind": "sticky",
                "tldraw_shape_id": "shape:human1",
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
    payload = r.json()["payload"]
    assert len(payload["options"]) >= 2
    assert len(payload["axes"]) >= 2
    for opt in payload["options"]:
        assert all(a["name"] in opt["scores"] for a in payload["axes"])
    assert "recommendation" in payload and payload["recommendation"]
