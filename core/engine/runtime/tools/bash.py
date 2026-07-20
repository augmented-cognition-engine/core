"""BashTool — executes shell commands in a subprocess with timeout support."""

from __future__ import annotations

import asyncio
from typing import Any

from core.engine.runtime.tools import RuntimeTool

_DEFAULT_TIMEOUT = 120


class BashTool(RuntimeTool):
    """Run a bash command and return stdout + stderr."""

    name: str = "bash"
    description: str = (
        "Run a shell command. Returns stdout and stderr combined. "
        "Non-zero exit codes are reported. Commands are killed after timeout."
    )
    is_read_only: bool = False

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "number",
                    "description": (f"Seconds before the command is killed. Defaults to {_DEFAULT_TIMEOUT}."),
                },
            },
            "required": ["command"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        command: str = input["command"]
        timeout: float = float(input.get("timeout", _DEFAULT_TIMEOUT))

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        try:
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            return f"Command timed out after {timeout:.0f}s"

        output = stdout_bytes.decode(errors="replace")

        if proc.returncode != 0:
            suffix = f"\nExit code: {proc.returncode}"
            output = output + suffix if output else suffix

        return output
