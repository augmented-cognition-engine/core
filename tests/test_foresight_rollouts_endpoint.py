"""Tests for /foresight/{id}/rollouts endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.api.main import app


def _make_db_conn():
    """Return a mock async context manager that yields a fake DB handle.

    The foresight endpoints do ``async with _pool.connection() as db:``
    and then call ``db.query()``. parse_rows is patched separately per
    test; the db mock just needs to be a valid async context manager.
    """
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    return mock_conn


@pytest.mark.asyncio
async def test_get_rollouts_empty_when_no_cache():
    """No cached rollout → empty scenarios list."""
    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", return_value=[]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/rollouts")
    assert resp.status_code == 200
    assert resp.json() == {"scenarios": []}


@pytest.mark.asyncio
async def test_get_rollouts_returns_latest_cached():
    """Latest cached rollout is returned with branches + authored_by normalized."""
    cached = {
        "id": "rollout_cache:abc",
        "candidate": "Use JWT",
        "product": "product:test",
        "branches": [
            {"path": ["x"], "terminal_score": 0.8, "top_risk": "leaks", "state_override": {}},
            {
                "path": ["y"],
                "terminal_score": 0.7,
                "top_risk": "complexity",
                "state_override": {},
                "authored_by_archetype": "skeptic",
            },
        ],
        "best_path": ["x"],
        "created_at": "2026-05-14T00:00:00Z",
    }
    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", return_value=[cached]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/rollouts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["scenarios"]) == 1
    scenario = body["scenarios"][0]
    # Legacy branches without authored_by_archetype get normalized to ""
    assert scenario["branches"][0]["authored_by_archetype"] == ""
    assert scenario["branches"][1]["authored_by_archetype"] == "skeptic"


@pytest.mark.asyncio
async def test_generate_rollout_requires_candidate():
    """POST without candidate_decision → 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/foresight/product:test/rollouts/generate", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_generate_rollout_calls_planner():
    """POST with candidate triggers plan_rollout."""
    fake_result_dict = {
        "candidate": "x",
        "product_id": "product:test",
        "branches": [],
        "best_path": ["x"],
        "created_at": "2026-05-14",
    }

    class _Stub:
        candidate = "x"
        product_id = "product:test"
        branches: list = []
        best_path = ["x"]
        created_at = "2026-05-14"

    with patch("core.engine.foresight.planner.plan_rollout", new=AsyncMock(return_value=_Stub())):
        with patch("core.engine.api.foresight.asdict", return_value=fake_result_dict):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/foresight/product:test/rollouts/generate",
                    json={"candidate_decision": "Use JWT for auth"},
                )
    assert resp.status_code == 200
    assert resp.json()["candidate"] == "x"


@pytest.mark.asyncio
async def test_get_calibration_empty():
    """No outcomes → empty list."""
    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", return_value=[]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/calibration")
    assert resp.status_code == 200
    assert resp.json() == {"outcomes": []}


@pytest.mark.asyncio
async def test_get_calibration_returns_outcomes_with_decision_title():
    """Closed outcomes surface enriched with the underlying decision title.

    Without the title the card reads as a context-free archetype + score;
    the title is what makes "Skeptic's call on Adopt JWT played out at 98%"
    legible.
    """
    outcome_rows = [
        {
            "id": "prediction_outcome:po1",
            "prediction": "decision_prediction:p1",
            "decision": "decision:d1",
            "archetype": "pm",
            "discipline": "product",
            "calibration_score": 0.82,
            "predicted_deltas": {"capability:onboard": 0.3},
            "actual_deltas": {"capability:onboard": 0.27},
            "closed_at": "2026-05-14T00:00:00Z",
        }
    ]
    decision_rows = [{"id": "decision:d1", "title": "Adopt JWT for partner API auth"}]

    # parse_rows is called twice in get_calibration: once for outcomes,
    # then once for the decision-title batched lookup.
    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", side_effect=[outcome_rows, decision_rows]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["outcomes"]) == 1
    o = body["outcomes"][0]
    assert o["archetype"] == "pm"
    assert o["calibration_score"] == 0.82
    assert o["predicted_deltas"] == {"capability:onboard": 0.3}
    # The headline regression: decision_title is threaded through.
    assert o["decision_title"] == "Adopt JWT for partner API auth"


@pytest.mark.asyncio
async def test_get_calibration_filters_orphan_outcomes():
    """Outcomes whose decision no longer exists must not appear.

    Test cycles and manual cleanups leave orphan prediction_outcome rows;
    rendering them as context-free archetype+score cards is worse than
    omitting them. The filter is the user-facing fix.
    """
    outcome_rows = [
        {
            "id": "prediction_outcome:po_live",
            "decision": "decision:live",
            "archetype": "pm",
            "discipline": "product",
            "calibration_score": 0.82,
            "predicted_deltas": {},
            "actual_deltas": {},
            "closed_at": "2026-05-14T00:00:00Z",
        },
        {
            "id": "prediction_outcome:po_orphan",
            "decision": "decision:deleted",  # decision row no longer exists
            "archetype": "skeptic",
            "discipline": "security",
            "calibration_score": 0.5,
            "predicted_deltas": {},
            "actual_deltas": {},
            "closed_at": "2026-05-14T00:00:00Z",
        },
    ]
    # Only the live decision resolves to a title; the orphan's decision
    # is absent from the batched lookup result.
    decision_rows = [{"id": "decision:live", "title": "Adopt JWT for partner API auth"}]

    with patch("core.engine.api.foresight._pool.connection", return_value=_make_db_conn()):
        with patch("core.engine.api.foresight.parse_rows", side_effect=[outcome_rows, decision_rows]):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/foresight/product:test/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["outcomes"]) == 1
    assert body["outcomes"][0]["id"] == "prediction_outcome:po_live"
    # The orphan does NOT appear.
    assert all(o["id"] != "prediction_outcome:po_orphan" for o in body["outcomes"])
