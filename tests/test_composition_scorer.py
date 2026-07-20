from unittest.mock import patch

import pytest

from core.engine.orchestration.composition_scorer import (
    HIGH_UNCERTAIN_RATE,
    LOW_OUTCOME_CONFIDENCE,
    OUTCOME_PENALTY,
    ScoredComposition,
    _effective_accepted,
    _effective_rejected,
    score_composition,
)


@pytest.mark.asyncio
async def test_cold_start_no_signals():
    """No composition signals → all weights 1.0, no adjustments."""
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=[]):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["practitioner"],
                "engagement": {"perspectives": ["practitioner"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert isinstance(result, ScoredComposition)
    assert result.perspective_weights == {"practitioner": 1.0}
    assert result.adjustments == []


@pytest.mark.asyncio
async def test_low_acceptance_penalizes():
    """Perspectives with low acceptance rate get weight penalty."""
    signals = [{"perspectives": ["theorist"], "feedback": "rejected", "utilization_rate": 0.5} for _ in range(6)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["theorist"],
                "engagement": {"perspectives": ["theorist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.perspective_weights["theorist"] < 1.0
    assert result.perspective_weights["theorist"] >= 0.1


@pytest.mark.asyncio
async def test_low_utilization_penalizes():
    """Perspectives with low utilization rate get weight penalty."""
    signals = [{"perspectives": ["strategist"], "feedback": "accepted", "utilization_rate": 0.05} for _ in range(6)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "testing",
                "perspectives": ["strategist"],
                "engagement": {"perspectives": ["strategist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.perspective_weights["strategist"] < 1.0


@pytest.mark.asyncio
async def test_compound_penalty_clamps():
    """Both low acceptance + low utilization compounds but clamps to MIN_WEIGHT."""
    signals = [{"perspectives": ["theorist"], "feedback": "rejected", "utilization_rate": 0.05} for _ in range(10)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["theorist"],
                "engagement": {"perspectives": ["theorist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.perspective_weights["theorist"] >= 0.1


@pytest.mark.asyncio
async def test_perspective_injection():
    """High-performing missing perspective gets injected."""
    signals = [{"perspectives": ["practitioner"], "feedback": "accepted", "utilization_rate": 0.7} for _ in range(10)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["theorist"],
                "engagement": {"perspectives": ["theorist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert "practitioner" in result.perspectives
    assert result.perspective_weights["practitioner"] == 0.6


@pytest.mark.asyncio
async def test_below_min_signals_no_adjustment():
    """Fewer than min_signals → no adjustment applied."""
    signals = [{"perspectives": ["theorist"], "feedback": "rejected", "utilization_rate": 0.05} for _ in range(3)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["theorist"],
                "engagement": {"perspectives": ["theorist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.perspective_weights["theorist"] == 1.0
    assert result.adjustments == []


@pytest.mark.asyncio
async def test_engagement_type_adjustment():
    """Adversarial suggested when it has higher acceptance for this discipline."""
    signals_adversarial = [
        {
            "perspectives": ["practitioner", "strategist"],
            "feedback": "accepted",
            "utilization_rate": 0.6,
            "engagement_type": "adversarial",
        }
        for _ in range(8)
    ]
    signals_pipeline = [
        {
            "perspectives": ["practitioner", "strategist"],
            "feedback": "rejected",
            "utilization_rate": 0.3,
            "engagement_type": "pipeline",
        }
        for _ in range(8)
    ]
    with patch(
        "core.engine.orchestration.composition_scorer._query_signals",
        return_value=signals_adversarial + signals_pipeline,
    ):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["practitioner", "strategist"],
                "engagement": {"perspectives": ["practitioner", "strategist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.engagement_type == "adversarial"
    assert any("adversarial" in a.lower() for a in result.adjustments)


@pytest.mark.asyncio
async def test_audit_trail():
    """Adjustments list documents what changed and why."""
    signals = [{"perspectives": ["theorist"], "feedback": "rejected", "utilization_rate": 0.05} for _ in range(10)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["theorist"],
                "engagement": {"perspectives": ["theorist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert len(result.adjustments) > 0
    assert all(isinstance(a, str) for a in result.adjustments)


# ---------------------------------------------------------------------------
# _effective_accepted / _effective_rejected — outcome_confidence proxy
# ---------------------------------------------------------------------------


def test_effective_accepted_explicit_accepted():
    assert _effective_accepted({"feedback": "accepted"}) is True


def test_effective_accepted_explicit_rejected():
    assert _effective_accepted({"feedback": "rejected"}) is False


def test_effective_accepted_proxy_high_confidence():
    """No explicit feedback + high outcome_confidence → treated as accepted."""
    assert _effective_accepted({"outcome_confidence": 0.8}) is True


def test_effective_accepted_proxy_low_confidence():
    """No explicit feedback + low outcome_confidence → not accepted."""
    assert _effective_accepted({"outcome_confidence": 0.3}) is False


def test_effective_accepted_no_data():
    """No feedback or outcome_confidence → returns False."""
    assert _effective_accepted({}) is False


def test_effective_rejected_explicit_rejected():
    assert _effective_rejected({"feedback": "rejected"}) is True


def test_effective_rejected_explicit_accepted():
    assert _effective_rejected({"feedback": "accepted"}) is False


def test_effective_rejected_proxy_low_confidence():
    """No explicit feedback + low outcome_confidence → treated as rejected."""
    assert _effective_rejected({"outcome_confidence": 0.2}) is True


def test_effective_rejected_proxy_high_confidence():
    """No explicit feedback + high outcome_confidence → not rejected."""
    assert _effective_rejected({"outcome_confidence": 0.7}) is False


def test_effective_rejected_no_data():
    assert _effective_rejected({}) is False


# ---------------------------------------------------------------------------
# outcome_confidence penalty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outcome_confidence_penalty_when_no_explicit_feedback():
    """Outcome penalty fires when outcome_confidence is consistently low and no explicit feedback."""
    signals = [{"perspectives": ["theorist"], "outcome_confidence": 0.2, "utilization_rate": 0.5} for _ in range(6)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["theorist"],
                "engagement": {"perspectives": ["theorist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    # outcome_confidence < LOW_OUTCOME_CONFIDENCE with acceptance_rate == 0 → OUTCOME_PENALTY applied
    assert result.perspective_weights["theorist"] < 1.0
    assert any("outcome_confidence" in a for a in result.adjustments)


@pytest.mark.asyncio
async def test_outcome_confidence_penalty_not_applied_when_accepted():
    """Per-perspective outcome penalty does NOT fire when signals are being accepted (acceptance_rate > 0)."""
    # Explicit feedback=accepted → acceptance_rate > 0, so per-perspective outcome penalty is skipped
    signals = [
        {"perspectives": ["theorist"], "outcome_confidence": 0.2, "utilization_rate": 0.5, "feedback": "accepted"}
        for _ in range(6)
    ]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["theorist"],
                "engagement": {"perspectives": ["theorist"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    # Per-perspective penalty line has form "{perspective}: weight * {OUTCOME_PENALTY} (outcome_confidence..."
    # It must NOT appear when acceptance_rate > 0
    assert not any(
        "theorist" in a and f"weight * {OUTCOME_PENALTY}" in a and "outcome_confidence" in a for a in result.adjustments
    )
    # Weight stays at 1.0 — the per-perspective penalty did not fire
    assert result.perspective_weights["theorist"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# routing_uncertain_rate and mean_outcome_confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routing_uncertain_rate_computed():
    """routing_uncertain_rate reflects fraction of signals flagged as uncertain."""
    signals = [
        {"perspectives": ["practitioner"], "routing_uncertain": True, "feedback": "accepted"} for _ in range(3)
    ] + [{"perspectives": ["practitioner"], "routing_uncertain": False, "feedback": "accepted"} for _ in range(3)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["practitioner"],
                "engagement": {"perspectives": ["practitioner"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.routing_uncertain_rate == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_high_uncertain_rate_adds_warning():
    """When routing_uncertain_rate > HIGH_UNCERTAIN_RATE, a warning is added to adjustments."""
    # All signals uncertain → rate = 1.0, well above HIGH_UNCERTAIN_RATE (0.5)
    signals = [{"perspectives": ["practitioner"], "routing_uncertain": True, "feedback": "accepted"} for _ in range(6)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["practitioner"],
                "engagement": {"perspectives": ["practitioner"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.routing_uncertain_rate > HIGH_UNCERTAIN_RATE
    assert any("Warning" in a and "routing may be unreliable" in a for a in result.adjustments)


@pytest.mark.asyncio
async def test_mean_outcome_confidence_returned():
    """mean_outcome_confidence is computed from signals that have the field."""
    signals = [{"perspectives": ["practitioner"], "outcome_confidence": 0.8, "feedback": "accepted"} for _ in range(6)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["practitioner"],
                "engagement": {"perspectives": ["practitioner"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.mean_outcome_confidence == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_mean_outcome_confidence_none_when_absent():
    """When no signals have outcome_confidence, mean_outcome_confidence is None."""
    signals = [{"perspectives": ["practitioner"], "feedback": "accepted"} for _ in range(6)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["practitioner"],
                "engagement": {"perspectives": ["practitioner"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.mean_outcome_confidence is None


@pytest.mark.asyncio
async def test_low_mean_outcome_adds_warning():
    """When mean outcome_confidence < LOW_OUTCOME_CONFIDENCE, a warning adjustment is added."""
    signals = [{"perspectives": ["practitioner"], "outcome_confidence": 0.2, "feedback": "accepted"} for _ in range(6)]
    with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
        result = await score_composition(
            classification={
                "discipline": "security",
                "perspectives": ["practitioner"],
                "engagement": {"perspectives": ["practitioner"]},
                "specialties": [],
                "archetype": "analyst",
                "mode": "reactive",
            },
            product_id="product:default",
        )
    assert result.mean_outcome_confidence is not None
    assert result.mean_outcome_confidence < LOW_OUTCOME_CONFIDENCE
    assert any("mean outcome_confidence" in a for a in result.adjustments)
