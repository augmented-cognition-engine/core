"""Boundary tests: handoff.recognized topic registers correctly +
render_summary produces partner-voice text without the [unknown topic:] fallback."""

from __future__ import annotations


def test_handoff_recognized_topic_registered():
    from core.engine.cognition.journey_voice import _BUS_TOPICS

    assert "handoff.recognized" in _BUS_TOPICS
    template = _BUS_TOPICS["handoff.recognized"]
    assert isinstance(template, str)
    assert len(template) >= 10


def test_handoff_recognized_template_uses_partner_voice():
    import re

    from core.engine.cognition.journey_voice import _BUS_TOPICS

    template = _BUS_TOPICS["handoff.recognized"]
    assert re.search(r"\b(we|our|us)\b", template, flags=re.I), (
        f"handoff.recognized template missing partner voice: {template!r}"
    )


def test_render_summary_for_handoff_does_not_emit_unknown_topic():
    from core.engine.cognition.journey_voice import render_summary

    rendered = render_summary("handoff.recognized", {"suggested_external_tool": "Claude"})
    assert "[unknown topic:" not in rendered
    assert "Claude" in rendered or "we" in rendered.lower()
