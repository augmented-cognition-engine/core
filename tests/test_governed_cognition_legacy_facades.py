"""E1-E legacy mutation facade dispositions and authority boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import core.engine.api.self_optimizer as optimizer_api
import core.engine.api.skills as skills_api
from core.engine.cognition.contracts import CognitionType
from core.engine.core.auth import get_current_user


@pytest.fixture
async def client():
    app = FastAPI()
    app.include_router(skills_api.router)
    app.include_router(optimizer_api.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user:reviewer",
        "product": "product:test",
        "authorities": ["cognition-review"],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, app


def _skill_request() -> dict:
    return {
        "slug": "taught-skill",
        "name": "Taught Skill",
        "description": "A review-required recipe.",
        "domain_path": "testing",
        "jobs": [
            {
                "name": "inspect",
                "archetype": "analyst",
                "mode": "procedural",
                "frameworks": ["first-principles"],
            }
        ],
    }


async def test_skill_create_returns_proposal_disposition_not_mutable_row(client, monkeypatch) -> None:
    http, _ = client

    async def no_existing(_slug, _product):
        return None, None

    proposal = SimpleNamespace(proposal_id="cognition_proposal:test")
    monkeypatch.setattr(skills_api, "_canonical", no_existing)
    persist = AsyncMock(return_value=proposal)
    monkeypatch.setattr(skills_api, "_persist_proposal", persist)
    response = await http.post("/skills?product=product:test", json=_skill_request())
    assert response.status_code == 202
    assert response.headers["deprecation"] == "true"
    payload = response.json()
    assert payload["status"] == "review_required"
    assert payload["compatibility_disposition"] == "canonical_proposal_created"
    assert payload["review_endpoint"].endswith("/review")
    persist.assert_awaited_once()


async def test_skill_delete_never_deletes_and_points_to_human_lifecycle(client, monkeypatch) -> None:
    http, _ = client
    head = SimpleNamespace(head_id="cognition_head:test", generation=3)
    revision = SimpleNamespace(revision_id="cognition_revision:test")

    async def existing(_slug, _product):
        return head, revision

    monkeypatch.setattr(skills_api, "_canonical", existing)
    response = await http.delete("/skills/taught-skill")
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "review_required"
    assert payload["history_preserved"] is True
    assert payload["expected_head_generation"] == 3
    assert payload["lifecycle_endpoint"].endswith("/lifecycle")


async def test_skill_foreign_product_query_fails_before_mutation(client) -> None:
    http, _ = client
    response = await http.post("/skills?product=product:foreign", json=_skill_request())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "foreign_product_scope"


async def test_self_optimizer_requires_explicit_review_authority(client) -> None:
    http, app = client
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user:ordinary",
        "product": "product:test",
        "authorities": [],
    }
    response = await http.post("/self-optimizer/proposals/self_optimizer_proposal:test/approve?product=product:test")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "human_authority_required"


def test_legacy_skill_proposal_converts_to_nonselectable_canonical_proposal() -> None:
    actor = optimizer_api.ReviewActorV1(
        actor_id="user:reviewer",
        actor_class=optimizer_api.ActorClass.HUMAN,
        authorities=("cognition-review",),
    )
    proposal = optimizer_api._canonical_proposal(
        {
            "id": "self_optimizer_proposal:test",
            "product": "product:test",
            "type": "skill",
            "name": "Taught Skill",
            "description": "Translated.",
            "draft": {
                "jobs": [
                    {
                        "name": "inspect",
                        "archetype": "analyst",
                        "mode": "procedural",
                        "frameworks": ["first-principles"],
                    }
                ]
            },
        },
        "product:test",
        actor,
    )
    assert proposal.target_identity.cognition_type is CognitionType.RECIPE
    assert proposal.scope.product_id == "product:test"
    assert proposal.created_by.authorities == ()
    assert proposal.proposal_id
