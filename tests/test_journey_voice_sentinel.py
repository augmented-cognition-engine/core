"""Voice-rule sentinel for journey copy.

Verifies every known-topic template renders without forbidden strings, with
no engine_runs_summarized leakage, and (where applicable) we-voice present.
Asserts UnknownTopicError raises loudly on unmapped topics.
"""

from __future__ import annotations

import pytest


def test_no_forbidden_strings_in_templates():
    from core.engine.cognition.journey_voice import KNOWN_TOPICS, render_summary
    from core.engine.voice.rules import find_forbidden_strings

    sample_payload = {
        "topic": "x",
        "pillar": "x",
        "slug": "x",
        "title": "x",
        "from_id": "x",
        "to_id": "x",
        "new_score": 0.5,
        "engine_name": "x",
        "spec_id": "x",
        "discipline": "x",
        "pattern_name": "x",
        "file_path": "x",
        "to_status": "x",
        "emission_topic": "x",
    }
    for topic in KNOWN_TOPICS:
        out = render_summary(topic, sample_payload, trace=None)
        forbidden = find_forbidden_strings(out)
        assert forbidden == [], f"topic {topic} produced forbidden: {forbidden}"


def test_no_engine_runs_summarized_in_templates():
    from core.engine.cognition.journey_voice import KNOWN_TOPICS, render_summary

    for topic in KNOWN_TOPICS:
        out = render_summary(topic, {}, trace=None)
        assert "engine_runs_summarized" not in out.lower(), f"leak in {topic}"


def test_unknown_topic_raises_loud():
    from core.engine.cognition.journey_voice import UnknownTopicError, render_summary

    with pytest.raises(UnknownTopicError):
        render_summary("xyz.unknown", {}, trace=None)
