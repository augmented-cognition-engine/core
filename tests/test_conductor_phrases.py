"""Unit tests for engine/cognition/conductor_phrases.py — pure helpers
that render partner-voice phrases for the /conductor live page.

Mirrors the test style of tests/test_loop_iterations.py and
tests/test_active_discipline.py — synthetic dicts, no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.engine.cognition.conductor_phrases import (
    HEARTBEAT_FRESH_SECONDS,
    compose_firing_phrase,
    compose_pending_gate_phrase,
    heartbeat_freshness,
)
from core.engine.voice.audit import audit_partner_voice

# ---------------------------------------------------------------------------
# heartbeat_freshness
# ---------------------------------------------------------------------------


def _fixed_now() -> datetime:
    """Deterministic 'now' fixture so tests don't drift on real-time clock."""
    return datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)


class TestHeartbeatFreshness:
    def test_none_returns_haven_t_seen_branch(self):
        result = heartbeat_freshness(None, now=_fixed_now())
        assert result["is_fresh"] is False
        assert result["age_seconds"] is None
        phrase = result["phrase"]
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert "haven't seen" in phrase
        assert audit_partner_voice(phrase).violations == []

    def test_fresh_branch_30s_ago(self):
        now = _fixed_now()
        beat = now - timedelta(seconds=30)
        result = heartbeat_freshness(beat, now=now)
        assert result["is_fresh"] is True
        assert result["age_seconds"] == 30
        phrase = result["phrase"]
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert audit_partner_voice(phrase).violations == []

    def test_stale_branch_5_min_ago(self):
        now = _fixed_now()
        beat = now - timedelta(minutes=5)
        result = heartbeat_freshness(beat, now=now)
        assert result["is_fresh"] is False
        assert result["age_seconds"] == 300
        phrase = result["phrase"]
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        # Minute count rendered honestly in stale phrase.
        assert "5 minute" in phrase or "5 minutes" in phrase
        assert audit_partner_voice(phrase).violations == []

    def test_accepts_datetime_input(self):
        # Regression test: SurrealDB hydrates datetime cols as datetime objects
        # but seeded test data lands as strings. Both must work.
        now = _fixed_now()
        beat_dt = now - timedelta(seconds=15)
        result = heartbeat_freshness(beat_dt, now=now)
        assert result["is_fresh"] is True
        assert result["age_seconds"] == 15

    def test_accepts_string_input(self):
        # Regression test for the datetime-vs-string bug from loop-timeline.
        now = _fixed_now()
        beat_dt = now - timedelta(seconds=20)
        beat_str = beat_dt.isoformat()
        result = heartbeat_freshness(beat_str, now=now)
        assert result["is_fresh"] is True
        assert result["age_seconds"] == 20

    def test_accepts_string_with_trailing_z(self):
        # Regression test for trailing 'Z' tolerance.
        now = _fixed_now()
        beat_dt = now - timedelta(seconds=10)
        beat_str = beat_dt.isoformat().replace("+00:00", "Z")
        result = heartbeat_freshness(beat_str, now=now)
        assert result["is_fresh"] is True
        assert result["age_seconds"] == 10

    def test_boundary_at_threshold(self):
        # Age exactly equal to HEARTBEAT_FRESH_SECONDS — counts as fresh.
        now = _fixed_now()
        beat = now - timedelta(seconds=HEARTBEAT_FRESH_SECONDS)
        result = heartbeat_freshness(beat, now=now)
        assert result["is_fresh"] is True

    def test_just_past_threshold_is_stale(self):
        now = _fixed_now()
        beat = now - timedelta(seconds=HEARTBEAT_FRESH_SECONDS + 1)
        result = heartbeat_freshness(beat, now=now)
        assert result["is_fresh"] is False


# ---------------------------------------------------------------------------
# compose_firing_phrase — known topics
# ---------------------------------------------------------------------------


KNOWN_TOPICS = [
    "conductor.gate_cleared",
    "conductor.gate_pending",
    "conductor.track_changed",
    "conductor.stall_detected",
    "conductor.action_failed",
    "quality.score_changed",
    "innovation.candidates_ready",
]


