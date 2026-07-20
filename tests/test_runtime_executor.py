"""Tests for the tool executor with concurrency rules."""

import pytest

from core.engine.runtime.models import ToolResultMessage, ToolUseBlock
from core.engine.runtime.tool_executor import ToolExecutor
from core.engine.runtime.tools import ToolRegistry
from core.engine.runtime.tools.bash import BashTool
from core.engine.runtime.tools.file_read import FileReadTool
from core.engine.runtime.tools.grep import GrepTool


def _make_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(BashTool())
    reg.register(FileReadTool())
    reg.register(GrepTool())
    return reg


@pytest.mark.asyncio
async def test_execute_single_tool():
    executor = ToolExecutor(_make_registry())
    blocks = [ToolUseBlock(id="tu_1", name="bash", input={"command": "echo hi"})]
    results = await executor.execute(blocks)
    assert len(results) == 1
    assert isinstance(results[0], ToolResultMessage)
    assert "hi" in results[0].content


@pytest.mark.asyncio
async def test_execute_unknown_tool():
    executor = ToolExecutor(_make_registry())
    blocks = [ToolUseBlock(id="tu_1", name="nonexistent", input={})]
    results = await executor.execute(blocks)
    assert len(results) == 1
    assert results[0].is_error
    assert "not found" in results[0].content.lower() or "unknown" in results[0].content.lower()


@pytest.mark.asyncio
async def test_execute_parallel_read_only():
    """Read-only tools should execute in parallel."""
    executor = ToolExecutor(_make_registry())
    blocks = [
        ToolUseBlock(id="tu_1", name="read", input={"file_path": "pyproject.toml"}),
        # Scope grep to a single small in-repo file to avoid full-tree scan latency
        ToolUseBlock(id="tu_2", name="grep", input={"pattern": "def", "path": "pyproject.toml"}),
    ]
    results = await executor.execute(blocks)
    assert len(results) == 2
    ids = {r.tool_use_id for r in results}
    assert ids == {"tu_1", "tu_2"}


@pytest.mark.asyncio
async def test_results_ordered_by_input():
    """Results must be in the same order as input blocks."""
    executor = ToolExecutor(_make_registry())
    blocks = [
        ToolUseBlock(id="tu_1", name="bash", input={"command": "echo first"}),
        ToolUseBlock(id="tu_2", name="bash", input={"command": "echo second"}),
    ]
    results = await executor.execute(blocks)
    assert results[0].tool_use_id == "tu_1"
    assert results[1].tool_use_id == "tu_2"
