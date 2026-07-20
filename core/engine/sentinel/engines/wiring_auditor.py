# engine/sentinel/engines/wiring_auditor.py
"""WiringAuditor — static-analysis check that detects built-but-not-connected components.

Checks:
  1. MCP parity — ace_* functions in tools.py with no reference in server.py
  2. Idle validators — _validate_* functions defined but never called in production code

Design: analysis methods accept source strings so they're pure functions and trivially
testable. run() handles file I/O and calls the analysis methods.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths relative to the repo root
_DEFAULT_TOOLS_PATH = "engine/mcp/tools.py"
_DEFAULT_SERVER_PATH = "engine/mcp/server.py"
_DEFAULT_SOURCE_ROOT = "engine"


class WiringAuditor:
    """Detects components that are built but not wired into the platform."""

    def __init__(
        self,
        tools_path: str | None = None,
        server_path: str | None = None,
        source_root: str | None = None,
    ) -> None:
        self.tools_path = tools_path or _DEFAULT_TOOLS_PATH
        self.server_path = server_path or _DEFAULT_SERVER_PATH
        self.source_root = source_root or _DEFAULT_SOURCE_ROOT

    # ── Public analysis methods (pure — accept source strings) ────────────────

    def check_mcp_parity(self, tools_source: str, server_source: str) -> list[str]:
        """Return list of ace_* function names defined in tools_source but absent from server_source.

        A name is considered 'registered' if it appears anywhere in server_source —
        sufficient because the server.py import pattern always names the function.
        """
        defined = re.findall(r"^(?:async )?def (ace_\w+)\s*\(", tools_source, re.MULTILINE)
        return [name for name in defined if name not in server_source]

    def check_idle_validators(
        self,
        source_files: dict[str, str],
        all_source: str,
    ) -> list[str]:
        """Return list of _validate_* function names defined in non-test source files
        that have zero call sites in all_source.

        A call site is any occurrence of ``_validate_foo(`` that is NOT a function
        definition (i.e., not preceded by ``def ``).
        """
        idle: list[str] = []

        for file_path, content in source_files.items():
            # Skip test files — validators defined in tests are test helpers, not idle
            if "test" in file_path.lower():
                continue

            defined = re.findall(r"def (_validate_\w+)\s*\(", content)
            for name in defined:
                # Count all appearances of "name(" in the combined source
                call_pattern = re.compile(rf"(?<!def ){re.escape(name)}\s*\(")
                calls = call_pattern.findall(all_source)
                if not calls:
                    idle.append(name)

        return idle

    # ── File I/O helpers (monkeypatchable for testing) ─────────────────────────

    def _read_tools_source(self) -> str:
        return Path(self.tools_path).read_text(encoding="utf-8")

    def _read_server_source(self) -> str:
        return Path(self.server_path).read_text(encoding="utf-8")

    def _collect_source_files(self) -> dict[str, str]:
        """Return {relative_path: content} for all .py files under source_root."""
        root = Path(self.source_root)
        files: dict[str, str] = {}
        for path in root.rglob("*.py"):
            try:
                files[str(path)] = path.read_text(encoding="utf-8")
            except Exception:
                pass
        return files

    # ── Main entry point ───────────────────────────────────────────────────────

    def run(self) -> dict:
        """Read source files and return a structured wiring report.

        Returns::

            {
                "mcp_parity_gaps": [...],   # ace_* functions not in server.py
                "idle_validators": [...],   # _validate_* functions with no call sites
                "total_gaps": int,
                "clean": bool,
            }
        """
        try:
            tools_source = self._read_tools_source()
        except Exception as exc:
            logger.warning("WiringAuditor: could not read tools source: %s", exc)
            tools_source = ""

        try:
            server_source = self._read_server_source()
        except Exception as exc:
            logger.warning("WiringAuditor: could not read server source: %s", exc)
            server_source = ""

        source_files = self._collect_source_files()
        all_source = "\n".join(source_files.values())

        mcp_gaps = self.check_mcp_parity(tools_source, server_source)
        idle_validators = self.check_idle_validators(source_files, all_source)

        total = len(mcp_gaps) + len(idle_validators)
        return {
            "mcp_parity_gaps": mcp_gaps,
            "idle_validators": idle_validators,
            "total_gaps": total,
            "clean": total == 0,
        }
