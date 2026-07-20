"""Tests for streaming model adapter."""

from __future__ import annotations

import pytest

from core.engine.runtime.model_adapter import MockAdapter
from core.engine.runtime.models import AssistantMessage


@pytest.mark.asyncio
async def test_mock_stream():
    adapter = MockAdapter(responses=["Hello world"])
    chunks = []
    final = None
    async for item in adapter.stream_model("sys", [{"role": "user", "content": "hi"}], []):
        if isinstance(item, str):
            chunks.append(item)
        elif isinstance(item, AssistantMessage):
            final = item
    assert len(chunks) >= 1
    assert final is not None
    assert final.content == "Hello world"


@pytest.mark.asyncio
async def test_mock_stream_tool_use():
    from core.engine.runtime.models import ToolUseBlock

    tu = ToolUseBlock(id="tu_1", name="bash", input={"command": "ls"})
    msg = AssistantMessage(content="Let me check.", model="mock", tool_use=[tu])
    adapter = MockAdapter(responses=[msg])
    chunks = []
    final = None
    async for item in adapter.stream_model("sys", [{"role": "user", "content": "list files"}], []):
        if isinstance(item, str):
            chunks.append(item)
        elif isinstance(item, AssistantMessage):
            final = item
    assert final is not None
    assert len(final.tool_use) == 1


@pytest.mark.asyncio
async def test_mock_stream_empty_queue():
    adapter = MockAdapter(responses=[])
    chunks = []
    final = None
    async for item in adapter.stream_model("sys", [{"role": "user", "content": "hi"}], []):
        if isinstance(item, str):
            chunks.append(item)
        elif isinstance(item, AssistantMessage):
            final = item
    assert final is not None
    assert "No more" in final.content


@pytest.mark.asyncio
async def test_mock_stream_yields_words():
    """String responses should be streamed word by word."""
    adapter = MockAdapter(responses=["one two three"])
    chunks = []
    async for item in adapter.stream_model("sys", [], []):
        if isinstance(item, str):
            chunks.append(item)
    # Should have 3 word chunks
    assert len(chunks) == 3
    assert "".join(chunks).strip() == "one two three"
