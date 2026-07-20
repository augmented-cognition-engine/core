"""Tests for confidence model."""

from core.engine.research.confidence import ConfidenceScore, compute_confidence
from core.engine.research.source_registry import SourceClass


def test_reference_with_corroboration_is_high():
    score = compute_confidence(SourceClass.REFERENCE, corroboration_count=2)
    assert score.tier == "high"
    assert score.value >= 0.85
    assert not score.flagged
    assert score.decay_days == 30


def test_reference_alone_is_medium_high():
    score = compute_confidence(SourceClass.REFERENCE, corroboration_count=1)
    assert score.tier == "medium_high"
    assert score.value >= 0.7
    assert not score.flagged


def test_exemplar_with_corroboration_is_medium_high():
    score = compute_confidence(SourceClass.EXEMPLAR, corroboration_count=3)
    assert score.tier == "medium_high"
    assert not score.flagged


def test_exemplar_alone_is_medium():
    score = compute_confidence(SourceClass.EXEMPLAR, corroboration_count=1)
    assert score.tier == "medium"


def test_signal_with_corroboration_is_medium():
    score = compute_confidence(SourceClass.SIGNAL, corroboration_count=2)
    assert score.tier == "medium"
    assert not score.flagged


def test_signal_alone_is_low_and_flagged():
    score = compute_confidence(SourceClass.SIGNAL, corroboration_count=1)
    assert score.tier == "low"
    assert score.flagged
    assert score.value <= 0.35


def test_noise_is_zero_and_flagged():
    score = compute_confidence(SourceClass.NOISE)
    assert score.value == 0.0
    assert score.flagged
    assert score.tier == "noise"


def test_str_representation():
    score = compute_confidence(SourceClass.REFERENCE, corroboration_count=2)
    s = str(score)
    assert "high" in s
    assert "flagged" not in s

    flagged = compute_confidence(SourceClass.SIGNAL, corroboration_count=1)
    assert "flagged" in str(flagged)


def test_confidence_score_is_dataclass():
    score = ConfidenceScore(value=0.8, tier="high", decay_days=30, flagged=False)
    assert score.value == 0.8
    assert score.tier == "high"
