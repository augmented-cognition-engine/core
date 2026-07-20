"""Runtime tool system — base class and registry.

Each tool is a class with a name, description, input schema, and execute method.
Tools declare whether they are read-only (can run in parallel) or not (exclusive).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RuntimeTool(ABC):
    """Base class for all runtime tools."""

    name: str = ""
    description: str = ""
    is_read_only: bool = False

    @abstractmethod
    def get_input_schema(self) -> dict[str, Any]:
        """Return JSON schema for the tool's input."""
        ...

    @abstractmethod
    async def execute(self, input: dict[str, Any]) -> str:
        """Execute the tool and return the result as a string."""
        ...

    def to_api_schema(self) -> dict[str, Any]:
        """Convert to the format expected by the model API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_input_schema(),
        }

    async def close(self) -> None:
        """Optional cleanup hook — override in tools that hold external resources."""


class ToolRegistry:
    """Registry of available tools. Lookup by name."""

    def __init__(self) -> None:
        self._tools: dict[str, RuntimeTool] = {}

    def register(self, tool: RuntimeTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> RuntimeTool | None:
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def list_schemas(self) -> list[dict[str, Any]]:
        return [t.to_api_schema() for t in self._tools.values()]
