"""Verify session.start.rendered is registered in journey_voice + threshold constants exist."""

from __future__ import annotations


def test_session_start_rendered_topic_registered():
    from core.engine.cognition.journey_voice import KNOWN_TOPICS, render_summary

    assert "session.start.rendered" in KNOWN_TOPICS
    out = render_summary("session.start.rendered", {}, trace=None)
    assert out  # non-empty


def test_threshold_constants_exposed():
    from core.engine.voice.audit import VOICE_AUDIT_AMBIENT_THRESHOLD, VOICE_AUDIT_TEASER_THRESHOLD

    assert 0.0 <= VOICE_AUDIT_AMBIENT_THRESHOLD <= 1.0
    assert 0.0 <= VOICE_AUDIT_TEASER_THRESHOLD <= 1.0
    # Sanity: ambient is more permissive than teaser (badge fires later than hook teaser)
    assert VOICE_AUDIT_AMBIENT_THRESHOLD <= VOICE_AUDIT_TEASER_THRESHOLD
