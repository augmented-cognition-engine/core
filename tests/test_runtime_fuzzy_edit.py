"""Tests for fuzzy edit matching."""

import os
import tempfile

import pytest

from core.engine.runtime.tools.file_edit import FileEditTool


@pytest.mark.asyncio
async def test_exact_match_still_works():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def hello():\n    return 'world'\n")
        path = f.name
    try:
        tool = FileEditTool()
        result = await tool.execute(
            {"file_path": path, "old_string": "def hello():", "new_string": "def hello_world():"}
        )
        assert "success" in result.lower() or "edit" in result.lower()
        assert "hello_world" in open(path).read()
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_whitespace_tolerant():
    """Match should succeed even with different indentation."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("    def hello():\n        return 'world'\n")
        path = f.name
    try:
        tool = FileEditTool()
        # old_string has no leading whitespace but file has 4 spaces
        result = await tool.execute(
            {
                "file_path": path,
                "old_string": "def hello():\n    return 'world'",
                "new_string": "def greet():\n    return 'earth'",
            }
        )
        content = open(path).read()
        assert "greet" in content
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_fuzzy_match():
    """Match should succeed with minor differences (fuzzy)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def calculate_total(items):\n    total = sum(item.price for item in items)\n    return total\n")
        path = f.name
    try:
        tool = FileEditTool()
        # Slightly different (missing 's' on items in comprehension) — should fuzzy match
        result = await tool.execute(
            {
                "file_path": path,
                "old_string": "def calculate_total(items):\n    total = sum(item.price for item in item)\n    return total",
                "new_string": "def calculate_total(items, tax=0):\n    total = sum(item.price for item in items)\n    return total * (1 + tax)",
            }
        )
        content = open(path).read()
        assert "tax" in content
    finally:
        os.unlink(path)
