"""Unit tests for StallDetector."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.conductor.stall_detector import StallDetector


@pytest.fixture
def db_pool():
    pool = MagicMock()
    pool.connection = MagicMock()
    return pool


@pytest.fixture
def detector(db_pool):
    return StallDetector(db_pool)


# ── Cadence ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cadence_skips_first_five(detector):
    """maybe_check skips first 5 calls."""
    with patch.object(detector, "_run_check", new_callable=AsyncMock) as mock_run:
        for _ in range(5):
            result = await detector.maybe_check("product:test")
            assert result is False
        mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_cadence_fires_on_sixth(detector):
    """maybe_check fires on 6th call and returns True."""
    with patch.object(detector, "_run_check", new_callable=AsyncMock) as mock_run:
        for _ in range(5):
            await detector.maybe_check("product:test")
        result = await detector.maybe_check("product:test")
        assert result is True
        mock_run.assert_called_once_with("product:test")


@pytest.mark.asyncio
async def test_no_stuck_tracks_returns_cleanly(detector):
    """When no stuck tracks found, no events emitted."""
    with patch.object(detector, "_detect_stuck_tracks", new_callable=AsyncMock, return_value=[]):
        with patch("core.engine.conductor.stall_detector.bus") as mock_bus:
            await detector._run_check("product:test")
            mock_bus.emit.assert_not_called()


# ── Detection ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_stuck_tracks_uses_stall_gate(detector, db_pool):
    """Query uses per-state thresholds from STALL_THRESHOLDS for both detection and re-detection gate."""
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[])
    db_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    await detector._detect_stuck_tracks("product:test")

    call_args = mock_conn.query.call_args
    query_str = call_args[0][0]
    assert "stuck_since" in query_str
    assert "stall_last_detected_at" in query_str
    # All per-state thresholds are present in the query
    for state, hours in StallDetector.STALL_THRESHOLDS.items():
        assert state in query_str
        assert f"{hours}h" in query_str


# ── Increment ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stall_count_increments(detector, db_pool):
    """UPDATE sets stall_count and stall_last_detected_at; never touches stuck_since."""
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[])
    db_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    result = await detector._increment_stall_count("track:1", current_count=2)

    assert result == 3
    call_args = mock_conn.query.call_args
    query_str = call_args[0][0]
    assert "stall_count" in query_str
    assert "stall_last_detected_at" in query_str
    assert "stuck_since" not in query_str  # MUST NOT modify stuck_since


@pytest.mark.asyncio
async def test_stall_count_fallback_on_db_error(detector, db_pool):
    """If DB update fails, returns current_count + 1 from pre-fetched row."""
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(side_effect=Exception("DB down"))
    db_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    result = await detector._increment_stall_count("track:1", current_count=1)

    assert result == 2  # fallback: current_count + 1


# ── Reflection ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_builds_prompt_with_spec(detector):
    """Prompt includes capability name, state, hours_stuck, and spec description."""
    from datetime import datetime, timedelta, timezone

    track = {
        "id": "track:1",
        "capability_slug": "auth-service",
        "dimension": "security",
        "state": "executing",
        "stuck_since": datetime.now(timezone.utc) - timedelta(hours=26),
        "stall_count": 0,
    }
    spec = {"description": "Implement OAuth2 flow with PKCE"}
    captured_prompt = []

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(
        side_effect=lambda prompt, model=None: captured_prompt.append(prompt) or "reflection text"
    )

    with patch("core.engine.conductor.stall_detector.get_llm", return_value=mock_llm):
        result = await detector._reflect_on_stall(track, spec)

    assert result == "reflection text"
    prompt = captured_prompt[0]
    assert "auth-service" in prompt
    assert "security" in prompt
    assert "executing" in prompt
    assert "OAuth2" in prompt
    assert "26." in prompt or "26" in prompt  # hours_stuck


@pytest.mark.asyncio
async def test_reflect_no_spec(detector):
    """When spec is None, prompt says 'no spec available'."""
    track = {
        "id": "track:1",
        "capability_slug": "auth-service",
        "dimension": "security",
        "state": "executing",
        "stuck_since": None,
        "stall_count": 0,
    }
    captured_prompt = []
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=lambda prompt, model=None: captured_prompt.append(prompt) or "ok")

    with patch("core.engine.conductor.stall_detector.get_llm", return_value=mock_llm):
        await detector._reflect_on_stall(track, spec=None)

    assert "no spec available" in captured_prompt[0]


@pytest.mark.asyncio
async def test_reflect_failure_returns_empty_string(detector):
    """LLM error → returns '' so event is still emitted."""
    track = {
        "id": "track:1",
        "capability_slug": "x",
        "dimension": "testing",
        "state": "executing",
        "stuck_since": None,
        "stall_count": 0,
    }

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=Exception("LLM unavailable"))

    with patch("core.engine.conductor.stall_detector.get_llm", return_value=mock_llm):
        result = await detector._reflect_on_stall(track, spec=None)

    assert result == ""


@pytest.mark.asyncio
async def test_run_check_continues_after_per_track_failure(detector):
    """A failure on one track does not abort processing of subsequent tracks."""
    track_a = {"id": "track:1", "capability_slug": "auth"}
    track_b = {"id": "track:2", "capability_slug": "billing"}

    call_log = []

    async def fake_process(track, product_id):
        call_log.append(str(track["id"]))
        if track["id"] == "track:1":
            raise RuntimeError("simulated failure")

    with patch.object(detector, "_detect_stuck_tracks", new_callable=AsyncMock, return_value=[track_a, track_b]):
        with patch.object(detector, "_process_stuck_track", side_effect=fake_process):
            await detector._run_check("product:test")

    assert call_log == ["track:1", "track:2"]


# ── Capture ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_capture_called_with_correct_fields(detector):
    """CapturePipeline receives observation_type=pattern, confidence=0.7, discipline_hint=dimension."""
    track = {
        "id": "track:42",
        "capability_slug": "auth-service",
        "dimension": "security",
    }

    with patch("core.engine.conductor.stall_detector.capture_service") as mock_svc:
        mock_svc.emit = AsyncMock()
        await detector._capture_observation(track, "reflection text", "product:test")

    mock_svc.emit.assert_called_once()
    event = mock_svc.emit.call_args[0][0]
    assert event.metadata["observation_type"] == "pattern"
    assert event.metadata["confidence"] == 0.7
    assert event.metadata["discipline_hint"] == "security"
    assert "auth-service" in event.content
    assert "reflection text" in event.content


@pytest.mark.asyncio
async def test_capture_skipped_when_no_reflection(detector):
    """Empty reflection → capture_service.emit is not called."""
    track = {"id": "track:1", "capability_slug": "x", "dimension": "testing"}

    with patch("core.engine.conductor.stall_detector.capture_service") as mock_svc:
        await detector._capture_observation(track, "", "product:test")
        mock_svc.emit.assert_not_called()


# ── Event payload ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_event_payload_has_all_required_fields(detector):
    """Emitted conductor.stall_detected payload contains all required fields."""
    from datetime import datetime, timedelta, timezone

    track = {
        "id": "track:1",
        "capability_slug": "auth-service",
        "dimension": "security",
        "state": "executing",
        "stuck_since": datetime.now(timezone.utc) - timedelta(hours=30),
        "stall_count": 0,
        "active_spec_id": None,
    }

    emitted = []

    with patch.object(detector, "_detect_stuck_tracks", new_callable=AsyncMock, return_value=[track]):
        with patch.object(detector, "_increment_stall_count", new_callable=AsyncMock, return_value=1):
            with patch.object(detector, "_reflect_on_stall", new_callable=AsyncMock, return_value="reflection"):
                with patch.object(detector, "_capture_observation", new_callable=AsyncMock):
                    with patch("core.engine.conductor.stall_detector.bus") as mock_bus:
                        mock_bus.emit = AsyncMock(side_effect=lambda e, p: emitted.append((e, p)))
                        await detector._run_check("product:test")

    assert len(emitted) == 1
    event_type, payload = emitted[0]
    assert event_type == "conductor.stall_detected"
    required_fields = {
        "product_id",
        "track_id",
        "capability_slug",
        "dimension",
        "state",
        "hours_stuck",
        "stall_count",
        "reflection",
    }
    assert required_fields.issubset(payload.keys())
    assert payload["stall_count"] == 1
    assert payload["reflection"] == "reflection"
    assert payload["hours_stuck"] > 0


# ── Conductor wiring ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conductor_calls_maybe_check_on_heartbeat():
    """Conductor._on_event calls stall_detector.maybe_check on conductor.heartbeat."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.conductor.conductor import Conductor

    db_pool = MagicMock()
    db_pool.connection = MagicMock()

    conductor = Conductor(db_pool)
    conductor._stall_detector = MagicMock()
    conductor._stall_detector.maybe_check = AsyncMock(return_value=False)
    conductor._groomer = MagicMock()
    conductor._groomer.maybe_groom = AsyncMock(return_value=False)

    with patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value={"payload": {}}):
        with patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True):
            with patch.object(conductor._rule_engine, "evaluate", return_value=[]):
                await conductor._on_event("conductor.heartbeat", {"product_id": "product:test"})

    conductor._stall_detector.maybe_check.assert_called_once_with("product:test")


