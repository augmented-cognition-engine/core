"""Tests for POST /canvas/sessions/{id}/fork — the canvas 'paths not taken' backend route.

Mirrors tests/test_classify_session_endpoint.py: ASGITransport bypasses auth middleware; the
ace_fork_reasoning tool + persistence are mocked (no real LLM/DB)."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.api.main import app


def _fake_session():
    return type("Sess", (), {"id": "canvas_session:abc", "title": "Marketplace?", "project_id": "product:platform"})()


@pytest.mark.asyncio
async def test_fork_reasoning_returns_camelcase_journey_fork_trace():
    fork_result = {
        "run_id": "reasoning_run:r1",
        "checkpoint_seq": 2,
        "recommendation": "fork",
        "best": {
            "label": "systems",
            "lens": "systems",
            "score": 0.66,
            "conclusion": "stage it",
            "capability_delta_score": 0.7,
        },
        "original": {"label": "original", "lens": "conclude", "score": 0.25, "conclusion": "ship it"},
        "forks": [
            {
                "label": "systems",
                "lens": "systems",
                "score": 0.66,
                "conclusion": "stage it",
                "capability_delta_score": 0.7,
            },
            {"label": "adversarial", "lens": "adversarial", "score": 0.41, "conclusion": "gate-first"},
        ],
        "created_at": "2026-06-24T00:00:00Z",
    }
    with (
        patch("core.engine.canvas.persistence.get_session", new=AsyncMock(return_value=_fake_session())),
        patch("core.engine.mcp.tools.ace_fork_reasoning", new=AsyncMock(return_value=fork_result)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/canvas/sessions/canvas_session:abc/fork",
                json={"run_id": "reasoning_run:r1", "checkpoint_seq": 2},
            )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # camelCase JourneyForkTrace shape the canvas consumes
    assert body["runId"] == "reasoning_run:r1"
    assert body["checkpointSeq"] == 2
    assert body["recommendation"] == "fork"
    assert body["best"]["lens"] == "systems"
    assert body["best"]["capabilityDeltaScore"] == 0.7  # snake_case → camelCase mapped
    assert body["original"]["label"] == "original"
    assert "capabilityDeltaScore" not in body["original"]  # omitted when the lens wasn't computed
    assert len(body["forks"]) == 2


@pytest.mark.asyncio
async def test_fork_reasoning_threads_lens_flag_and_session_product():
    captured: dict = {}

    async def _fake_fork(**kwargs):
        captured.update(kwargs)
        return {
            "run_id": "r",
            "checkpoint_seq": 1,
            "recommendation": "keep_original",
            "best": {"label": "original", "lens": "c", "score": 0.5, "conclusion": "x"},
            "original": {"label": "original", "lens": "c", "score": 0.5, "conclusion": "x"},
            "forks": [],
        }

    with (
        patch("core.engine.canvas.persistence.get_session", new=AsyncMock(return_value=_fake_session())),
        patch("core.engine.mcp.tools.ace_fork_reasoning", new=_fake_fork),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/canvas/sessions/canvas_session:abc/fork",
                json={"run_id": "r", "checkpoint_seq": 1, "with_capability_lens": True},
            )
    assert resp.status_code == 200
    assert captured["with_capability_lens"] is True
    assert captured["product_id"] == "product:platform"  # taken from the session, not the request


@pytest.mark.asyncio
async def test_fork_reasoning_surfaces_error_when_unreconstructable():
    with (
        patch("core.engine.canvas.persistence.get_session", new=AsyncMock(return_value=_fake_session())),
        patch(
            "core.engine.mcp.tools.ace_fork_reasoning",
            new=AsyncMock(return_value={"error": "no tail to fork", "run_id": "r", "checkpoint_seq": 9}),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/canvas/sessions/canvas_session:abc/fork",
                json={"run_id": "r", "checkpoint_seq": 9},
            )
    assert resp.status_code == 200
    assert "error" in resp.json()
