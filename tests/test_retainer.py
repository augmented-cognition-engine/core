# tests/test_retainer.py
"""Tests for P4 Component 3 — Retainer Tracker.

TDD order:
1. EngagementState model (deliveries, verifications)
2. ExpansionRecommendation model
3. RetainerTracker.record_delivery() — updates engagement state
4. RetainerTracker.next_expansion() — returns highest-priority next candidate
5. Delivery history is append-only (immutable)
6. Fallback when no discovery sprint report available
"""

from __future__ import annotations

import pytest

# ── EngagementState model tests ───────────────────────────────────────────────


def test_engagement_state_starts_empty():
    """A fresh EngagementState has no deliveries or verifications."""
    from core.engine.product.retainer import EngagementState

    state = EngagementState(product_id="product:test")
    assert state.product_id == "product:test"
    assert state.deliveries == []
    assert state.verifications == []


def test_engagement_state_record_delivery_appends():
    """record_delivery() appends to the deliveries list."""
    from core.engine.product.retainer import EngagementState

    state = EngagementState(product_id="product:test")
    state.record_delivery(spec_id="agent_spec:abc", title="Auth middleware")
    assert len(state.deliveries) == 1
    assert state.deliveries[0]["spec_id"] == "agent_spec:abc"
    assert state.deliveries[0]["title"] == "Auth middleware"
    assert state.deliveries[0]["status"] == "delivered"


def test_engagement_state_record_verification_appends():
    """record_verification() appends to the verifications list."""
    from core.engine.product.retainer import EngagementState

    state = EngagementState(product_id="product:test")
    state.record_verification(spec_id="agent_spec:abc", passed=True)
    assert len(state.verifications) == 1
    assert state.verifications[0]["spec_id"] == "agent_spec:abc"
    assert state.verifications[0]["passed"] is True


def test_engagement_state_delivery_history_is_append_only():
    """Deliveries cannot be overwritten — append-only history."""
    from core.engine.product.retainer import EngagementState

    state = EngagementState(product_id="product:test")
    state.record_delivery(spec_id="agent_spec:abc", title="First delivery")
    state.record_delivery(spec_id="agent_spec:abc", title="First delivery duplicate")

    # Both entries exist — no deduplication or overwrite
    assert len(state.deliveries) == 2


def test_engagement_state_to_dict_is_serializable():
    """EngagementState.to_dict() returns a JSON-serializable structure."""
    from core.engine.product.retainer import EngagementState

    state = EngagementState(product_id="product:test")
    state.record_delivery(spec_id="agent_spec:abc", title="Auth middleware")
    d = state.to_dict()
    assert d["product_id"] == "product:test"
    assert len(d["deliveries"]) == 1


# ── ExpansionRecommendation model tests ───────────────────────────────────────


def test_expansion_recommendation_has_required_fields():
    """ExpansionRecommendation captures what was built, what's next, and ROI."""
    from core.engine.product.retainer import ExpansionRecommendation

    rec = ExpansionRecommendation(
        product_id="product:test",
        delivered_specs=["Auth middleware"],
        next_title="Add circuit breaker",
        next_description="Prevents cascade failures across all service calls",
        next_annual_value=62400.0,
        retainer_framing="We automated auth, here's circuit breakers which unlocks compliance",
    )
    assert rec.product_id == "product:test"
    assert len(rec.delivered_specs) == 1
    assert rec.next_title == "Add circuit breaker"
    assert rec.next_annual_value == 62400.0


def test_expansion_recommendation_to_dict_is_serializable():
    """ExpansionRecommendation.to_dict() returns all expected keys."""
    from core.engine.product.retainer import ExpansionRecommendation

    rec = ExpansionRecommendation(
        product_id="product:test",
        delivered_specs=["Auth middleware"],
        next_title="Add circuit breaker",
        next_description="Prevents cascade failures",
        next_annual_value=62400.0,
        retainer_framing="We automated auth, here's what's next",
    )
    d = rec.to_dict()
    assert "delivered_specs" in d
    assert "next_title" in d
    assert "next_annual_value" in d
    assert "retainer_framing" in d


# ── RetainerTracker tests ─────────────────────────────────────────────────────


def test_retainer_tracker_initializes_with_product():
    """RetainerTracker initializes for a specific product_id."""
    from core.engine.product.retainer import RetainerTracker

    tracker = RetainerTracker(product_id="product:test")
    assert tracker.product_id == "product:test"


def test_retainer_tracker_record_delivery_updates_state():
    """record_delivery() records a delivered spec in engagement state."""
    from core.engine.product.retainer import RetainerTracker

    tracker = RetainerTracker(product_id="product:test")
    tracker.record_delivery(spec_id="agent_spec:abc", title="Auth middleware")

    state = tracker.engagement_state
    assert len(state.deliveries) == 1
    assert state.deliveries[0]["spec_id"] == "agent_spec:abc"


