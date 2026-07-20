"""Trust as a believability multiplier in retrieval ranking (#3 — gives the provenance system its
runtime teeth). Pure functions: trust DISCOUNTS insights explicitly scored low-trust, and is NEUTRAL
(no penalty) for un-reconciled insights (trust IS NONE) so missing data is never punished."""

import pytest

from core.engine.orchestrator.trust_ranking import trust_multiplier, trust_weighted


def test_none_trust_is_neutral():
    # Un-reconciled insight (reconciler hasn't run yet) → no discount, ranks on confidence alone.
    assert trust_multiplier(None) == 1.0
    assert trust_weighted(0.8, None) == pytest.approx(0.8)


def test_low_trust_discounts():
    # A self-generated reasoning insight (trust 0.5) gets its rank halved.
    assert trust_multiplier(0.5) == 0.5
    assert trust_weighted(0.9, 0.5) == pytest.approx(0.45)


def test_high_trust_barely_discounts():
    assert trust_weighted(0.7, 0.95) == pytest.approx(0.665)


def test_low_trust_high_confidence_ranks_below_high_trust_medium_confidence():
    """The whole point: a confidently-stated self-generated insight must not out-rank a well-trusted
    human capture. reasoning(conf 0.9, trust 0.5)=0.45 < human(conf 0.7, trust 0.8)=0.56."""
    reasoning = trust_weighted(0.9, 0.5)
    human = trust_weighted(0.7, 0.8)
    assert reasoning < human


def test_multiplier_clamped_and_fault_tolerant():
    assert trust_multiplier(1.5) == 1.0  # clamp high
    assert trust_multiplier(-0.2) == 0.0  # clamp low
    assert trust_multiplier("bad") == 1.0  # non-numeric → neutral (never crash retrieval)
    assert trust_multiplier(0.0) == 0.0  # a fully-distrusted insight is floored, not treated as None
