"""Tests for the journey partner-voice generator."""

from __future__ import annotations

import pytest


def test_render_summary_canvas_thread_committed():
    from core.engine.cognition.journey_voice import render_summary

    out = render_summary(
        "canvas.thread.committed",
        {"topic": "auth middleware refactor"},
        trace=None,
    )
    assert "auth middleware refactor" in out
    assert out  # non-empty


def test_render_summary_gap_detected():
    from core.engine.cognition.journey_voice import render_summary

    out = render_summary(
        "gap.detected",
        {"pillar": "test coverage"},
        trace=None,
    )
    assert "test coverage" in out


def test_render_summary_unknown_topic_raises():
    from core.engine.cognition.journey_voice import UnknownTopicError, render_summary

    with pytest.raises(UnknownTopicError):
        render_summary("definitely.not.a.topic", {}, trace=None)


def test_known_topics_full_set_renders():
    """Every entry in KNOWN_TOPICS renders without raising."""
    from core.engine.cognition.journey_voice import KNOWN_TOPICS, render_summary

    for topic in KNOWN_TOPICS:
        out = render_summary(topic, {}, trace=None)
        assert out, f"empty render for {topic}"


def test_known_topics_covers_canvas_enum():
    """KNOWN_TOPICS includes all 21 LivingCanvasEventType values prefixed canvas.<type>."""
    from core.engine.cognition.journey_voice import KNOWN_TOPICS
    from core.engine.events.canvas import LivingCanvasEventType

    for ev in LivingCanvasEventType:
        assert f"canvas.{ev.value}" in KNOWN_TOPICS, f"missing template for canvas.{ev.value}"
