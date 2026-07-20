"""Test coverage extractor — runs the stack-appropriate coverage tool and
normalizes output into CoverageRow records.

Pattern matches engine/scanner/ tool adapters (bandit, ruff, pip-audit):
- Subprocess execution with timeout
- Graceful degradation when tool not installed
- Normalized output: list[CoverageRow]
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CoverageRow:
    """Per-file coverage record. Stack-agnostic shape."""

    file: str
    lines_covered: int
    lines_total: int
    branches_covered: int = 0
    branches_total: int = 0
    functions_covered: int = 0
    functions_total: int = 0
    untested_functions: list[str] = field(default_factory=list)

    @property
    def line_pct(self) -> float:
        return (self.lines_covered / self.lines_total) if self.lines_total else 0.0

    @property
    def branch_pct(self) -> float:
        return (self.branches_covered / self.branches_total) if self.branches_total else 0.0

    @property
    def function_pct(self) -> float:
        return (self.functions_covered / self.functions_total) if self.functions_total else 0.0


@dataclass
class CoverageReport:
    rows: list[CoverageRow]
    tool: str
    stack: str
    duration_seconds: float
    raw_output_path: str | None


async def run_coverage(
    repo_path: str,
    stack: str = "python",
    timeout_seconds: int = 600,
) -> CoverageReport:
    """Run the appropriate coverage tool for the stack and return normalized rows.

    Never raises. Returns CoverageReport with empty rows if tool missing or tests fail.
    """
    if stack == "python":
        return await _run_python(repo_path, timeout_seconds)
    if stack in ("node", "javascript", "typescript"):
        return await _run_node(repo_path, timeout_seconds)
    if stack == "go":
        return await _run_go(repo_path, timeout_seconds)
    return CoverageReport(rows=[], tool="none", stack=stack, duration_seconds=0.0, raw_output_path=None)


async def _run_python(repo_path: str, timeout: int) -> CoverageReport:
    """pytest --cov --cov-report=xml:coverage.xml"""
    start = time.time()
    if not shutil.which("pytest"):
        return CoverageReport(
            rows=[],
            tool="pytest-cov",
            stack="python",
            duration_seconds=0.0,
            raw_output_path=None,
        )

    output_path = os.path.join(repo_path, ".ace/coverage.xml")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        "pytest",
        "--cov",
        f"--cov-report=xml:{output_path}",
        "--cov-report=",
        "-q",
        "-m",
        "not e2e",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=repo_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except Exception as exc:
        logger.debug("pytest --cov failed (non-fatal): %s", exc)
        return CoverageReport(
            rows=[],
            tool="pytest-cov",
            stack="python",
            duration_seconds=time.time() - start,
            raw_output_path=None,
        )

    rows = _parse_cobertura(output_path, repo_path) if os.path.exists(output_path) else []
    return CoverageReport(
        rows=rows,
        tool="pytest-cov",
        stack="python",
        duration_seconds=time.time() - start,
        raw_output_path=output_path,
    )


def _parse_cobertura(xml_path: str, repo_path: str) -> list[CoverageRow]:
    """Parse cobertura XML (output by pytest-cov, c8, jest --coverage)."""
    rows: list[CoverageRow] = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as exc:
        logger.debug("Failed to parse cobertura XML at %s: %s", xml_path, exc)
        return rows

    prefix = repo_path.rstrip("/") + "/"

    for cls in root.iter("class"):
        filename = cls.get("filename", "")
        if not filename:
            continue

        rel = filename.replace(prefix, "").lstrip("/")

        lines = list(cls.iter("line"))
        lines_total = len(lines)
        lines_covered = sum(1 for ln in lines if int(ln.get("hits", "0")) > 0)
        branches_total = sum(1 for ln in lines if ln.get("branch") == "true")
        branches_covered = sum(1 for ln in lines if ln.get("branch") == "true" and int(ln.get("hits", "0")) > 0)

        methods = list(cls.iter("method"))
        functions_total = len(methods)
        functions_covered = 0
        untested: list[str] = []
        for m in methods:
            name = m.get("name", "")
            m_lines = list(m.iter("line"))
            hits = sum(int(ln.get("hits", "0")) for ln in m_lines)
            if hits > 0:
                functions_covered += 1
            elif name:
                untested.append(name)

        rows.append(
            CoverageRow(
                file=rel,
                lines_covered=lines_covered,
                lines_total=lines_total,
                branches_covered=branches_covered,
                branches_total=branches_total,
                functions_covered=functions_covered,
                functions_total=functions_total,
                untested_functions=untested,
            )
        )

    return rows


async def _run_node(repo_path: str, timeout: int) -> CoverageReport:
    """c8 --reporter cobertura — deferred to E6 v2."""
    return CoverageReport(rows=[], tool="c8", stack="node", duration_seconds=0.0, raw_output_path=None)


async def _run_go(repo_path: str, timeout: int) -> CoverageReport:
    """go test -coverprofile — deferred to E6 v2."""
    return CoverageReport(rows=[], tool="go-cover", stack="go", duration_seconds=0.0, raw_output_path=None)
