"""FileWriteTool — creates or overwrites a file with given content."""

from __future__ import annotations

import os
from typing import Any

from core.engine.runtime.tools import RuntimeTool
from core.engine.runtime.tools.git_safety import pre_edit_save


class FileWriteTool(RuntimeTool):
    """Write content to a file, creating parent directories as needed."""

    name: str = "write"
    description: str = (
        "Write content to a file. Creates the file (and any missing parent directories) "
        "if it does not exist, or overwrites it if it does."
    )
    is_read_only: bool = False

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write to the file.",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        file_path: str = input["file_path"]
        content: str = input["content"]

        try:
            pre_edit_save(file_path)
            parent = os.path.dirname(file_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as exc:
            return f"Error writing file: {exc}"

        return f"Success: wrote {len(content)} bytes to {file_path}"
