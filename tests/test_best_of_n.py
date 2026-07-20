import pytest

from core.engine.cognition.best_of_n import BestOfNSampler, PhaseCandidate
from core.engine.cognition.phase_output import PhaseOutput


def _candidate(output: str, confidence: float, score: float = 0.0) -> PhaseCandidate:
    po = PhaseOutput(output=output, confidence=confidence, evidence=[], gaps=[])
    return PhaseCandidate(output=output, phase_output=po, score=score)


def test_select_best_single_candidate():
    sampler = BestOfNSampler()
    candidates = [_candidate("only", 0.7)]
    assert sampler.select_best(candidates).output == "only"


def test_select_best_picks_highest_confidence_when_unscored():
    sampler = BestOfNSampler()
    candidates = [
        _candidate("low", 0.3),
        _candidate("high", 0.8),  # winner: 0.6*0.8 = 0.48
        _candidate("mid", 0.5),
    ]
    assert sampler.select_best(candidates).output == "high"


def test_select_best_score_overrides_confidence():
    sampler = BestOfNSampler()
    candidates = [
        _candidate("high_conf_no_score", confidence=0.9, score=0.0),  # key=0.54
        _candidate("low_conf_high_score", confidence=0.4, score=1.0),  # key=0.24+0.40=0.64  ← winner
    ]
    assert sampler.select_best(candidates).output == "low_conf_high_score"


def test_select_best_blends_confidence_and_score():
    sampler = BestOfNSampler()
    candidates = [
        _candidate("a", confidence=0.6, score=0.6),  # key=0.36+0.24=0.60
        _candidate("b", confidence=0.8, score=0.4),  # key=0.48+0.16=0.64  ← winner
        _candidate("c", confidence=0.5, score=0.7),  # key=0.30+0.28=0.58
    ]
    assert sampler.select_best(candidates).output == "b"


def test_select_best_raises_on_empty():
    sampler = BestOfNSampler()
    with pytest.raises(ValueError, match="non-empty"):
        sampler.select_best([])
