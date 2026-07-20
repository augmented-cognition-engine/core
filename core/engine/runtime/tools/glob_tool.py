"""GlobTool — find files matching a glob pattern."""

from __future__ import annotations

import glob
import os
from typing import Any

from core.engine.runtime.tools import RuntimeTool

_MAX_RESULTS = 250


class GlobTool(RuntimeTool):
    """Find files matching a glob pattern."""

    name: str = "glob"
    description: str = (
        "Find files matching a glob pattern. Supports ** for recursive matching. "
        f"Returns up to {_MAX_RESULTS} paths sorted by modification time."
    )
    is_read_only: bool = True

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match (e.g. '**/*.py', '*.txt').",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search in. Defaults to current directory.",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        pattern: str = input["pattern"]
        base_path: str = input.get("path", ".")

        # Combine base path with pattern
        full_pattern = os.path.join(base_path, pattern)

        try:
            matches = glob.glob(full_pattern, recursive=True)
        except Exception as exc:
            return f"Error running glob: {exc}"

        if not matches:
            return "No files matched."

        # Sort by modification time (newest first)
        try:
            matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        except OSError:
            matches.sort()

        if len(matches) > _MAX_RESULTS:
            matches = matches[:_MAX_RESULTS]
            truncated = True
        else:
            truncated = False

        result = "\n".join(matches)
        if truncated:
            result += f"\n... (results capped at {_MAX_RESULTS})"

        return result
