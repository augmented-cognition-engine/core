"""Tests for the runtime tool system."""

import pytest

from core.engine.runtime.tools import RuntimeTool, ToolRegistry


class EchoTool(RuntimeTool):
    name = "echo"
    description = "Echoes the input"
    is_read_only = True

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, input: dict) -> str:
        return input["text"]


def test_tool_registration():
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    assert registry.get("echo") is tool
    assert "echo" in registry.list_names()


def test_tool_schema_generation():
    tool = EchoTool()
    schema = tool.to_api_schema()
    assert schema["name"] == "echo"
    assert schema["description"] == "Echoes the input"
    assert "properties" in schema["input_schema"]


def test_unknown_tool_returns_none():
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


@pytest.mark.asyncio
async def test_tool_execution():
    tool = EchoTool()
    result = await tool.execute({"text": "hello"})
    assert result == "hello"


def test_tool_read_only_flag():
    tool = EchoTool()
    assert tool.is_read_only is True
