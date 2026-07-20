"""End-to-end tests for the Runtime SDK."""

import pytest

from core.engine.runtime import Runtime
from core.engine.runtime.model_adapter import MockAdapter
from core.engine.runtime.models import AssistantMessage, ToolUseBlock


@pytest.mark.asyncio
async def test_runtime_simple_chat():
    runtime = Runtime(adapter=MockAdapter(responses=["Hello from ACE!"]), enable_intelligence=False)
    messages = [msg async for msg in runtime.chat("hi")]
    assistants = [m for m in messages if isinstance(m, AssistantMessage)]
    assert len(assistants) == 1
    assert assistants[0].content == "Hello from ACE!"


@pytest.mark.asyncio
async def test_runtime_multi_turn():
    runtime = Runtime(adapter=MockAdapter(responses=["First.", "Second."]), enable_intelligence=False)
    r1 = [msg async for msg in runtime.chat("one")]
    r2 = [msg async for msg in runtime.chat("two")]
    a1 = [m for m in r1 if isinstance(m, AssistantMessage)]
    a2 = [m for m in r2 if isinstance(m, AssistantMessage)]
    assert a1[0].content == "First."
    assert a2[0].content == "Second."


@pytest.mark.asyncio
async def test_runtime_tool_execution():
    tool_use = ToolUseBlock(id="tu_1", name="bash", input={"command": "echo works"})
    runtime = Runtime(
        adapter=MockAdapter(
            responses=[
                AssistantMessage(content="Running command.", model="mock", tool_use=[tool_use]),
                "Command succeeded.",
            ]
        ),
        enable_intelligence=False,
    )
    messages = [msg async for msg in runtime.chat("run echo")]
    types = [type(m).__name__ for m in messages]
    assert "AssistantMessage" in types
    assert "ToolResultMessage" in types


@pytest.mark.asyncio
async def test_runtime_message_history_persists():
    runtime = Runtime(adapter=MockAdapter(responses=["First.", "Second."]), enable_intelligence=False)
    _ = [msg async for msg in runtime.chat("one")]
    _ = [msg async for msg in runtime.chat("two")]
    assert len(runtime.messages) >= 4


@pytest.mark.asyncio
async def test_runtime_default_tools_registered():
    runtime = Runtime(adapter=MockAdapter(responses=["ok"]), enable_intelligence=False)
    tool_names = runtime.tool_names
    assert "bash" in tool_names
    assert "read" in tool_names
    assert "write" in tool_names
    assert "edit" in tool_names
    assert "grep" in tool_names
    assert "glob" in tool_names
