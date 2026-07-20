"""Unit tests for loop iteration helpers. Three pure functions:
- cluster_events(events, gap_seconds): group events by temporal proximity
- compose_iteration_phrase(iteration): partner-voice summary sentence
- summarize_topics(event_ids_by_topic, max_named): compact topic listing
"""

from __future__ import annotations

from datetime import datetime, timezone

# -------- cluster_events --------


def test_cluster_events_empty():
    from core.engine.cognition.loop_iterations import cluster_events

    assert cluster_events([]) == []


def test_cluster_events_single():
    from core.engine.cognition.loop_iterations import cluster_events

    events = [{"id": "ev:1", "occurred_at": "2026-05-03T10:00:00Z", "topic": "capture"}]
    result = cluster_events(events)
    assert len(result) == 1
    assert result[0]["event_ids"] == ["ev:1"]
    assert result[0]["started_at"] == "2026-05-03T10:00:00Z"
    assert result[0]["ended_at"] == "2026-05-03T10:00:00Z"


def test_cluster_events_two_within_window():
    from core.engine.cognition.loop_iterations import cluster_events

    events = [
        {"id": "ev:1", "occurred_at": "2026-05-03T10:00:00Z", "topic": "capture"},
        {"id": "ev:2", "occurred_at": "2026-05-03T10:00:30Z", "topic": "gap.detected"},
    ]
    result = cluster_events(events, gap_seconds=90)
    assert len(result) == 1
    assert result[0]["event_ids"] == ["ev:1", "ev:2"]


def test_cluster_events_two_beyond_window():
    from core.engine.cognition.loop_iterations import cluster_events

    events = [
        {"id": "ev:1", "occurred_at": "2026-05-03T10:00:00Z", "topic": "capture"},
        {"id": "ev:2", "occurred_at": "2026-05-03T10:05:00Z", "topic": "capture"},
    ]
    result = cluster_events(events, gap_seconds=90)
    assert len(result) == 2


def test_cluster_events_accepts_datetime_occurred_at():
    """SurrealDB hydrates `datetime` columns as datetime objects when
    reading from real tables — cluster_events must accept them and
    normalize to ISO-string output."""
    from core.engine.cognition.loop_iterations import cluster_events

    events = [
        {"id": "ev:1", "occurred_at": datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc), "topic": "capture"},
        {"id": "ev:2", "occurred_at": datetime(2026, 5, 3, 10, 0, 30, tzinfo=timezone.utc), "topic": "gap.detected"},
    ]
    result = cluster_events(events, gap_seconds=90)
    assert len(result) == 1
    # started_at / ended_at must be strings even though input was datetime
    assert isinstance(result[0]["started_at"], str)
    assert isinstance(result[0]["ended_at"], str)
    assert result[0]["started_at"].startswith("2026-05-03T10:00:00")


def test_cluster_events_three_a_b_gap_c():
    """A-30s-B-200s-C → [A,B] then [C]"""
    from core.engine.cognition.loop_iterations import cluster_events

    events = [
        {"id": "ev:A", "occurred_at": "2026-05-03T10:00:00Z", "topic": "capture"},
        {"id": "ev:B", "occurred_at": "2026-05-03T10:00:30Z", "topic": "gap.detected"},
        {"id": "ev:C", "occurred_at": "2026-05-03T10:04:00Z", "topic": "composition.attached"},
    ]
    result = cluster_events(events, gap_seconds=90)
    assert len(result) == 2
    assert result[0]["event_ids"] == ["ev:A", "ev:B"]
    assert result[1]["event_ids"] == ["ev:C"]


# -------- compose_iteration_phrase --------


def test_compose_iteration_phrase_single_event():
    from core.engine.cognition.loop_iterations import compose_iteration_phrase

    iteration = {
        "started_at": "2026-05-03T10:00:00Z",
        "ended_at": "2026-05-03T10:00:00Z",
        "event_ids": ["ev:1"],
        "topics": {"capture": ["ev:1"]},
    }
    phrase = compose_iteration_phrase(iteration)
    assert phrase.startswith(("we ", "between ", "our "))
    assert len(phrase) >= 75
    assert "capture" in phrase
    assert "[unknown topic:" not in phrase


def test_compose_iteration_phrase_multi_event():
    from core.engine.cognition.loop_iterations import compose_iteration_phrase

    iteration = {
        "started_at": "2026-05-03T10:00:00Z",
        "ended_at": "2026-05-03T10:01:30Z",
        "event_ids": ["ev:1", "ev:2", "ev:3"],
        "topics": {"capture": ["ev:1", "ev:2"], "gap.detected": ["ev:3"]},
    }
    phrase = compose_iteration_phrase(iteration)
    assert phrase.startswith(("we ", "between ", "our "))
    assert len(phrase) >= 75
    assert "capture" in phrase or "gap.detected" in phrase
    assert "3" in phrase or "three" in phrase  # reflects event_count
    assert "[unknown topic:" not in phrase


def test_compose_iteration_phrase_partner_voice_audit():
    """Run the audit_partner_voice rule across both branches."""
    from core.engine.cognition.loop_iterations import compose_iteration_phrase
    from core.engine.voice.audit import audit_partner_voice

    single = compose_iteration_phrase(
        {
            "started_at": "2026-05-03T10:00:00Z",
            "ended_at": "2026-05-03T10:00:00Z",
            "event_ids": ["ev:1"],
            "topics": {"capture": ["ev:1"]},
        }
    )
    multi = compose_iteration_phrase(
        {
            "started_at": "2026-05-03T10:00:00Z",
            "ended_at": "2026-05-03T10:01:30Z",
            "event_ids": ["ev:1", "ev:2"],
            "topics": {"capture": ["ev:1", "ev:2"]},
        }
    )
    for phrase in (single, multi):
        result = audit_partner_voice(phrase)
        assert result.violations == [], f"voice violations in {phrase!r}: {result.violations}"


# -------- summarize_topics --------


def test_summarize_topics_empty():
    from core.engine.cognition.loop_iterations import summarize_topics

    assert summarize_topics({}) == ""


def test_summarize_topics_single():
    from core.engine.cognition.loop_iterations import summarize_topics

    assert summarize_topics({"capture": ["a", "b"]}) == "capture"


def test_summarize_topics_three_uses_comma():
    from core.engine.cognition.loop_iterations import summarize_topics

    out = summarize_topics(
        {
            "capture": ["a"],
            "gap.detected": ["b"],
            "composition.attached": ["c"],
        }
    )
    assert "capture" in out and "gap.detected" in out and "composition.attached" in out
    assert "," in out


def test_summarize_topics_max_named():
    from core.engine.cognition.loop_iterations import summarize_topics

    out = summarize_topics(
        {f"topic{i}": ["x"] for i in range(5)},
        max_named=3,
    )
    # exactly 3 named topics + +2 more
    assert "+2 more" in out
