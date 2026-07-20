"""Unit tests for handoff helpers. Three pure functions:
- should_handoff(result): decide handoff from classifier result
- find_active_handoff(events): pick most recent handoff.recognized event
- compose_handoff_phrase(tool): partner-voice chip text
"""

from __future__ import annotations

import pytest

# -------- should_handoff --------


def test_should_handoff_true_when_below_threshold():
    from core.engine.cognition.handoff import HANDOFF_DEFAULT_TOOL, should_handoff

    fire, tool = should_handoff({"discipline_confidence": 0.2})
    assert fire is True
    assert tool == HANDOFF_DEFAULT_TOOL


def test_should_handoff_false_when_at_or_above_threshold():
    from core.engine.cognition.handoff import should_handoff

    # exactly at threshold (0.4) — does NOT fire (strict less-than)
    fire, tool = should_handoff({"discipline_confidence": 0.4})
    assert fire is False
    assert tool is None
    # well above
    fire2, tool2 = should_handoff({"discipline_confidence": 0.85})
    assert fire2 is False
    assert tool2 is None


def test_should_handoff_false_when_key_missing():
    from core.engine.cognition.handoff import should_handoff

    fire, tool = should_handoff({})
    assert fire is False
    assert tool is None


def test_should_handoff_false_when_input_not_dict():
    from core.engine.cognition.handoff import should_handoff

    fire, tool = should_handoff("not-a-dict")  # type: ignore[arg-type]
    assert fire is False
    assert tool is None


def test_should_handoff_false_when_confidence_not_numeric():
    from core.engine.cognition.handoff import should_handoff

    fire, tool = should_handoff({"discipline_confidence": "low"})
    assert fire is False
    assert tool is None


# -------- compose_handoff_phrase --------


def test_phrase_contains_tool_name_and_partner_voice():
    from core.engine.cognition.handoff import compose_handoff_phrase

    p = compose_handoff_phrase("Claude")
    assert p.startswith("we recognized")
    assert "Claude" in p


def test_phrase_meets_length_floor():
    """Length floor — chip phrase ≥75 chars even with shortest plausible tool name."""
    from core.engine.cognition.handoff import compose_handoff_phrase

    p = compose_handoff_phrase("X")  # 1-char tool
    assert len(p) >= 75, f"phrase too short ({len(p)} chars): {p!r}"


def test_phrase_passes_audit_partner_voice():
    """Snapshot test: representative tool names all produce audit-passing phrases."""
    from core.engine.cognition.handoff import compose_handoff_phrase
    from core.engine.voice.audit import audit_partner_voice

    for tool in ("Claude", "GPT", "Cursor", "X"):
        p = compose_handoff_phrase(tool)
        result = audit_partner_voice(p)
        assert result.violations == [], f"phrase for {tool!r} failed audit: {p!r} (violations: {result.violations})"


def test_phrase_raises_for_empty_tool():
    from core.engine.cognition.handoff import compose_handoff_phrase

    with pytest.raises(ValueError, match="tool"):
        compose_handoff_phrase("")


# -------- find_active_handoff --------


def test_find_active_handoff_none_for_empty_events():
    from core.engine.cognition.handoff import find_active_handoff

    assert find_active_handoff([]) is None


def test_find_active_handoff_ignores_non_handoff_topics():
    from core.engine.cognition.handoff import find_active_handoff

    events = [
        {"id": "journey_event:1", "topic": "gap.detected", "occurred_at": "2026-05-02T10:00:00Z", "payload": {}},
        {"id": "journey_event:2", "topic": "review.completed", "occurred_at": "2026-05-02T11:00:00Z", "payload": {}},
    ]
    assert find_active_handoff(events) is None


def test_find_active_handoff_picks_most_recent():
    from core.engine.cognition.handoff import HANDOFF_TOOL_URL, find_active_handoff

    events = [
        {
            "id": "journey_event:1",
            "topic": "handoff.recognized",
            "occurred_at": "2026-05-02T09:00:00Z",
            "payload": {"suggested_external_tool": "Claude"},
        },
        {"id": "journey_event:2", "topic": "gap.detected", "occurred_at": "2026-05-02T10:00:00Z", "payload": {}},
        {
            "id": "journey_event:3",
            "topic": "handoff.recognized",
            "occurred_at": "2026-05-02T11:00:00Z",
            "payload": {"suggested_external_tool": "Claude"},
        },
    ]
    result = find_active_handoff(events)
    assert result is not None
    assert result["tool"] == "Claude"
    assert result["url"] == HANDOFF_TOOL_URL["Claude"]
    assert result["source_event_id"] == "journey_event:3"
    assert result["observed_at"] == "2026-05-02T11:00:00Z"
    assert "we recognized" in result["phrase"]
    assert "Claude" in result["phrase"]


def test_find_active_handoff_handles_missing_payload_tool():
    """If payload lacks suggested_external_tool, fall back to default."""
    from core.engine.cognition.handoff import HANDOFF_DEFAULT_TOOL, find_active_handoff

    events = [
        {"id": "journey_event:1", "topic": "handoff.recognized", "occurred_at": "2026-05-02T11:00:00Z", "payload": {}},
    ]
    result = find_active_handoff(events)
    assert result is not None
    assert result["tool"] == HANDOFF_DEFAULT_TOOL


def test_find_active_handoff_unknown_tool_url_falls_back():
    """Unknown tool name → URL falls back to claude.ai."""
    from core.engine.cognition.handoff import find_active_handoff

    events = [
        {
            "id": "journey_event:1",
            "topic": "handoff.recognized",
            "occurred_at": "2026-05-02T11:00:00Z",
            "payload": {"suggested_external_tool": "MysteryTool"},
        },
    ]
    result = find_active_handoff(events)
    assert result is not None
    assert result["tool"] == "MysteryTool"
    # URL falls back to claude.ai when tool unknown
    assert result["url"] == "https://claude.ai"
