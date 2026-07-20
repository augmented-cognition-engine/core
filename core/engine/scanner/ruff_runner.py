# engine/scanner/ruff_runner.py
"""Ruff code quality adapter.

ruff check --output-format json <path>

Maps rule code prefixes to ACE disciplines:
    S (bandit security rules) → security
    C90 (complexity)          → performance
    ANN (type annotations)    → documentation
    PL (pylint)               → architecture
    PT (pytest)               → testing
    Default                   → code_conventions
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil

from core.engine.scanner.hardening import Finding

logger = logging.getLogger(__name__)

_available: bool = bool(shutil.which("ruff"))

_RULE_DISCIPLINE: dict[str, str] = {
    "S": "security",
    "C90": "performance",
    "ANN": "documentation",
    "PL": "architecture",
    "PT": "testing",
}


def _rule_to_discipline(code: str) -> str:
    for prefix, disc in _RULE_DISCIPLINE.items():
        if code.startswith(prefix):
            return disc
    return "code_conventions"


async def run(repo_path: str, config: dict | None = None) -> list[Finding]:
    """Run ruff check against repo_path. Returns [] gracefully if not installed."""
    if not _available:
        return []

    cmd = [
        "ruff",
        "check",
        "--output-format",
        "json",
        "--exclude",
        "venv,.venv,node_modules",
        repo_path,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        data = json.loads(stdout or b"[]")
        return _parse(data, repo_path)
    except Exception as exc:
        logger.debug("Ruff failed (non-fatal): %s", exc)
        return []


def _parse(raw: list[dict], repo_path: str) -> list[Finding]:
    out: list[Finding] = []
    for r in raw:
        code = r.get("code", "")
        path = r.get("filename", "").replace(repo_path.rstrip("/") + "/", "")
        loc = r.get("location", {})
        # Security rule codes → high; everything else → low
        sev = "high" if code.startswith("S") else "low"
        fix_cmd = f"ruff check --fix {path}" if r.get("fix") else ""
        out.append(
            Finding(
                discipline=_rule_to_discipline(code),
                severity=sev,
                file=path,
                line=loc.get("row"),
                col=loc.get("column"),
                message=r.get("message", ""),
                tool="ruff",
                rule_id=code,
                fix_command=fix_cmd,
            )
        )
    return out
