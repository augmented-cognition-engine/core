"""Tests that all modules are wired into the runtime."""

import pytest

from core.engine.runtime import Runtime
from core.engine.runtime.model_adapter import MockAdapter
from core.engine.runtime.models import AssistantMessage, ToolUseBlock


@pytest.mark.asyncio
async def test_safety_limits_accessible():
    runtime = Runtime(adapter=MockAdapter(responses=["ok"]), enable_intelligence=False)
    assert runtime.safety is not None
    assert runtime.safety.max_turns == 100


@pytest.mark.asyncio
async def test_progress_tracker_records():
    tu = ToolUseBlock(id="tu_1", name="bash", input={"command": "echo hi"})
    runtime = Runtime(
        adapter=MockAdapter(
            responses=[
                AssistantMessage(content="Running.", model="mock", tool_use=[tu]),
                "Done.",
            ]
        ),
        enable_intelligence=False,
    )
    _ = [msg async for msg in runtime.chat("run something")]
    # Progress should have recorded the tool
    assert runtime.progress.tool_summary() != ""


@pytest.mark.asyncio
async def test_prompt_cache_tracked():
    runtime = Runtime(adapter=MockAdapter(responses=["ok"]), enable_intelligence=False)
    _ = [msg async for msg in runtime.chat("hi")]
    assert runtime.prompt_cache.prompt_hash is not None


@pytest.mark.asyncio
async def test_verification_nudge_counts():
    runtime = Runtime(adapter=MockAdapter(responses=["done1", "done2", "done3"]), enable_intelligence=False)
    for i in range(3):
        _ = [msg async for msg in runtime.chat(f"task {i}")]
    assert runtime.verification_nudge.should_nudge()


@pytest.mark.asyncio
async def test_get_adapter_used():
    """Runtime without explicit adapter should use get_adapter."""
    # This just verifies the import path works — actual API calls need keys
    from core.engine.runtime.adapters import get_adapter

    adapter = get_adapter("gpt-4o")
    assert adapter is not None


@pytest.mark.asyncio
async def test_error_recovery_accessible():
    runtime = Runtime(adapter=MockAdapter(responses=["ok"]), enable_intelligence=False)
    assert runtime._error_recovery is not None
    assert not runtime._error_recovery.has_attempted_compact


@pytest.mark.asyncio
async def test_backward_compat():
    """All existing test patterns must still work."""
    runtime = Runtime(adapter=MockAdapter(responses=["Hello!"]), enable_intelligence=False)
    msgs = [msg async for msg in runtime.chat("hi")]
    assistants = [m for m in msgs if isinstance(m, AssistantMessage)]
    assert len(assistants) == 1
    assert assistants[0].content == "Hello!"
