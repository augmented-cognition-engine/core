"""Unit tests for compose_headline. Pins the partner-voice contract:
- always opens with 'We', satisfies audit_partner_voice
- expresses signals in plain phrases, not raw dict dumps
- handles missing fields gracefully
"""

from __future__ import annotations

import pytest


def test_headline_basic_two_skills_with_phase_signal():
    from core.engine.cognition.composition_headline import compose_headline

    trace = {
        "meta_skills": ["systems_intelligence", "verification_intelligence"],
        "frame": "scaling-architecture",
        "signals": {"phase": "BUILD"},
    }
    result = compose_headline(trace)
    assert result.startswith("We composed ")
    assert "systems intelligence and verification intelligence" in result
    assert "scaling-architecture" in result
    assert "your phase is BUILD" in result


def test_headline_three_skills_uses_oxford_join():
    from core.engine.cognition.composition_headline import compose_headline

    trace = {
        "meta_skills": ["a_intel", "b_intel", "c_intel"],
        "frame": "framework-x",
        "signals": {"phase": "DISCOVER"},
    }
    result = compose_headline(trace)
    # 3-element join uses commas with final ', and'
    assert "a intel, b intel, and c intel" in result


def test_headline_pillar_floor_signal():
    from core.engine.cognition.composition_headline import compose_headline

    trace = {
        "meta_skills": ["systems_intelligence"],
        "frame": "logic-floor",
        "signals": {"pillar_floor": {"logic": 0.42}},
    }
    result = compose_headline(trace)
    assert "logic dipped to 0.42" in result


def test_headline_discipline_signal():
    from core.engine.cognition.composition_headline import compose_headline

    trace = {
        "meta_skills": ["ux_intel"],
        "frame": "ux-frame",
        "signals": {"discipline_classified": "ux"},
    }
    result = compose_headline(trace)
    assert "the work classifies as ux" in result


def test_headline_unknown_signals_falls_back_gracefully():
    from core.engine.cognition.composition_headline import compose_headline

    trace = {
        "meta_skills": ["mystery_intel"],
        "frame": "unknown-frame",
        "signals": {"some_unrecognized_field": "value"},
    }
    result = compose_headline(trace)
    assert "the signals matched" in result


def test_headline_empty_signals_dict_falls_back():
    from core.engine.cognition.composition_headline import compose_headline

    trace = {
        "meta_skills": ["mystery_intel"],
        "frame": "unknown-frame",
        "signals": {},
    }
    result = compose_headline(trace)
    assert "the signals matched" in result


def test_headline_passes_audit_partner_voice():
    """Snapshot test: every representative trace shape must satisfy audit_partner_voice."""
    from core.engine.cognition.composition_headline import compose_headline
    from core.engine.voice.audit import audit_partner_voice

    samples = [
        {"meta_skills": ["a"], "frame": "x", "signals": {}},
        {"meta_skills": ["a", "b"], "frame": "x-y", "signals": {"phase": "BUILD"}},
        {"meta_skills": ["a", "b", "c"], "frame": "x", "signals": {"pillar_floor": {"logic": 0.5}}},
        {"meta_skills": ["a"], "frame": "x", "signals": {"discipline_classified": "data"}},
        {"meta_skills": ["a"], "frame": "x", "signals": {}, "scenario": "demo", "perspectives": ["p1"]},
    ]
    for trace in samples:
        result = compose_headline(trace)
        audit = audit_partner_voice(result)
        assert audit.violations == [], (
            f"trace {trace} produced violating headline: {result!r} (violations: {audit.violations})"
        )


def test_headline_missing_meta_skills_raises():
    from core.engine.cognition.composition_headline import compose_headline

    with pytest.raises(ValueError, match="meta_skills"):
        compose_headline({"meta_skills": [], "frame": "x", "signals": {}})


def test_headline_missing_frame_raises():
    from core.engine.cognition.composition_headline import compose_headline

    with pytest.raises(ValueError, match="frame"):
        compose_headline({"meta_skills": ["a"], "frame": "", "signals": {}})
