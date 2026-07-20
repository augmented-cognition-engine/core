"""GrepTool — search file contents using ripgrep (rg) with grep fallback."""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from core.engine.runtime.tools import RuntimeTool

_TIMEOUT = 30
_MAX_LINES = 250


class GrepTool(RuntimeTool):
    """Search for a pattern in files using ripgrep or grep."""

    name: str = "grep"
    description: str = (
        "Search for a regex pattern across files. Uses ripgrep (rg) if available, "
        "falls back to grep -rn. Returns up to 250 matching lines."
    )
    is_read_only: bool = True

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file path to search in. Defaults to current directory.",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.py'). Only applies when using ripgrep.",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        pattern: str = input["pattern"]
        path: str = input.get("path", ".")
        glob_pattern: str | None = input.get("glob")

        use_rg = shutil.which("rg") is not None

        if use_rg:
            cmd = ["rg", "--line-number", "--no-heading", pattern]
            if glob_pattern:
                cmd += ["--glob", glob_pattern]
            cmd.append(path)
        else:
            cmd = ["grep", "-rn", pattern, path]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            return f"Error: grep timed out after {_TIMEOUT}s"
        except FileNotFoundError as exc:
            return f"Error: command not found: {exc}"

        output = stdout_bytes.decode(errors="replace")
        stderr_output = stderr_bytes.decode(errors="replace").strip()

        # grep/rg exit code 1 means no matches — not an error
        if proc.returncode not in (0, 1):
            msg = f"grep failed (exit {proc.returncode})"
            if stderr_output:
                msg += f": {stderr_output}"
            return msg

        if not output.strip():
            return "No matches found."

        lines = output.splitlines()
        if len(lines) > _MAX_LINES:
            lines = lines[:_MAX_LINES]
            lines.append(f"... (output capped at {_MAX_LINES} lines)")

        return "\n".join(lines)
