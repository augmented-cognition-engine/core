"""Tests for GET /canvas/runs/{run_id}/trace — the Trace UI data layer (replay a reasoning run).

run_ledger is mocked (no real DB); ASGITransport bypasses auth middleware."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.api.main import app


def _events():
    return [
        {
            "seq": 0,
            "event_type": "run_started",
            "payload": {
                "thought": "Should we ship the marketplace?",
                "depth": 3,
                "discipline": "strategy",
                "meta_skills": ["strategic_intelligence"],
            },
        },
        {
            "seq": 1,
            "event_type": "phase",
            "payload": {"cognitive_function": "frame", "output": "framed it", "confidence": 0.8},
        },
        {
            "seq": 2,
            "event_type": "phase",
            "payload": {"cognitive_function": "conclude", "output": "ship it", "confidence": 0.7},
        },
        {
            "seq": 3,
            "event_type": "run_complete",
            "payload": {"conclusion": "Ship the curated marketplace.", "status": "complete"},
        },
    ]


@pytest.mark.asyncio
async def test_get_run_trace_replays_the_reasoning():
    with patch("core.engine.cognition.run_ledger.get_run_events", new=AsyncMock(return_value=_events())):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/canvas/runs/reasoning_run:abc/trace")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is True
    assert body["thought"] == "Should we ship the marketplace?"
    assert body["discipline"] == "strategy"
    assert len(body["phases"]) == 2  # frame, conclude (run_started/run_complete excluded)
    assert body["phases"][0]["function"] == "frame"
    assert body["phases"][0]["confidence"] == 0.8
    assert body["conclusion"] == "Ship the curated marketplace."
    assert body["status"] == "complete"


@pytest.mark.asyncio
async def test_get_run_trace_unavailable_when_no_events():
    with patch("core.engine.cognition.run_ledger.get_run_events", new=AsyncMock(return_value=[])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/canvas/runs/reasoning_run:missing/trace")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["phases"] == []


@pytest.mark.asyncio
async def test_get_run_trace_reads_engagement_phase_name_key():
    """Engagement-path phases use `phase_name`; multiphase uses `cognitive_function`. Both render."""
    events = _events()
    for e in events:
        if e["event_type"] == "phase":
            e["payload"] = {"phase_name": e["payload"]["cognitive_function"], "output": e["payload"]["output"]}
    with patch("core.engine.cognition.run_ledger.get_run_events", new=AsyncMock(return_value=events)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/canvas/runs/reasoning_run:abc/trace")
    assert [p["function"] for p in resp.json()["phases"]] == ["frame", "conclude"]
