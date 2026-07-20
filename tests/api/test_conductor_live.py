"""API tests for GET /conductor/live/{product_id} — Cohort B #17.

Two test layers:

- Integration (e2e): empty product, stale heartbeat, auth — TestClient
  against the real ASGI app and real SurrealDB pool. Mirrors
  tests/api/test_journey_api.py and tests/api/test_loop_api.py.

- Handler-unit (mocked DB): seeded full-shape scenario. Uses AsyncMock +
  patch to stub the pool layer, mirroring tests/test_conductor_api.py.
  Reason: the ace_test namespace's `capability_lifecycle_track.state`
  field carries an ASSERT that rejects values outside the allowed set,
  including 'gate_pending' (which is an event-topic name, not a persisted
  state per the v052 schema). We cannot CREATE a row with state =
  'gate_pending' in the test DB, and modifying shared schema is not in
  scope for this task. Mocking the DB for that single scenario keeps the
  contract assertions on the handler honest without schema drift.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Empty product
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_conductor_live_empty_product_returns_empty_shape():
    """Empty product → 200 with empty arrays/dicts and a 'no heartbeat' phrase."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "cl1@example.com",
        "product": "product:test_clive_empty",
    }

    try:
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_clive_empty")
            await db.query("DELETE capability_lifecycle_track WHERE product = product:test_clive_empty")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/conductor/live/product:test_clive_empty")
            assert r.status_code == 200, r.text
            data = r.json()

            assert data["track_states"] == {}
            assert data["stuck_count"] == 0
            assert data["recent_firings"] == []
            assert data["pending_gates"] == []
            assert data["product_id"] == "product:test_clive_empty"
            assert data["generated_at"]

            hb = data["heartbeat"]
            assert hb["observed_at"] is None
            assert hb["is_fresh"] is False
            assert hb["age_seconds"] is None
            # Phrase must be a non-empty partner-voice string.
            assert isinstance(hb["phrase"], str)
            assert hb["phrase"]
            assert hb["phrase"].startswith("we ")
            assert len(hb["phrase"]) >= 75
            assert "[unknown topic:" not in hb["phrase"]
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_clive_empty")
            await db.query("DELETE capability_lifecycle_track WHERE product = product:test_clive_empty")