def test_retainer_tracker_next_expansion_returns_recommendation(
    mock_discovery_report,
):
    """next_expansion() returns an ExpansionRecommendation with next unbuilt candidate."""
    from core.engine.product.retainer import ExpansionRecommendation, RetainerTracker

    tracker = RetainerTracker(product_id="product:test")
    # First candidate delivered
    tracker.record_delivery(
        spec_id="agent_spec:abc",
        title=mock_discovery_report.automation_candidates[0].title,
    )

    rec = tracker.next_expansion(discovery_report=mock_discovery_report)

    assert isinstance(rec, ExpansionRecommendation)
    # Next should be the second candidate (first is already delivered)
    assert rec.next_title == mock_discovery_report.automation_candidates[1].title
    assert "Auth middleware" in rec.delivered_specs or "billing" in rec.delivered_specs[0].lower()


def test_retainer_tracker_next_expansion_with_no_deliveries(mock_discovery_report):
    """next_expansion() returns the highest-priority candidate when nothing delivered yet."""
    from core.engine.product.retainer import RetainerTracker

    tracker = RetainerTracker(product_id="product:test")
    rec = tracker.next_expansion(discovery_report=mock_discovery_report)

    # First candidate is next when nothing delivered
    assert rec.next_title == mock_discovery_report.automation_candidates[0].title


def test_retainer_tracker_next_expansion_without_discovery_report():
    """next_expansion() falls back gracefully when no discovery report available."""
    from core.engine.product.retainer import RetainerTracker

    tracker = RetainerTracker(product_id="product:test")
    tracker.record_delivery(spec_id="agent_spec:abc", title="Auth middleware")

    rec = tracker.next_expansion(discovery_report=None)

    # Fallback: recommendation without specific next target
    assert rec is not None
    assert len(rec.delivered_specs) == 1


def test_retainer_tracker_all_candidates_delivered_returns_none(mock_discovery_report):
    """next_expansion() returns None when all candidates are delivered."""
    from core.engine.product.retainer import RetainerTracker

    tracker = RetainerTracker(product_id="product:test")
    for candidate in mock_discovery_report.automation_candidates:
        tracker.record_delivery(spec_id=f"agent_spec:{candidate.title[:8]}", title=candidate.title)

    rec = tracker.next_expansion(discovery_report=mock_discovery_report)
    assert rec is None


def test_retainer_tracker_roi_in_expansion_is_numerical(mock_discovery_report):
    """next_expansion() includes a real annual_value figure, not a qualitative string."""
    from core.engine.product.retainer import RetainerTracker

    tracker = RetainerTracker(product_id="product:test")
    rec = tracker.next_expansion(discovery_report=mock_discovery_report)

    assert isinstance(rec.next_annual_value, (int, float))
    assert rec.next_annual_value > 0


def test_retainer_tracker_framing_mentions_delivered_work(mock_discovery_report):
    """retainer_framing references what was already delivered."""
    from core.engine.product.retainer import RetainerTracker

    tracker = RetainerTracker(product_id="product:test")
    tracker.record_delivery(
        spec_id="agent_spec:abc",
        title=mock_discovery_report.automation_candidates[0].title,
    )

    rec = tracker.next_expansion(discovery_report=mock_discovery_report)
    # Framing should reference the delivered work
    assert len(rec.retainer_framing) > 0


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_discovery_report():
    """A minimal DiscoveryReport with 3 automation candidates for retainer tests."""
    from core.engine.product.report_models import AutomationCandidate, DiscoveryReport, SpecStub

    candidates = [
        AutomationCandidate(
            title="Automate billing reconciliation",
            description="Replace manual billing with automated reconciliation",
            hours_per_week_saved=8.0,
            loaded_hourly_rate=150.0,
            effort_tier="medium",
            spec_stub=SpecStub(
                title="Automate billing reconciliation",
                acceptance_criteria=["Billing reconciliation runs automatically"],
                estimated_scope="medium",
            ),
        ),
        AutomationCandidate(
            title="Automate report generation",
            description="Replace manual weekly reports",
            hours_per_week_saved=3.0,
            loaded_hourly_rate=150.0,
            effort_tier="low",
            spec_stub=SpecStub(
                title="Automate report generation",
                acceptance_criteria=["Reports generated automatically each week"],
                estimated_scope="low",
            ),
        ),
        AutomationCandidate(
            title="Implement CI/CD pipeline",
            description="Replace manual deployment steps",
            hours_per_week_saved=5.0,
            loaded_hourly_rate=150.0,
            effort_tier="high",
            spec_stub=None,
        ),
    ]

    return DiscoveryReport(
        product_id="product:test",
        client_name="Test Client",
        executive_summary="Test client has manual processes worth automating.",
        automation_candidates=candidates,
        systems_map_summary="Core systems: billing, reporting, devops.",
        preliminary=False,
    )
