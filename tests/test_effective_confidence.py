"""effective_confidence — the confidence the system USES for decisions: calibrated when present, else
raw self_assessment. Python mirror of the SQL (calibrated_assessment ?? self_assessment) at the
confidence gates. See docs/superpowers/specs/2026-06-23-calibration-apply-consumers-design.md.
"""

from __future__ import annotations

from core.engine.intelligence.calibration import effective_confidence


def test_prefers_calibrated_when_present():
    task = {"self_assessment": 0.9, "calibrated_assessment": 0.2}
    assert effective_confidence(task) == 0.2


def test_falls_back_to_raw_when_calibrated_none():
    task = {"self_assessment": 0.3, "calibrated_assessment": None}
    assert effective_confidence(task) == 0.3


def test_falls_back_to_raw_when_calibrated_absent():
    assert effective_confidence({"self_assessment": 0.55}) == 0.55


def test_default_when_neither_present():
    assert effective_confidence({}) == 0.0
    assert effective_confidence({}, default=0.7) == 0.7


def test_object_valued_calibrated_skipped_falls_back():
    # calibrated_assessment redefined object-typed (schema split) — non-number must not be used.
    task = {"self_assessment": 0.4, "calibrated_assessment": {"nested": 1}}
    assert effective_confidence(task) == 0.4


def test_bool_calibrated_not_treated_as_number():
    # bool is an int subclass; a stray True must not become 1.0
    task = {"self_assessment": 0.4, "calibrated_assessment": True}
    assert effective_confidence(task) == 0.4
