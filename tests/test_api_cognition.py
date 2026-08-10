"""Governed-cognition API boundary tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import core.engine.api.cognition as cognition_api
from core.engine.core.auth import get_current_user


class _TaskDB:
    def __init__(self, task):
        self.task = task
        self.calls = []

    async def query(self, query, params):
        self.calls.append((query, params))
        return self.task


class _Pool:
    def __init__(self, db):
        self.db = db

    @asynccontextmanager
    async def connection(self):
        yield self.db


@pytest.fixture
async def client():
    app = FastAPI()
    app.include_router(cognition_api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value, app


def _request() -> dict:
    return {
        "task_id": "task:source",
        "stable_key": "taught_recipe",
        "name": "Taught Recipe",
        "description": "A recipe taught from an accepted task.",
        "intent": "Reuse the accepted framing sequence.",
        "base_recipe_slug": "coding_intelligence",
    }


async def test_teach_requires_authentication(client) -> None:
    http, _ = client
    response = await http.post("/cognition/proposals/from-task", json=_request())
    assert response.status_code == 401


async def test_teach_from_task_creates_non_selectable_sourced_proposal(client, monkeypatch) -> None:
    http, app = client
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user:author",
        "product": "product:alpha",
    }
    db = _TaskDB(
        {
            "id": "task:source",
            "product": "product:alpha",
            "description": "Frame and verify a migration.",
            "output": "Accepted migration plan.",
            "decision_receipt": {
                "id": "decision:source",
                "reviewed_at": datetime(2026, 8, 9, 12, 30, tzinfo=UTC),
            },
        }
    )
    monkeypatch.setattr(cognition_api, "pool", _Pool(db))

    class FakeService:
        def __init__(self, store):
            pass

        async def propose(self, proposal):
            return proposal

    monkeypatch.setattr(cognition_api, "DurableCognitionGovernanceService", FakeService)
    response = await http.post("/cognition/proposals/from-task", json=_request())
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["selectable"] is False
    proposal = payload["proposal"]
    assert proposal["target_identity"]["owner"]["namespace"] == "product:alpha"
    assert proposal["draft_body"]["slug"] == "taught_recipe"
    assert proposal["sources"][0]["source_id"] == "task:source"
    assert proposal["sources"][0]["content_hash"]
    assert payload["semantic_diff"]["changes"]


async def test_teach_does_not_read_foreign_task(client, monkeypatch) -> None:
    http, app = client
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user:author",
        "product": "product:alpha",
    }
    monkeypatch.setattr(cognition_api, "pool", _Pool(_TaskDB([])))
    response = await http.post("/cognition/proposals/from-task", json=_request())
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "task_not_found"


async def test_review_requires_explicit_cognition_review_authority(client, monkeypatch) -> None:
    http, app = client
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user:author",
        "product": "product:alpha",
        "authorities": [],
    }

    class FakeService:
        def __init__(self, store):
            pass

        async def review(self, **kwargs):
            assert kwargs["actor"].authorities == ()
            raise PermissionError("human_authority_required")

    monkeypatch.setattr(cognition_api, "DurableCognitionGovernanceService", FakeService)
    response = await http.post(
        "/cognition/proposals/cognition_proposal:abc/review",
        json={
            "review_request_id": "review:request",
            "disposition": "approve",
            "rationale": "Reviewed.",
            "expected_head_generation": 0,
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "human_authority_required"
