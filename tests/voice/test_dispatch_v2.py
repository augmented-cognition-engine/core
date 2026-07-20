"""Tests for VoiceDispatch dataclass and the inverted _dispatch_to_voice shape."""

from __future__ import annotations

from core.engine.voice.dispatch import VoiceDispatch


def test_voice_dispatch_fields():
    from core.engine.voice.renderers import render_recommendation

    rec = {"pillar": "experience", "discipline": "ux", "gap": 0.3, "blocking_patterns": []}
    d = VoiceDispatch(
        renderer=render_recommendation,
        render_input=rec,
        priority="HIGH",
        topic="rec:experience.ux",
        thread_bearing=True,
    )
    assert d.priority == "HIGH"
    assert d.topic == "rec:experience.ux"
    assert d.thread_bearing is True


def test_dispatch_to_voice_drift_returns_voice_dispatch():
    from core.engine.voice.stream import _dispatch_to_voice

    payload = {
        "prev_blocked_frac": 0.3,
        "new_blocked_frac": 0.7,
        "blocking_pillars": ["experience"],
        "n_total": 15,
        "n_blocked": 11,
    }
    result = _dispatch_to_voice("canvas.drift.crossed", payload)
    assert isinstance(result, VoiceDispatch)
    assert result.priority == "HIGH"
    assert result.topic == "drift"
    assert result.thread_bearing is False


def test_dispatch_to_voice_recommendation_shifted_swap():
    from core.engine.voice.stream import _dispatch_to_voice

    payload = {
        "top_pillar": "experience",
        "top_discipline": "accessibility",
        "swap": True,
        "rec": {"pillar": "experience", "discipline": "accessibility", "gap": 0.5, "blocking_patterns": []},
    }
    result = _dispatch_to_voice("canvas.recommendation.shifted", payload)
    assert isinstance(result, VoiceDispatch)
    assert result.priority == "HIGH"
    assert result.topic == "rec:experience.accessibility"
    assert result.thread_bearing is True


def test_dispatch_to_voice_recommendation_shifted_no_swap():
    from core.engine.voice.stream import _dispatch_to_voice

    payload = {
        "top_pillar": "experience",
        "top_discipline": "ux",
        "swap": False,
        "rec": {"pillar": "experience", "discipline": "ux", "gap": 0.3, "blocking_patterns": []},
    }
    result = _dispatch_to_voice("canvas.recommendation.shifted", payload)
    assert isinstance(result, VoiceDispatch)
    assert result.priority == "MEDIUM"
    assert result.thread_bearing is True


def test_dispatch_to_voice_score_changed_returns_none():
    from core.engine.voice.stream import _dispatch_to_voice

    result = _dispatch_to_voice("canvas.score.changed", {})
    assert result is None


def test_dispatch_to_voice_handoff_progress_returns_none():
    from core.engine.voice.stream import _dispatch_to_voice

    result = _dispatch_to_voice("canvas.handoff.progress", {})
    assert result is None


def test_dispatch_to_voice_unknown_event_returns_none():
    from core.engine.voice.stream import _dispatch_to_voice

    result = _dispatch_to_voice("canvas.unknown.event", {})
    assert result is None


def test_dispatch_to_voice_uncertainty_opened_is_not_thread_bearing():
    from core.engine.voice.stream import _dispatch_to_voice

    payload = {"query_id": "q1", "question": "Is the DB ready?"}
    result = _dispatch_to_voice("canvas.uncertainty.opened", payload)
    assert isinstance(result, VoiceDispatch)
    assert result.priority == "HIGH"
    assert result.thread_bearing is False


def test_dispatch_to_voice_state_change_is_not_thread_bearing():
    from core.engine.voice.stream import _dispatch_to_voice

    result = _dispatch_to_voice("canvas.capability.added", {"description": "new thing"})
    assert isinstance(result, VoiceDispatch)
    assert result.thread_bearing is False
