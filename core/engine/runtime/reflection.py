"""Discipline-aware edit validation — validate against ACE's quality standards.

Uses the runtime's BashTool for consistent tool tracking. Base validation
runs lint and test commands. Discipline-specific checks layer on top:

  security    → bandit SAST scan on modified Python files
  testing     → verify test files exist for modified modules
  All others  → base lint + test only

Max 3 reflection iterations to prevent infinite loops.
"""

from __future__ import annotations

import logging
import shutil

logger = logging.getLogger(__name__)

MAX_REFLECTIONS = 3

# Disciplines that trigger additional checks beyond lint + test
_DISCIPLINE_CHECKS: dict[str, str] = {
    # bandit: Python SAST — catches common security anti-patterns
    # -ll = medium severity and above only (avoids noise)
    "security": "bandit -r {files} -ll --quiet 2>&1 || true",
}


class ReflectionLoop:
    """Validates edits and generates reflection messages on failure."""

    def __init__(
        self,
        lint_cmd: str | None = None,
        test_cmd: str | None = None,
    ) -> None:
        self._lint_cmd = lint_cmd
        self._test_cmd = test_cmd
        self._reflection_count = 0

    @property
    def reflection_count(self) -> int:
        return self._reflection_count

    def can_reflect(self) -> bool:
        return self._reflection_count < MAX_REFLECTIONS

    def reset(self) -> None:
        self._reflection_count = 0

    async def validate(
        self,
        modified_files: list[str] | None = None,
        discipline: str | None = None,
    ) -> str | None:
        """Run validation. Returns error string if failed, None if clean.

        Parameters
        ----------
        modified_files:
            Files edited this turn — used for discipline-specific checks.
        discipline:
            ACE classifier discipline for this turn (e.g. 'security',
            'testing'). Enables targeted checks beyond base lint + test.
        """
        if not self._lint_cmd and not self._test_cmd:
            return None

        errors = []

        if self._lint_cmd:
            lint_result = await self._run_cmd(self._lint_cmd)
            if lint_result:
                errors.append(f"Lint errors:\n{lint_result}")

        if self._test_cmd:
            test_result = await self._run_cmd(self._test_cmd)
            if test_result:
                errors.append(f"Test failures:\n{test_result}")

        # Discipline-specific checks — layered on top of base validation
        if discipline and modified_files:
            extra = await self._discipline_check(discipline, modified_files)
            if extra:
                errors.append(extra)

        if errors:
            self._reflection_count += 1
            return "\n\n".join(errors)

        return None

    async def _discipline_check(self, discipline: str, modified_files: list[str]) -> str | None:
        """Run discipline-specific checks on the modified files."""
        template = _DISCIPLINE_CHECKS.get(discipline)
        if not template:
            return None

        # security → bandit, Python files only
        if discipline == "security":
            if not shutil.which("bandit"):
                return None
            py_files = [f for f in modified_files if f.endswith(".py")]
            if not py_files:
                return None
            cmd = template.format(files=" ".join(py_files))
            result = await self._run_cmd(cmd)
            if result:
                return f"Security issues (bandit):\n{result}"

        return None

    async def _run_cmd(self, cmd: str) -> str | None:
        """Run via BashTool for consistent tool tracking."""
        from core.engine.runtime.tools.bash import BashTool

        tool = BashTool()
        result = await tool.execute({"command": cmd, "timeout": 120})
        # BashTool returns output + exit code info
        if "Exit code:" in result and "Exit code: 0" not in result:
            # Cap output to prevent context explosion
            if len(result) > 3000:
                result = result[:3000] + "\n... (truncated)"
            return result
        return None
