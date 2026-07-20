"""FileEditTool — surgical string replacement within a file.

Supports cascading match strategies:
1. Exact match (fastest, preferred)
2. Whitespace-tolerant (strips leading whitespace, handles indentation differences)
3. Fuzzy match (difflib.SequenceMatcher, threshold 0.8) for minor typos/differences
"""

from __future__ import annotations

import difflib
import logging
import os
import textwrap
from typing import Any

from core.engine.runtime.tools import RuntimeTool
from core.engine.runtime.tools.git_safety import pre_edit_save

logger = logging.getLogger(__name__)

_FUZZY_THRESHOLD = 0.85


def _find_fuzzy_region(content: str, old_string: str) -> tuple[int, int] | None:
    """Find the region in content that best fuzzy-matches old_string.

    Splits content into candidate windows of the same line count as old_string,
    scores each with SequenceMatcher, and returns the (start, end) byte offsets
    of the best match if it exceeds _FUZZY_THRESHOLD.
    """
    old_lines = old_string.splitlines()
    n = len(old_lines)
    if n == 0:
        return None

    content_lines = content.splitlines(keepends=True)
    total = len(content_lines)

    best_ratio = 0.0
    best_start_line = -1

    for i in range(total - n + 1):
        window = "".join(content_lines[i : i + n])
        ratio = difflib.SequenceMatcher(None, old_string, window).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start_line = i

    if best_ratio < _FUZZY_THRESHOLD or best_start_line < 0:
        return None

    # Convert line index to byte offsets
    start_offset = sum(len(line) for line in content_lines[:best_start_line])
    end_offset = start_offset + sum(len(line) for line in content_lines[best_start_line : best_start_line + n])
    return start_offset, end_offset


def _strip_common_indent(text: str) -> str:
    """Remove common leading whitespace from all lines."""
    return textwrap.dedent(text)


class FileEditTool(RuntimeTool):
    """Replace a string in a file using cascading match strategies."""

    name: str = "edit"
    description: str = (
        "Replace a string in a file. Tries exact match first, then whitespace-tolerant, "
        "then fuzzy match (difflib). old_string must resolve to exactly one region."
    )
    is_read_only: bool = False

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit.",
                },
                "old_string": {
                    "type": "string",
                    "description": "The string to find and replace. Exact match preferred; fuzzy fallback available.",
                },
                "new_string": {
                    "type": "string",
                    "description": "The string to substitute in place of old_string.",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        file_path: str = input["file_path"]
        old_string: str = input["old_string"]
        new_string: str = input["new_string"]

        if not os.path.exists(file_path):
            return f"Error: file not found: {file_path}"

        if not os.path.isfile(file_path):
            return f"Error: path is not a file: {file_path}"

        try:
            with open(file_path, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError as exc:
            return f"Error reading file: {exc}"

        # --- Strategy 1: Exact match ---
        count = content.count(old_string)
        if count == 1:
            pre_edit_save(file_path)
            new_content = content.replace(old_string, new_string, 1)
            return self._write(file_path, new_content, "exact")
        if count > 1:
            return (
                f"Error: old_string matches {count} times in {file_path}. "
                "Provide more context to make the match unique."
            )

        # --- Strategy 2: Whitespace-tolerant ---
        stripped_old = _strip_common_indent(old_string)
        stripped_content = _strip_common_indent(content)
        ws_count = stripped_content.count(stripped_old)
        if ws_count == 1:
            # Rebuild full content by replacing in the stripped version, then
            # reattach the original indentation by replacing byte-for-byte in the
            # original content via fuzzy region lookup on the stripped form.
            region = _find_fuzzy_region(content, stripped_old)
            if region:
                start, end = region
                pre_edit_save(file_path)
                new_content = content[:start] + new_string + content[end:]
                return self._write(file_path, new_content, "whitespace-tolerant")
            # Fallback: direct replace on stripped content
            pre_edit_save(file_path)
            new_content = stripped_content.replace(stripped_old, new_string, 1)
            return self._write(file_path, new_content, "whitespace-tolerant")
        if ws_count > 1:
            return (
                f"Error: whitespace-tolerant old_string matches {ws_count} times in {file_path}. "
                "Provide more context to make the match unique."
            )

        # --- Strategy 3: Fuzzy match ---
        region = _find_fuzzy_region(content, old_string)
        if region is None:
            # Also try with stripped old_string
            region = _find_fuzzy_region(content, stripped_old)

        if region:
            start, end = region
            pre_edit_save(file_path)
            new_content = content[:start] + new_string + content[end:]
            logger.debug("fuzzy edit applied to %s (ratio >= %.2f)", file_path, _FUZZY_THRESHOLD)
            return self._write(file_path, new_content, "fuzzy")

        return f"Error: old_string not found in {file_path} (tried exact, whitespace-tolerant, and fuzzy matching)"

    def _write(self, file_path: str, new_content: str, strategy: str) -> str:
        try:
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write(new_content)
        except OSError as exc:
            return f"Error writing file: {exc}"
        return f"Success: applied edit to {file_path} ({strategy} match)"
