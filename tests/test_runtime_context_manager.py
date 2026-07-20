# tests/test_runtime_context_manager.py
"""Tests for graph-backed context rotation."""

from core.engine.runtime.context_manager import ContextManager
from core.engine.runtime.models import (
    AssistantMessage,
    ToolResultMessage,
    ToolUseBlock,
    UserMessage,
)
from core.engine.runtime.session_memory import SessionMemory


def _make_conversation(n_turns: int = 5) -> list:
    """Build a synthetic conversation with tool results."""
    messages = []
    for i in range(n_turns):
        messages.append(UserMessage(content=f"User message {i}"))
        tu = ToolUseBlock(id=f"tu_{i}", name="bash", input={"command": f"echo {i}"})
        messages.append(
            AssistantMessage(
                content=f"Let me run command {i}",
                model="mock",
                tool_use=[tu],
            )
        )
        messages.append(
            ToolResultMessage(
                tool_use_id=f"tu_{i}",
                content=f"Output from command {i}\n" + ("x" * 500),
                is_error=False,
            )
        )
        messages.append(AssistantMessage(content=f"Command {i} succeeded.", model="mock"))
    return messages


def test_microcompact_clears_old_tool_results():
    mgr = ContextManager()
    messages = _make_conversation(5)
    result = mgr.microcompact(messages, keep_recent=2)
    cleared = [m for m in result if isinstance(m, ToolResultMessage) and "[Cleared]" in m.content]
    kept = [m for m in result if isinstance(m, ToolResultMessage) and "[Cleared]" not in m.content]
    assert len(cleared) == 3
    assert len(kept) == 2


def test_microcompact_preserves_recent():
    mgr = ContextManager()
    messages = _make_conversation(3)
    result = mgr.microcompact(messages, keep_recent=3)
    cleared = [m for m in result if isinstance(m, ToolResultMessage) and "[Cleared]" in m.content]
    assert len(cleared) == 0


def test_drop_and_reload_shortens():
    mgr = ContextManager()
    messages = _make_conversation(10)
    memory = SessionMemory()
    memory.update_section("current_state", "Working on auth refactor")
    result = mgr.drop_and_reload(
        messages,
        session_memory=memory,
        keep_recent_exchanges=3,
    )
    assert len(result) < len(messages)


def test_drop_and_reload_includes_session_memory():
    mgr = ContextManager()
    messages = _make_conversation(10)
    memory = SessionMemory()
    memory.update_section("current_state", "Fixing SQL injection in login.py")
    result = mgr.drop_and_reload(
        messages,
        session_memory=memory,
        keep_recent_exchanges=3,
    )
    # The reload message should contain session memory
    has_session = any(isinstance(m, UserMessage) and "SQL injection" in m.content for m in result)
    assert has_session


def test_drop_and_reload_includes_dropped_summary():
    mgr = ContextManager()
    messages = _make_conversation(10)
    result = mgr.drop_and_reload(messages, keep_recent_exchanges=3)
    # Should mention what was dropped
    has_dropped = any(isinstance(m, UserMessage) and "dropped" in m.content.lower() for m in result)
    assert has_dropped


def test_drop_and_reload_preserves_recent():
    mgr = ContextManager()
    messages = _make_conversation(10)
    result = mgr.drop_and_reload(messages, keep_recent_exchanges=3)
    # Last user message should still be present
    user_msgs = [m for m in result if isinstance(m, UserMessage) and not m.is_meta]
    assert any("User message 9" in m.content for m in user_msgs)


def test_drop_and_reload_skips_when_few_messages():
    mgr = ContextManager()
    messages = _make_conversation(3)
    result = mgr.drop_and_reload(messages, keep_recent_exchanges=5)
    assert result == messages  # not enough to drop


def test_emergency_compact():
    mgr = ContextManager()
    messages = _make_conversation(10)
    memory = SessionMemory()
    memory.update_section("current_state", "Emergency state")
    result = mgr.emergency_compact(messages, memory, keep_recent=2)
    assert len(result) < len(messages)
    has_emergency = any(isinstance(m, UserMessage) and "emergency" in m.content.lower() for m in result)
    assert has_emergency


def test_compaction_circuit_breaker():
    mgr = ContextManager()
    mgr._consecutive_failures = 3
    messages = _make_conversation(5)
    result = mgr.compact(messages)
    assert result == messages


def test_compaction_count():
    mgr = ContextManager()
    assert mgr.compaction_count == 0
    messages = _make_conversation(5)
    mgr.compact(messages)
    assert mgr.compaction_count == 1


def test_full_compact_pipeline():
    """Full pipeline: microcompact → drop+reload → result is shorter."""
    mgr = ContextManager()
    messages = _make_conversation(15)  # lots of messages
    memory = SessionMemory()
    memory.update_section("current_state", "Working on feature X")
    result = mgr.compact(
        messages,
        session_memory=memory,
        current_query="feature X",
    )
    assert len(result) < len(messages)
    assert mgr.compaction_count == 1
