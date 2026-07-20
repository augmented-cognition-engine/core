# tests/cognition/test_disagreement_signal.py
"""Phase 0 — the self-consistency disagreement signal (pure function).

The close-call evaluator already samples the same model 3×; today it averages the
scores and discards the spread. The spread is a free *honesty* signal: when the
model disagrees with itself, the verdict is unstable. (The evaluator-integration
behaviour is tested in tests/test_phase_evaluator.py, which is exempt from the
autouse evaluator stub.)
"""

import pytest

from core.engine.cognition.phase_evaluator import EvaluationResult
from core.engine.cognition.self_consistency import disagreement


def _r(score):
    return EvaluationResult(score=score, reasoning="x")


def test_disagreement_zero_when_scores_agree():
    assert disagreement([_r(0.5), _r(0.5), _r(0.5)]) == 0.0


def test_disagreement_is_score_spread():
    assert disagreement([_r(0.3), _r(0.6), _r(0.5)]) == pytest.approx(0.3)


def test_disagreement_max_at_full_spread():
    """Boundary: a 0.0 / 1.0 split is maximal disagreement (1.0) → max 20% haircut."""
    assert disagreement([_r(0.0), _r(0.5), _r(1.0)]) == pytest.approx(1.0)


def test_disagreement_ignores_non_numeric_scores():
    class _NoScore:
        pass

    assert disagreement([_r(0.2), _NoScore(), _r(0.7)]) == pytest.approx(0.5)


def test_disagreement_zero_with_fewer_than_two_samples():
    assert disagreement([_r(0.5)]) == 0.0
    assert disagreement([]) == 0.0


def test_non_close_call_result_has_zero_disagreement_default():
    """A confident (non-close-call) EvaluationResult carries disagreement=0.0."""
    assert EvaluationResult(score=0.9, reasoning="clear").disagreement == 0.0
