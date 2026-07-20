"""Tests for runtime message types and state models."""

from core.engine.runtime.models import (
    AssistantMessage,
    RuntimeConfig,
    SystemMessage,
    ToolResultMessage,
    ToolUseBlock,
    Transition,
    TurnState,
    UserMessage,
)


def test_user_message_creation():
    msg = UserMessage(content="hello")
    assert msg.type == "user"
    assert msg.content == "hello"


def test_assistant_message_creation():
    msg = AssistantMessage(content="hi there", model="claude-sonnet-4-6")
    assert msg.type == "assistant"
    assert msg.content == "hi there"
    assert msg.model == "claude-sonnet-4-6"


def test_assistant_message_with_tool_use():
    tool_use = ToolUseBlock(id="tu_1", name="bash", input={"command": "ls"})
    msg = AssistantMessage(content="Let me check.", model="claude-sonnet-4-6", tool_use=[tool_use])
    assert len(msg.tool_use) == 1
    assert msg.tool_use[0].name == "bash"


def test_tool_result_message():
    msg = ToolResultMessage(tool_use_id="tu_1", content="file1.py\nfile2.py", is_error=False)
    assert msg.type == "tool_result"
    assert not msg.is_error


def test_system_message():
    msg = SystemMessage(content="compacted", subtype="compact_boundary")
    assert msg.type == "system"


def test_message_union_discriminates():
    user = UserMessage(content="hello")
    assistant = AssistantMessage(content="hi", model="test")
    assert isinstance(user, UserMessage)
    assert isinstance(assistant, AssistantMessage)


def test_turn_state_defaults():
    state = TurnState()
    assert state.turn_count == 1
    assert state.transition is None
    assert state.messages == []


def test_runtime_config():
    config = RuntimeConfig(model="claude-sonnet-4-6", product_id="product:platform")
    assert config.model == "claude-sonnet-4-6"
    assert config.max_turns == 100


def test_transition_enum():
    assert Transition.NEXT_TURN == "next_turn"
    assert Transition.COMPLETED == "completed"


def test_thinking_delta_import_and_fields():
    from core.engine.runtime.events import ThinkingDelta

    td = ThinkingDelta(content="let me think...")
    assert td.content == "let me think..."


def test_system_message_compaction_fields():
    from core.engine.runtime.models import SystemMessage

    msg = SystemMessage(content="compacted", subtype="compaction", before_tokens=18000, after_tokens=4000)
    assert msg.before_tokens == 18000
    assert msg.after_tokens == 4000
    assert msg.subtype == "compaction"


def test_intelligence_loaded_message():
    from core.engine.runtime.models import IntelligenceLoadedMessage

    msg = IntelligenceLoadedMessage(entries=[("testing", 3), ("security", 1)])
    assert msg.entries == [("testing", 3), ("security", 1)]
    assert msg.type == "intelligence_loaded"
    # Verify it's part of the Message union
    assert isinstance(msg, IntelligenceLoadedMessage)
