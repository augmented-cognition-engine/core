def test_score_shift_threshold():
    """Score shift >0.05 fires; ≤0.05 doesn't."""
    from core.engine.voice.detectors.recommendation_shift_detector import is_score_shift

    assert is_score_shift(prev=0.5, new=0.6) is True
    assert is_score_shift(prev=0.5, new=0.52) is False
    assert is_score_shift(prev=0.5, new=0.45) is False
    assert is_score_shift(prev=0.5, new=0.44) is True


import pytest


@pytest.mark.asyncio
async def test_swap_emits_resolved_for_old_top1(db_pool):
    """On a swap, both canvas.recommendation.shifted and canvas.recommendation.resolved are emitted.
    canvas.recommendation.resolved carries the OLD pillar/discipline (the displaced top-1).
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    emitted = []

    async def fake_emit(event_type, payload):
        emitted.append((event_type, payload))

    fake_bus = MagicMock()
    fake_bus.emit = fake_emit

    old_top = {
        "top_pillar": "experience",
        "top_discipline": "accessibility",
        "top_rank_score": 0.8,
    }
    new_top = [
        {
            "pillar": "operations",
            "discipline": "cicd",
            "rank": 0.9,
        }
    ]

    with (
        patch(
            "core.engine.voice.detectors.recommendation_shift_detector.bus",
            new=fake_bus,
        ),
        patch("core.engine.voice.detectors.recommendation_shift_detector.StrategicPrioritizer") as MockPrioritizer,
        patch(
            "core.engine.voice.detectors.recommendation_shift_detector.parse_rows",
            return_value=[old_top],
        ),
        patch("core.engine.voice.detectors.recommendation_shift_detector.pool") as mock_pool,
        patch(
            "core.engine.voice.detectors.recommendation_shift_detector.read_voice_thread",
            new=AsyncMock(return_value=None),
        ),
    ):
        mock_prioritizer_instance = AsyncMock()
        mock_prioritizer_instance.prioritize = AsyncMock(return_value=new_top)
        MockPrioritizer.return_value = mock_prioritizer_instance

        # Mock the pool context manager for both the SELECT and UPSERT queries
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

        from core.engine.voice.detectors.recommendation_shift_detector import _maybe_emit_shift

        await _maybe_emit_shift("product:platform")

    event_types = [e[0] for e in emitted]
    assert "canvas.recommendation.shifted" in event_types, f"shifted not in {event_types}"
    assert "canvas.recommendation.resolved" in event_types, f"resolved not in {event_types}"

    resolved_payload = next(p for t, p in emitted if t == "canvas.recommendation.resolved")
    assert resolved_payload["top_pillar"] == "experience"
    assert resolved_payload["top_discipline"] == "accessibility"


@pytest.mark.asyncio
async def test_swap_emits_reopened_when_resolved_thread_recurs(db_pool):
    """When new top-1's topic has a resolved voice_thread (changed within 14d), emit .reopened."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.voice.thread import VoiceThread

    emitted = []

    async def fake_emit(event_type, payload):
        emitted.append((event_type, payload))

    fake_bus = MagicMock()
    fake_bus.emit = fake_emit

    # Prev state: operations.cicd was top-1
    old_top = {
        "top_pillar": "operations",
        "top_discipline": "cicd",
        "top_rank_score": 0.9,
    }
    # New top-1: experience.ux is back
    new_top = [
        {
            "pillar": "experience",
            "discipline": "ux",
            "rank": 0.95,
        }
    ]

    now = datetime.now(timezone.utc)
    resolved_thread = VoiceThread(
        id="voice_thread:t1",
        topic="rec:experience.ux",
        product_id="product:platform",
        status="resolved",
        raised_at=now - timedelta(days=20),
        last_referenced_at=now - timedelta(days=5),
        last_state_changed_at=now - timedelta(days=5),  # resolved within 14d
        mention_count=3,
        current_payload_hash="h1",
        primary_event_type="canvas.recommendation.shifted",
    )

    with (
        patch(
            "core.engine.voice.detectors.recommendation_shift_detector.bus",
            new=fake_bus,
        ),
        patch("core.engine.voice.detectors.recommendation_shift_detector.StrategicPrioritizer") as MockPrioritizer,
        patch(
            "core.engine.voice.detectors.recommendation_shift_detector.parse_rows",
            return_value=[old_top],
        ),
        patch("core.engine.voice.detectors.recommendation_shift_detector.pool") as mock_pool,
        patch(
            "core.engine.voice.detectors.recommendation_shift_detector.read_voice_thread",
            new=AsyncMock(return_value=resolved_thread),
        ),
    ):
        mock_prioritizer_instance = AsyncMock()
        mock_prioritizer_instance.prioritize = AsyncMock(return_value=new_top)
        MockPrioritizer.return_value = mock_prioritizer_instance

        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

        from core.engine.voice.detectors.recommendation_shift_detector import _maybe_emit_shift

        await _maybe_emit_shift("product:platform")

    event_types = [e[0] for e in emitted]
    assert "canvas.recommendation.reopened" in event_types, f"reopened not in {event_types}"

    reopened_payload = next(p for t, p in emitted if t == "canvas.recommendation.reopened")
    assert reopened_payload["top_pillar"] == "experience"
    assert reopened_payload["top_discipline"] == "ux"
