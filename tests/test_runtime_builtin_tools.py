"""Tests for built-in runtime tools."""

import os
import tempfile

import pytest

from core.engine.runtime.tools.bash import BashTool
from core.engine.runtime.tools.file_read import FileReadTool


@pytest.mark.asyncio
async def test_bash_tool_ls():
    tool = BashTool()
    result = await tool.execute({"command": "echo hello"})
    assert "hello" in result


@pytest.mark.asyncio
async def test_bash_tool_exit_code():
    tool = BashTool()
    result = await tool.execute({"command": "false"})
    assert "exit code" in result.lower() or "error" in result.lower()


@pytest.mark.asyncio
async def test_bash_tool_timeout():
    tool = BashTool()
    result = await tool.execute({"command": "sleep 60", "timeout": 1})
    assert "timeout" in result.lower() or "timed out" in result.lower()


def test_bash_tool_schema():
    tool = BashTool()
    schema = tool.get_input_schema()
    assert "command" in schema["properties"]


def test_bash_tool_is_not_read_only():
    assert BashTool.is_read_only is False


@pytest.mark.asyncio
async def test_file_read_tool():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line 1\nline 2\nline 3\n")
        path = f.name
    try:
        tool = FileReadTool()
        result = await tool.execute({"file_path": path})
        assert "line 1" in result
        assert "line 2" in result
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_file_read_tool_with_offset():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for i in range(10):
            f.write(f"line {i + 1}\n")
        path = f.name
    try:
        tool = FileReadTool()
        result = await tool.execute({"file_path": path, "offset": 3, "limit": 2})
        assert "line 3" in result
        assert "line 4" in result
        assert "line 1" not in result
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_file_read_nonexistent():
    tool = FileReadTool()
    result = await tool.execute({"file_path": "/nonexistent/path.txt"})
    assert "error" in result.lower() or "not found" in result.lower() or "no such" in result.lower()


def test_file_read_is_read_only():
    assert FileReadTool.is_read_only is True
