"""Unit tests for active discipline helpers. Two pure functions:
- find_active_discipline(events): pick most recent event with discipline_classified
- compose_discipline_phrase(discipline, signals, topic): partner-voice render
"""

from __future__ import annotations

import pytest

# -------- find_active_discipline --------


def test_find_active_discipline_returns_none_for_empty_events():
    from core.engine.cognition.active_discipline import find_active_discipline

    assert find_active_discipline([]) is None


def test_find_active_discipline_ignores_events_without_discipline():
    from core.engine.cognition.active_discipline import find_active_discipline

    events = [
        {
            "id": "journey_event:1",
            "topic": "gap.detected",
            "occurred_at": "2026-05-02T10:00:00Z",
            "composition_trace": {"meta_skills": ["a"], "frame": "f", "signals": {}},
        },
        {
            "id": "journey_event:2",
            "topic": "session.started",
            "occurred_at": "2026-05-02T11:00:00Z",
            "composition_trace": None,
        },
    ]
    assert find_active_discipline(events) is None


def test_find_active_discipline_picks_most_recent_classified():
    from core.engine.cognition.active_discipline import find_active_discipline

    events = [
        {
            "id": "journey_event:1",
            "topic": "gap.detected",
            "occurred_at": "2026-05-02T09:00:00Z",
            "composition_trace": {"signals": {"discipline_classified": "data"}},
        },
        {
            "id": "journey_event:2",
            "topic": "review.completed",
            "occurred_at": "2026-05-02T11:00:00Z",
            "composition_trace": {"signals": {"discipline_classified": "ux", "phase": "BUILD"}},
        },
        {
            "id": "journey_event:3",
            "topic": "outcome.committed",
            "occurred_at": "2026-05-02T10:00:00Z",
            "composition_trace": {"signals": {"discipline_classified": "logic"}},
        },
    ]
    result = find_active_discipline(events)
    assert result is not None
    assert result["discipline"] == "ux"
    assert result["source_event_id"] == "journey_event:2"
    assert result["observed_at"] == "2026-05-02T11:00:00Z"
    # phrase populated by compose_discipline_phrase
    assert "we see you're shaping ux" in result["phrase"]


def test_find_active_discipline_handles_missing_signals_dict():
    from core.engine.cognition.active_discipline import find_active_discipline

    # Trace present but no signals key — graceful skip, not crash
    events = [
        {
            "id": "journey_event:1",
            "topic": "gap.detected",
            "occurred_at": "2026-05-02T10:00:00Z",
            "composition_trace": {"meta_skills": ["a"], "frame": "f"},
        },
    ]
    assert find_active_discipline(events) is None


# -------- compose_discipline_phrase --------


def test_compose_phrase_with_phase_signal():
    from core.engine.cognition.active_discipline import compose_discipline_phrase

    phrase = compose_discipline_phrase("ux", {"phase": "BUILD"}, "review.completed")
    assert phrase.startswith("we see you're shaping ux")
    assert "phase BUILD" in phrase


def test_compose_phrase_with_pillar_floor_signal():
    from core.engine.cognition.active_discipline import compose_discipline_phrase

    phrase = compose_discipline_phrase("logic", {"pillar_floor": {"logic": 0.42}}, "gap.detected")
    assert phrase.startswith("we see you're shaping logic")
    assert "logic dipped to 0.42" in phrase


def test_compose_phrase_no_signals_uses_topic_fallback():
    from core.engine.cognition.active_discipline import compose_discipline_phrase

    phrase = compose_discipline_phrase("ux", {}, "gap.detected")
    # Falls back to topic-based context to keep phrase rich
    assert phrase.startswith("we see you're shaping ux")
    assert "gap.detected" in phrase
    assert "from what we read" in phrase


def test_compose_phrase_meets_length_floor():
    """Even minimum-length input (2-char discipline, no signals) produces ≥75 chars."""
    from core.engine.cognition.active_discipline import compose_discipline_phrase

    phrase = compose_discipline_phrase("ux", {}, "x.y")
    assert len(phrase) >= 75, f"phrase too short ({len(phrase)} chars): {phrase!r}"


def test_compose_phrase_passes_audit_partner_voice_across_shapes():
    """Snapshot test: every representative input must satisfy audit_partner_voice."""
    from core.engine.cognition.active_discipline import compose_discipline_phrase
    from core.engine.voice.audit import audit_partner_voice

    samples = [
        ("ux", {"phase": "BUILD"}, "review.completed"),
        ("logic", {"pillar_floor": {"logic": 0.42}}, "gap.detected"),
        ("ux", {}, "gap.detected"),
        ("data", {"phase": "DISCOVER"}, "outcome.committed"),
    ]
    for discipline, signals, topic in samples:
        phrase = compose_discipline_phrase(discipline, signals, topic)
        result = audit_partner_voice(phrase)
        assert result.violations == [], (
            f"phrase failed audit for ({discipline!r}, {signals!r}, {topic!r}): "
            f"{phrase!r} (violations: {result.violations})"
        )


def test_compose_phrase_raises_for_empty_discipline():
    from core.engine.cognition.active_discipline import compose_discipline_phrase

    with pytest.raises(ValueError, match="discipline"):
        compose_discipline_phrase("", {"phase": "BUILD"}, "review.completed")
