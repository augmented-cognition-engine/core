# tests/test_orchestration_dispatcher.py
"""Unit tests for mode + pattern dispatch logic."""

from core.engine.orchestration.agent import AgentConfig
from core.engine.orchestration.dispatcher import dispatch
from core.engine.orchestration.request import OrchestrationRequest


def _make_request(**kwargs):
    defaults = {
        "description": "test",
        "product_id": "product:test",
        "workspace_id": "ws:default",
        "user_id": "user:1",
    }
    defaults.update(kwargs)
    return OrchestrationRequest(**defaults)


def test_explicit_pattern_override():
    req = _make_request(pattern="adversarial")
    decision = dispatch(req, {"complexity": "simple"})
    assert decision.pattern == "adversarial"


def test_chat_simple_is_reactive_independent():
    req = _make_request(source="chat")
    decision = dispatch(req, {"complexity": "simple"})
    assert decision.mode == "reactive"
    assert decision.pattern == "independent"


def test_chat_moderate_is_reactive_independent():
    """Chat source + moderate complexity still gets reactive independent."""
    req = _make_request(source="chat")
    decision = dispatch(req, {"complexity": "moderate"})
    assert decision.mode == "reactive"
    assert decision.pattern == "independent"


def test_forced_skill_is_pipeline():
    req = _make_request(force_skill="code_review")
    decision = dispatch(req, {"complexity": "moderate"})
    assert decision.pattern == "pipeline"


def test_multiple_agents_with_evaluator_is_adversarial():
    req = _make_request(
        agent_configs=[
            AgentConfig(role="generator"),
            AgentConfig(role="evaluator"),
        ],
    )
    decision = dispatch(req, {"complexity": "moderate"})
    assert decision.pattern == "adversarial"


def test_multiple_agents_with_critic_is_adversarial():
    """Critic role also triggers adversarial."""
    req = _make_request(
        agent_configs=[
            AgentConfig(role="generator"),
            AgentConfig(role="critic"),
        ],
    )
    decision = dispatch(req, {"complexity": "moderate"})
    assert decision.pattern == "adversarial"


def test_multiple_same_role_is_fanout():
    req = _make_request(
        agent_configs=[
            AgentConfig(role="researcher"),
            AgentConfig(role="researcher"),
        ],
    )
    decision = dispatch(req, {"complexity": "moderate"})
    assert decision.pattern == "fanout"


def test_multiple_different_roles_is_pipeline():
    """Multiple agents with different (non-evaluator/critic) roles → pipeline."""
    req = _make_request(
        agent_configs=[
            AgentConfig(role="researcher"),
            AgentConfig(role="writer"),
        ],
    )
    decision = dispatch(req, {"complexity": "moderate"})
    assert decision.pattern == "pipeline"
    assert decision.mode == "deliberative"


def test_complex_task_is_deliberative():
    req = _make_request()
    decision = dispatch(req, {"complexity": "complex"})
    assert decision.mode == "deliberative"
    assert decision.pattern == "pipeline"


def test_simple_default_is_reactive_independent():
    req = _make_request()
    decision = dispatch(req, {"complexity": "simple"})
    assert decision.mode == "reactive"
    assert decision.pattern == "independent"


def test_explicit_pattern_complex_is_deliberative():
    """Explicit pattern + complex classification → deliberative mode."""
    req = _make_request(pattern="fanout")
    decision = dispatch(req, {"complexity": "complex"})
    assert decision.mode == "deliberative"
    assert decision.pattern == "fanout"


def test_explicit_pattern_simple_is_reactive():
    """Explicit pattern + simple classification → reactive mode."""
    req = _make_request(pattern="team")
    decision = dispatch(req, {"complexity": "simple"})
    assert decision.mode == "reactive"
    assert decision.pattern == "team"


def test_dispatch_decision_has_reasoning():
    """Every dispatch decision includes a reasoning string."""
    req = _make_request()
    decision = dispatch(req, {"complexity": "simple"})
    assert isinstance(decision.reasoning, str)
    assert len(decision.reasoning) > 0


def test_missing_complexity_defaults_to_simple():
    """Missing complexity in classification defaults to simple behavior."""
    req = _make_request()
    decision = dispatch(req, {})
    assert decision.mode == "reactive"
    assert decision.pattern == "independent"
