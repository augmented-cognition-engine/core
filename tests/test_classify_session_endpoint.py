"""Tests for POST /canvas/sessions/{id}/classify endpoint.

Auth pattern mirrors tests/canvas/test_canvas_api.py — ASGITransport bypasses
middleware in test mode; no explicit token plumbing needed.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.api.main import app


@pytest.mark.asyncio
async def test_classify_session_returns_roster():
    fake_classification = {
        "discipline": "ux",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
        "specialties": ["interface-design"],
        "engagement": {"perspectives": ["analyst", "advisor"]},
    }
    with (
        patch("core.engine.canvas.persistence.create_session", new=AsyncMock()) as create,
        patch("core.engine.canvas.persistence.get_session", new=AsyncMock()) as get_sess,
        patch("core.engine.orchestrator.classifier.classify_task", new=AsyncMock(return_value=fake_classification)),
        patch(
            "core.engine.cognition.classifier.FrameworkClassifier.resolve_instrument",
            new=AsyncMock(return_value="constraint-theory"),
        ),
    ):
        create.return_value = type(
            "Sess",
            (),
            {
                "id": "canvas_session:abc",
                "title": "JWT vs cookies",
                "project_id": "product:platform",
                "model_dump": lambda self: {
                    "id": "canvas_session:abc",
                    "title": "JWT vs cookies",
                    "project_id": "product:platform",
                },
            },
        )()
        get_sess.return_value = type(
            "Sess", (), {"id": "canvas_session:abc", "title": "JWT vs cookies", "project_id": "product:platform"}
        )()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/canvas/sessions/canvas_session:abc/classify")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["discipline"] == "ux"
    assert isinstance(body["archetypes"], list)
    assert 1 <= len(body["archetypes"]) <= 5
    for a in body["archetypes"]:
        assert "archetype" in a and "color_hint" in a and "idle_zone_hint" in a
    assert body["specialties"] == ["interface-design"]


@pytest.mark.asyncio
async def test_classify_session_is_idempotent():
    """Two calls on the same session id return matching archetype lists."""
    fake_classification = {
        "discipline": "architecture",
        "archetype": "executor",
        "mode": "deliberative",
        "complexity": "moderate",
        "specialties": [],
        "engagement": {"perspectives": ["analyst", "advisor"]},
    }
    with (
        patch("core.engine.canvas.persistence.get_session", new=AsyncMock()) as get_sess,
        patch("core.engine.orchestrator.classifier.classify_task", new=AsyncMock(return_value=fake_classification)),
        patch(
            "core.engine.cognition.classifier.FrameworkClassifier.resolve_instrument",
            new=AsyncMock(return_value="first-principles"),
        ),
    ):
        get_sess.return_value = type(
            "Sess", (), {"id": "canvas_session:abc", "title": "Same input", "project_id": "product:platform"}
        )()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r1 = await ac.post("/canvas/sessions/canvas_session:abc/classify")
            r2 = await ac.post("/canvas/sessions/canvas_session:abc/classify")
    assert r1.status_code == 200 and r2.status_code == 200
    arch1 = [a["archetype"] for a in r1.json()["archetypes"]]
    arch2 = [a["archetype"] for a in r2.json()["archetypes"]]
    assert arch1 == arch2
