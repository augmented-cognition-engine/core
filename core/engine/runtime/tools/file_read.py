"""FileReadTool — reads a file with optional line offset and limit."""

from __future__ import annotations

import os
from typing import Any

from core.engine.runtime.tools import RuntimeTool

_DEFAULT_LIMIT = 2000


class FileReadTool(RuntimeTool):
    """Read a file and return its contents with line numbers."""

    name: str = "read"
    description: str = (
        "Read a file from the filesystem. Returns numbered lines. Use offset and limit to read a slice of a large file."
    )
    is_read_only: bool = True

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": ("1-based line number to start reading from. Defaults to 1 (beginning of file)."),
                },
                "limit": {
                    "type": "integer",
                    "description": (f"Maximum number of lines to return. Defaults to {_DEFAULT_LIMIT}."),
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        file_path: str = input["file_path"]
        offset: int = int(input.get("offset", 1))
        limit: int = int(input.get("limit", _DEFAULT_LIMIT))

        if not os.path.exists(file_path):
            return f"Error: file not found: {file_path}"

        if not os.path.isfile(file_path):
            return f"Error: path is not a file: {file_path}"

        try:
            with open(file_path, encoding="utf-8", errors="replace") as fh:
                all_lines = fh.readlines()
        except OSError as exc:
            return f"Error reading file: {exc}"

        # offset is 1-based; slice out the requested window
        start = max(0, offset - 1)
        selected = all_lines[start : start + limit]

        lines_out: list[str] = []
        for i, line in enumerate(selected, start=start + 1):
            lines_out.append(f"{i}\t{line}")

        return "".join(lines_out)
