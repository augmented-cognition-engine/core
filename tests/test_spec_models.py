import pytest

from core.engine.product.spec_models import (
    AcceptanceCriterion,
    AgentFeedbackCreate,
    AgentSpecCreate,
    VerificationResult,
)


def test_agent_spec_create_valid():
    spec = AgentSpecCreate(
        objective="Add rate limiting to API endpoints",
        source="gap",
        acceptance_criteria=[
            AcceptanceCriterion(criterion="Returns 429 after 100 req/min", verification="curl test", automated=True),
        ],
        constraints=["Do not modify auth middleware signature"],
        estimated_files=["core/engine/api/main.py"],
    )
    assert spec.source == "gap"
    assert len(spec.acceptance_criteria) == 1


def test_agent_spec_create_empty_criteria_rejected():
    with pytest.raises(ValueError):
        AgentSpecCreate(
            objective="Do something",
            source="human",
            acceptance_criteria=[],
        )


def test_agent_feedback_valid():
    fb = AgentFeedbackCreate(
        spec_id="agent_spec:123",
        feedback_type="blocker",
        content="Stripe SDK conflicts with HTTP client",
        context={"attempted": "pip install stripe", "error": "version conflict"},
    )
    assert fb.feedback_type == "blocker"


def test_verification_result():
    vr = VerificationResult(
        spec_id="agent_spec:123",
        overall="partially_met",
        criteria_results=[
            {"criterion": "Returns 429", "status": "met", "evidence": "test passes"},
            {"criterion": "Existing tests pass", "status": "not_met", "evidence": "2 failures"},
        ],
        follow_up_needed=True,
    )
    assert vr.follow_up_needed is True
    assert len(vr.criteria_results) == 2