# ── Bootstrap rule ────────────────────────────────────────────────────────────


def test_stall_escalate_rule_in_default_rules():
    """DEFAULT_RULES contains stall_escalate on conductor.stall_detected with stall_count >= 2."""
    from core.engine.conductor.bootstrap import DEFAULT_RULES

    rule = next((r for r in DEFAULT_RULES if r["name"] == "stall_escalate"), None)
    assert rule is not None, "stall_escalate rule missing from DEFAULT_RULES"
    assert rule["trigger_event"] == "conductor.stall_detected"
    conditions = rule["conditions"]
    assert any(
        c["field"] == "payload.stall_count" and c["op"] in ("ge", ">=") and c["value"] >= 2 for c in conditions
    ), "stall_escalate must condition on payload.stall_count >= 2"
    assert any(a["type"] == "notify" for a in rule["actions"])


def test_stuck_track_escalation_removed():
    """The old stub stuck_track_escalation rule is no longer in DEFAULT_RULES."""
    from core.engine.conductor.bootstrap import DEFAULT_RULES

    names = [r["name"] for r in DEFAULT_RULES]
    assert "stuck_track_escalation" not in names, "stuck_track_escalation stub must be replaced by stall_escalate"


@pytest.mark.asyncio
async def test_vision_filter_bypassed_for_stall_detected():
    """_vision_filter.is_aligned is NOT called for conductor.stall_detected events."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.conductor.conductor import Conductor

    db_pool = MagicMock()
    conductor = Conductor(db_pool)
    conductor._org_id = "product:test"

    with patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value={"payload": {}}):
        with patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock) as mock_aligned:
            with patch.object(conductor._rule_engine, "evaluate", return_value=[]):
                await conductor._on_event(
                    "conductor.stall_detected",
                    {"product_id": "product:test", "track_id": "track:1", "stall_count": 1},
                )

    mock_aligned.assert_not_called()
