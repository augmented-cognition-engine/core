# tests/test_synthesizer_confidence.py
"""Tests for synthesizer handling of non-numeric confidence values."""


def test_safe_confidence_with_string():
    from core.engine.capture.synthesizer import _safe_confidence

    assert _safe_confidence("high") == 0.5


def test_safe_confidence_with_none():
    from core.engine.capture.synthesizer import _safe_confidence

    assert _safe_confidence(None) == 0.5


def test_safe_confidence_with_empty_string():
    from core.engine.capture.synthesizer import _safe_confidence

    assert _safe_confidence("") == 0.5


def test_safe_confidence_with_valid_float():
    from core.engine.capture.synthesizer import _safe_confidence

    assert _safe_confidence(0.85) == 0.85


def test_safe_confidence_with_string_number():
    from core.engine.capture.synthesizer import _safe_confidence

    assert _safe_confidence("0.7") == 0.7


def test_safe_confidence_clamps_above_one():
    from core.engine.capture.synthesizer import _safe_confidence

    assert _safe_confidence(1.5) == 1.0


def test_safe_confidence_clamps_below_zero():
    from core.engine.capture.synthesizer import _safe_confidence

    assert _safe_confidence(-0.3) == 0.0
