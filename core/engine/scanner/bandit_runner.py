# engine/scanner/bandit_runner.py
"""Bandit Python security scanner adapter.

Output: bandit -r <path> -f json -ll (medium+ severity only)

Severity mapping:
    HIGH + HIGH confidence → critical
    HIGH → high
    MEDIUM → medium
    LOW → low
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil

from core.engine.scanner.hardening import Finding

logger = logging.getLogger(__name__)

_available: bool = bool(shutil.which("bandit"))


async def run(repo_path: str, config: dict | None = None) -> list[Finding]:
    """Run bandit against repo_path. Returns [] gracefully if not installed."""
    if not _available:
        return []

    cfg = config or {}
    exclude = cfg.get(
        "exclude",
        f"{repo_path}/venv,{repo_path}/.venv,{repo_path}/tests,{repo_path}/node_modules",
    )

    cmd = [
        "bandit",
        "-r",
        repo_path,
        "-f",
        "json",
        "-ll",
        "-q",
        "--exclude",
        exclude,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        data = json.loads(stdout or b"{}")
        return _parse(data.get("results", []), repo_path)
    except Exception as exc:
        logger.debug("Bandit failed (non-fatal): %s", exc)
        return []


def _parse(raw: list[dict], repo_path: str) -> list[Finding]:
    out: list[Finding] = []
    sev_map = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
    for r in raw:
        sev = r.get("issue_severity", "LOW")
        conf = r.get("issue_confidence", "LOW")
        # Upgrade to critical when both severity and confidence are HIGH
        mapped = "critical" if (sev == "HIGH" and conf == "HIGH") else sev_map.get(sev, "low")
        path = r.get("filename", "").replace(repo_path.rstrip("/") + "/", "")
        out.append(
            Finding(
                discipline="security",
                severity=mapped,
                file=path,
                line=r.get("line_number"),
                message=r.get("issue_text", ""),
                tool="bandit",
                rule_id=r.get("test_id", ""),
                fix_command="",
            )
        )
    return out
