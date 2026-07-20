"""Boundary test: outcome.* + effectiveness.score.recomputed topics
are registered in journey_voice so the journey API renders them
without a [unknown topic: ...] fallback."""

from __future__ import annotations


def test_outcome_topics_registered():
    from core.engine.cognition.journey_voice import _BUS_TOPICS

    for topic in ("outcome.committed", "outcome.ignored", "effectiveness.score.recomputed"):
        assert topic in _BUS_TOPICS, f"missing topic {topic} in _BUS_TOPICS"
        template = _BUS_TOPICS[topic]
        assert isinstance(template, str) and len(template) >= 10, f"empty template for {topic}"


def test_outcome_topic_templates_use_partner_voice():
    """Templates must contain we/our/us — partner voice rule per JT2."""
    import re

    from core.engine.cognition.journey_voice import _BUS_TOPICS

    for topic in ("outcome.committed", "outcome.ignored", "effectiveness.score.recomputed"):
        template = _BUS_TOPICS[topic]
        assert re.search(r"\b(we|our|us)\b", template, flags=re.I), (
            f"{topic} template missing we/our/us — voice rule violation"
        )
