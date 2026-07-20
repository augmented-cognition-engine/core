"""Test that new event constants exist and are registered in ALL_EVENT_TYPES."""

from core.engine.canvas.event_protocol import (
    ALL_EVENT_TYPES,
    EVENT_AGENT_ACTIVITY_PLACED,
    EVENT_DECISION_PREDICTION_ATTACHED,
    EVENT_LAYER5_CONTEXT_LOADED,
    EVENT_PREDICTION_OUTCOME_CLOSED,
    AgentActivityPlacedPayload,
    DecisionPredictionAttachedPayload,
    Layer5ContextLoadedPayload,
    PredictionOutcomeClosedPayload,
)


def test_new_event_constants_defined():
    assert EVENT_AGENT_ACTIVITY_PLACED == "agent.activity.placed"
    assert EVENT_DECISION_PREDICTION_ATTACHED == "decision.prediction.attached"
    assert EVENT_PREDICTION_OUTCOME_CLOSED == "prediction.outcome.closed"


def test_new_events_registered_in_all_event_types():
    assert EVENT_AGENT_ACTIVITY_PLACED in ALL_EVENT_TYPES
    assert EVENT_DECISION_PREDICTION_ATTACHED in ALL_EVENT_TYPES
    assert EVENT_PREDICTION_OUTCOME_CLOSED in ALL_EVENT_TYPES


def test_agent_activity_payload_validates():
    p = AgentActivityPlacedPayload(
        agent_id="pm",
        archetype="PM",
        shape_id="shape:abc",
        action="placed",
        rationale="proposed JWT",
    )
    assert p.shape_id == "shape:abc"
    p2 = AgentActivityPlacedPayload(agent_id="pm", archetype="PM", action="placed", rationale="...")
    assert p2.shape_id is None


def test_prediction_attached_payload_validates():
    p = DecisionPredictionAttachedPayload(
        decision_id="decision:t",
        prediction_id="decision_prediction:t",
        agent_id="pm",
        predicted_delta=0.12,
        falsifier="no auth events in 14 days",
        horizon_days=14,
    )
    assert p.horizon_days == 14


def test_prediction_closed_payload_validates():
    p = PredictionOutcomeClosedPayload(
        prediction_id="decision_prediction:t",
        agent_id="skeptic",
        archetype="Skeptic",
        predicted=0.10,
        actual=0.08,
        calibration_score=0.80,
        weight_delta=0.06,
        discipline="security",
    )
    assert p.weight_delta > 0


def test_layer5_context_loaded_constant():
    assert EVENT_LAYER5_CONTEXT_LOADED == "layer5.context_loaded"
    assert EVENT_LAYER5_CONTEXT_LOADED in ALL_EVENT_TYPES


def test_layer5_context_loaded_payload_validates():
    """Full payload — all fields including degraded tiers + contradictions count."""
    p = Layer5ContextLoadedPayload(
        decision_count=5,
        capability_count=2,
        discipline_count=2,
        recency_count=1,
        degraded_tiers=["recency"],
        contradictions_count=1,
        elapsed_ms=42.5,
    )
    assert p.decision_count == 5
    assert p.degraded_tiers == ["recency"]
    assert p.contradictions_count == 1


def test_layer5_payload_defaults_for_clean_load():
    """Cold-start clean case: only counts required, degraded/contradictions optional."""
    p = Layer5ContextLoadedPayload(
        decision_count=3,
        capability_count=1,
        discipline_count=1,
        recency_count=1,
    )
    assert p.degraded_tiers == []
    assert p.contradictions_count == 0
    assert p.elapsed_ms == 0.0
