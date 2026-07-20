"""Tests for write/search built-in tools."""

import os
import tempfile

import pytest

from core.engine.runtime.tools.file_edit import FileEditTool
from core.engine.runtime.tools.file_write import FileWriteTool
from core.engine.runtime.tools.glob_tool import GlobTool
from core.engine.runtime.tools.grep import GrepTool


@pytest.mark.asyncio
async def test_file_write():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        path = f.name
    try:
        tool = FileWriteTool()
        result = await tool.execute({"file_path": path, "content": "hello world"})
        assert "success" in result.lower() or "wrote" in result.lower()
        assert open(path).read() == "hello world"
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_file_edit():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("old text here")
        path = f.name
    try:
        tool = FileEditTool()
        result = await tool.execute(
            {
                "file_path": path,
                "old_string": "old text",
                "new_string": "new text",
            }
        )
        assert "success" in result.lower() or "applied" in result.lower()
        assert "new text here" in open(path).read()
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_file_edit_no_match():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("some content")
        path = f.name
    try:
        tool = FileEditTool()
        result = await tool.execute(
            {
                "file_path": path,
                "old_string": "nonexistent",
                "new_string": "replacement",
            }
        )
        assert "not found" in result.lower() or "no match" in result.lower()
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_grep():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "test.py")
        with open(p, "w") as f:
            f.write("def hello():\n    pass\ndef world():\n    pass\n")
        tool = GrepTool()
        result = await tool.execute({"pattern": "def", "path": d})
        assert "hello" in result
        assert "world" in result


@pytest.mark.asyncio
async def test_glob():
    with tempfile.TemporaryDirectory() as d:
        for name in ["a.py", "b.py", "c.txt"]:
            open(os.path.join(d, name), "w").close()
        tool = GlobTool()
        result = await tool.execute({"pattern": "*.py", "path": d})
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result
