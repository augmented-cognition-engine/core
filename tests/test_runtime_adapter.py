"""Tests for model adapters — mock and Claude."""

import pytest

from core.engine.runtime.model_adapter import MockAdapter, ModelAdapter
from core.engine.runtime.models import AssistantMessage, ToolUseBlock


@pytest.mark.asyncio
async def test_mock_adapter_simple_response():
    adapter = MockAdapter(responses=["Hello, world!"])
    messages = []
    async for msg in adapter.call_model(
        system="You are helpful.",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
    ):
        messages.append(msg)
    assert len(messages) == 1
    assert isinstance(messages[0], AssistantMessage)
    assert messages[0].content == "Hello, world!"


@pytest.mark.asyncio
async def test_mock_adapter_tool_use():
    tool_use = ToolUseBlock(id="tu_1", name="bash", input={"command": "ls"})
    adapter = MockAdapter(
        responses=[
            AssistantMessage(content="Let me check.", model="mock", tool_use=[tool_use]),
        ]
    )
    messages = []
    async for msg in adapter.call_model(
        system="You are helpful.",
        messages=[{"role": "user", "content": "list files"}],
        tools=[{"name": "bash", "description": "Run a command", "input_schema": {}}],
    ):
        messages.append(msg)
    assert len(messages) == 1
    assert len(messages[0].tool_use) == 1
    assert messages[0].tool_use[0].name == "bash"


@pytest.mark.asyncio
async def test_mock_adapter_sequential_responses():
    adapter = MockAdapter(responses=["first", "second"])
    r1 = [msg async for msg in adapter.call_model("sys", [{"role": "user", "content": "1"}], [])]
    r2 = [msg async for msg in adapter.call_model("sys", [{"role": "user", "content": "2"}], [])]
    assert r1[0].content == "first"
    assert r2[0].content == "second"


def test_model_adapter_protocol():
    """MockAdapter must satisfy the ModelAdapter protocol."""
    adapter = MockAdapter(responses=["ok"])
    assert isinstance(adapter, ModelAdapter)


@pytest.mark.asyncio
async def test_mock_adapter_stream_model_yields_thinking_delta():
    from core.engine.runtime.events import ThinkingDelta

    adapter = MockAdapter(responses=["hello world"])
    chunks = []
    async for chunk in adapter.stream_model("sys", [], []):
        chunks.append(chunk)

    thinking = [c for c in chunks if isinstance(c, ThinkingDelta)]
    text = [c for c in chunks if isinstance(c, str)]
    final = [c for c in chunks if isinstance(c, AssistantMessage)]

    assert len(thinking) >= 1
    assert len(text) >= 1
    assert len(final) == 1
    assert final[0].content == "hello world"


def test_model_adapter_protocol_has_stream_model():
    from core.engine.runtime.model_adapter import ModelAdapter

    # Protocol should declare stream_model
    assert "stream_model" in dir(ModelAdapter)