class TestComposeFiringPhraseKnownTopics:
    @pytest.mark.parametrize("topic", KNOWN_TOPICS)
    def test_each_known_topic_partner_voice_clean(self, topic):
        event = {"id": f"journey_event:{topic}", "topic": topic, "payload": {}}
        phrase = compose_firing_phrase(event)
        assert phrase.startswith("we "), f"phrase must open with 'we' for {topic}: {phrase!r}"
        assert len(phrase) >= 75, f"phrase ≥75 chars required for {topic}: {len(phrase)} — {phrase!r}"
        assert "[unknown topic:" not in phrase
        result = audit_partner_voice(phrase)
        assert result.violations == [], f"voice audit failed for {topic}: {result.violations}"

    def test_track_changed_with_payload(self):
        event = {
            "id": "journey_event:abc",
            "topic": "conductor.track_changed",
            "payload": {"from_state": "idle", "to_state": "in_progress"},
        }
        phrase = compose_firing_phrase(event)
        assert "idle" in phrase
        assert "in_progress" in phrase
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert audit_partner_voice(phrase).violations == []

    def test_track_changed_without_payload(self):
        # Worst-case input: payload missing; substitution must still hit ≥75.
        event = {"id": "journey_event:abc", "topic": "conductor.track_changed"}
        phrase = compose_firing_phrase(event)
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert "[unknown topic:" not in phrase
        assert audit_partner_voice(phrase).violations == []

    def test_track_changed_empty_payload_dict(self):
        event = {
            "id": "journey_event:abc",
            "topic": "conductor.track_changed",
            "payload": {},
        }
        phrase = compose_firing_phrase(event)
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert audit_partner_voice(phrase).violations == []


# ---------------------------------------------------------------------------
# compose_firing_phrase — unknown topic fallback
# ---------------------------------------------------------------------------


class TestComposeFiringPhraseUnknownTopic:
    def test_unknown_topic_defensive_fallback(self):
        event = {"id": "journey_event:xyz", "topic": "synthetic.never.seen"}
        phrase = compose_firing_phrase(event)
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert "[unknown topic:" not in phrase
        assert audit_partner_voice(phrase).violations == []
        # The topic name should appear in the phrase for honesty.
        assert "synthetic.never.seen" in phrase

    def test_unknown_topic_short_name_still_meets_floor(self):
        # Worst-case: 3-char topic must still let phrase reach ≥75 chars.
        event = {"id": "journey_event:short", "topic": "abc"}
        phrase = compose_firing_phrase(event)
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert "[unknown topic:" not in phrase
        assert audit_partner_voice(phrase).violations == []


# ---------------------------------------------------------------------------
# compose_pending_gate_phrase
# ---------------------------------------------------------------------------


class TestComposePendingGatePhrase:
    def test_full_track_dict(self):
        now = _fixed_now()
        track = {
            "track_id": "capability_lifecycle_track:abc",
            "name": "auth-refactor",
            "stuck_since": (now - timedelta(minutes=12)).isoformat(),
        }
        phrase = compose_pending_gate_phrase(track)
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert "auth-refactor" in phrase
        assert audit_partner_voice(phrase).violations == []

    def test_track_without_name(self):
        # Worst-case: missing name → "an unnamed track"; still ≥75.
        track = {"track_id": "capability_lifecycle_track:nameless"}
        phrase = compose_pending_gate_phrase(track)
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert "an unnamed track" in phrase
        assert audit_partner_voice(phrase).violations == []

    def test_track_without_stuck_since(self):
        # Missing stuck_since → "an unspecified time"; still ≥75.
        track = {"track_id": "capability_lifecycle_track:no-time", "name": "feature-x"}
        phrase = compose_pending_gate_phrase(track)
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert "an unspecified time" in phrase
        assert audit_partner_voice(phrase).violations == []

    def test_track_completely_minimal(self):
        # Worst-of-worst: empty dict.
        phrase = compose_pending_gate_phrase({})
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert "an unnamed track" in phrase
        assert "an unspecified time" in phrase
        assert audit_partner_voice(phrase).violations == []

    def test_track_stuck_since_as_datetime(self):
        # Regression: stuck_since may arrive as datetime from SurrealDB hydration.
        now = _fixed_now()
        track = {
            "track_id": "capability_lifecycle_track:dt",
            "name": "feature-y",
            "stuck_since": now - timedelta(hours=2),
        }
        phrase = compose_pending_gate_phrase(track)
        assert phrase.startswith("we ")
        assert len(phrase) >= 75
        assert audit_partner_voice(phrase).violations == []
