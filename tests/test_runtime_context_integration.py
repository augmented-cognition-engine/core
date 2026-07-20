"""Tests for context management integration."""

import pytest

from core.engine.runtime import Runtime
from core.engine.runtime.model_adapter import MockAdapter
from core.engine.runtime.models import AssistantMessage


@pytest.mark.asyncio
async def test_runtime_tracks_tokens():
    runtime = Runtime(adapter=MockAdapter(responses=["Hello!"]), enable_intelligence=False)
    _ = [msg async for msg in runtime.chat("hi")]
    assert runtime.token_tracker is not None
    assert runtime.token_tracker.turn_count >= 0


@pytest.mark.asyncio
async def test_runtime_context_manager_exists():
    runtime = Runtime(adapter=MockAdapter(responses=["ok"]), enable_intelligence=False)
    assert runtime.context_manager is not None


@pytest.mark.asyncio
async def test_backward_compat_no_intelligence():
    runtime = Runtime(adapter=MockAdapter(responses=["Hello!"]), enable_intelligence=False)
    messages = [msg async for msg in runtime.chat("hi")]
    assistants = [m for m in messages if isinstance(m, AssistantMessage)]
    assert len(assistants) == 1