# ---------------------------------------------------------------------------
# Seeded product — heartbeat + firings + pending gate + state distribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conductor_live_seeded_product_renders_full_shape():
    """Handler-unit test: heartbeat ~10s ago + 3 firings + 1 pending gate +
    state distribution → fully-populated response, partner-voice clean
    across all phrases.

    Mocks the pool layer because the ace_test namespace's
    capability_lifecycle_track.state ASSERT rejects 'gate_pending' (it's
    an event-topic name in v052, not a persisted state). Mirrors the
    AsyncMock + patch pattern from tests/test_conductor_api.py.
    """
    from core.engine.voice.audit import audit_partner_voice

    now = datetime.now(timezone.utc)

    # Five queries fire in order inside get_live_state. parse_rows is
    # patched with side_effect to return one row-list per call.
    state_rows = [
        {"state": "gate_pending", "cnt": 1},
        {"state": "met", "cnt": 1},
    ]
    stuck_rows = [{"cnt": 0}]
    heartbeat_rows = [
        {
            "id": "journey_event:hb1",
            "occurred_at": now - timedelta(seconds=10),
            "topic": "conductor.heartbeat",
        }
    ]
    firing_rows = [
        # DESC order — newest first.
        {
            "id": "journey_event:f3",
            "occurred_at": now - timedelta(minutes=3),
            "topic": "quality.score_changed",
            "payload": {"dimension": "security"},
        },
        {
            "id": "journey_event:f2",
            "occurred_at": now - timedelta(minutes=6),
            "topic": "conductor.track_changed",
            "payload": {"from_state": "spec_pending", "to_state": "executing"},
        },
        {
            "id": "journey_event:f1",
            "occurred_at": now - timedelta(minutes=9),
            "topic": "conductor.gate_cleared",
            "payload": {"track_id": "capability_lifecycle_track:abc"},
        },
    ]
    gate_rows = [
        {
            "id": "capability_lifecycle_track:test_clive_seed_pg",
            "name": "sample track",
            "state": "gate_pending",
            "stuck_since": now - timedelta(minutes=30),
        }
    ]

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    cm.__aexit__ = AsyncMock()

    with (
        patch("core.engine.api.conductor.pool") as mock_pool,
        patch(
            "core.engine.api.conductor.parse_rows",
            side_effect=[state_rows, stuck_rows, heartbeat_rows, firing_rows, gate_rows],
        ),
    ):
        mock_pool.connection.return_value = cm

        from core.engine.api.conductor import get_live_state

        data = await get_live_state(
            "product:test_clive_seed",
            user={"product": "product:test_clive_seed"},
        )

    # ------------- track_states -------------
    states = data["track_states"]
    assert states.get("gate_pending") == 1, states
    assert states.get("met") == 1, states
    assert data["stuck_count"] == 0

    # ------------- heartbeat -------------
    hb = data["heartbeat"]
    assert hb["is_fresh"] is True, hb
    assert hb["age_seconds"] is not None
    assert hb["age_seconds"] <= 30, hb
    assert hb["observed_at"], hb
    assert isinstance(hb["observed_at"], str)
    assert hb["phrase"].startswith("we ")
    assert len(hb["phrase"]) >= 75
    assert "[unknown topic:" not in hb["phrase"]

    # ------------- recent_firings -------------
    firings = data["recent_firings"]
    assert len(firings) == 3, firings
    # DESC order preserved through the handler.
    assert firings[0]["topic"] == "quality.score_changed"
    assert firings[1]["topic"] == "conductor.track_changed"
    assert firings[2]["topic"] == "conductor.gate_cleared"
    for f in firings:
        assert f["id"]
        assert f["occurred_at"]
        assert isinstance(f["occurred_at"], str)
        phrase = f["phrase"]
        assert phrase.startswith("we "), phrase
        assert len(phrase) >= 75, phrase
        assert "[unknown topic:" not in phrase
        result = audit_partner_voice(phrase)
        assert result.violations == [], f"voice violations in {phrase!r}: {result.violations}"

    # ------------- pending_gates -------------
    gates = data["pending_gates"]
    assert len(gates) == 1, gates
    g = gates[0]
    assert g["track_id"] == "capability_lifecycle_track:test_clive_seed_pg"
    assert g["name"] == "sample track"
    assert g["state"] == "gate_pending"
    assert g["stuck_since"]
    assert isinstance(g["stuck_since"], str)
    phrase = g["phrase"]
    assert phrase.startswith("we "), phrase
    assert len(phrase) >= 75, phrase
    assert "[unknown topic:" not in phrase
    result = audit_partner_voice(phrase)
    assert result.violations == [], f"voice violations in {phrase!r}: {result.violations}"

    assert data["generated_at"]
    assert data["product_id"] == "product:test_clive_seed"


# ---------------------------------------------------------------------------
# Stale heartbeat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_conductor_live_stale_heartbeat_renders_minutes_phrase():
    """Heartbeat 5 minutes ago → is_fresh=False, phrase mentions minutes."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {
        "email": "cl3@example.com",
        "product": "product:test_clive_stale",
    }

    try:
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_clive_stale")
            await db.query(
                "CREATE journey_event SET topic = 'conductor.heartbeat', "
                "product = product:test_clive_stale, payload = {}, "
                "occurred_at = time::now() - 5m"
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/conductor/live/product:test_clive_stale")
            assert r.status_code == 200, r.text
            data = r.json()
            hb = data["heartbeat"]
            assert hb["is_fresh"] is False, hb
            assert hb["age_seconds"] is not None
            assert hb["age_seconds"] >= 60
            assert "minute" in hb["phrase"], hb["phrase"]
            assert hb["phrase"].startswith("we ")
            assert len(hb["phrase"]) >= 75
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_clive_stale")


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_conductor_live_requires_auth():
    """Missing token → 401."""
    from core.engine.api.main import app
    from core.engine.core.db import pool

    await pool.init()
    # No dependency override → real auth path runs and rejects missing bearer.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/conductor/live/product:test_clive_auth")
        assert r.status_code == 401, r.text
