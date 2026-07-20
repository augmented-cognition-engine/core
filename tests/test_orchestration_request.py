# tests/test_orchestration_request.py
"""Unit tests for OrchestrationRequest constructors and defaults."""

from core.engine.orchestration.agent import AgentConfig
from core.engine.orchestration.request import OrchestrationRequest


def test_from_chat():
    req = OrchestrationRequest.from_chat(
        session_id="sess1",
        message="hello",
        product_id="product:test",
        workspace_id="ws:default",
        user_id="user:1",
    )
    assert req.source == "chat"
    assert req.persist_task is False
    assert req.stream_tokens is True
    assert req.description == "hello"


def test_from_runner():
    req = OrchestrationRequest.from_runner(
        queue_item={"description": "do the thing"},
        product_id="product:test",
    )
    assert req.source == "runner"
    assert req.user_id == "user:runner"
    assert req.description == "do the thing"


def test_from_evolution():
    req = OrchestrationRequest.from_evolution(
        system_prompt="You are...",
        task_prompt="Research X",
        pattern="fanout",
        product_id="product:test",
    )
    assert req.source == "evolution"
    assert req.pattern == "fanout"
    assert req.persist_task is False
    assert req.persist_events is True
    assert req.run_post_hooks is False
    assert req.use_agent_sdk is True


def test_default_values():
    req = OrchestrationRequest(
        description="test",
        product_id="product:test",
        workspace_id="ws:default",
        user_id="user:1",
    )
    assert req.source == "direct"
    assert req.persist_task is True
    assert req.stream_tokens is False
    assert req.pattern is None


def test_from_runner_workspace_default():
    """Runner source defaults to workspace:default."""
    req = OrchestrationRequest.from_runner(
        queue_item={"description": "task"},
        product_id="product:test",
    )
    assert req.workspace_id == "workspace:default"


def test_from_evolution_classification_override():
    """Evolution source sets classification_override."""
    req = OrchestrationRequest.from_evolution(
        system_prompt="You are...",
        task_prompt="Research X",
        pattern="adversarial",
        product_id="product:test",
    )
    assert req.classification_override is not None
    assert req.classification_override["mode"] == "reflective"
    assert req.classification_override["complexity"] == "complex"


def test_from_chat_with_conversation_messages():
    """Chat source can carry conversation history."""
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    req = OrchestrationRequest.from_chat(
        session_id="sess1",
        message="what next?",
        product_id="product:test",
        workspace_id="ws:default",
        user_id="user:1",
        conversation_messages=messages,
    )
    assert req.conversation_messages is not None
    assert len(req.conversation_messages) == 2


def test_agent_configs_override():
    """agent_configs can be passed directly."""
    configs = [AgentConfig(role="researcher"), AgentConfig(role="writer")]
    req = OrchestrationRequest(
        description="test",
        product_id="product:test",
        workspace_id="ws:default",
        user_id="user:1",
        agent_configs=configs,
    )
    assert req.agent_configs is not None
    assert len(req.agent_configs) == 2
    assert req.agent_configs[0].role == "researcher"


def test_force_skill_and_frameworks():
    """force_skill and force_frameworks fields work."""
    req = OrchestrationRequest(
        description="test",
        product_id="product:test",
        workspace_id="ws:default",
        user_id="user:1",
        force_skill="code_review",
        force_frameworks=True,
        frameworks_hint=["pytest"],
    )
    assert req.force_skill == "code_review"
    assert req.force_frameworks is True
    assert req.frameworks_hint == ["pytest"]
