# engine/scanner/security_scanner.py
"""Semgrep security scanner — subprocess runner, structured findings.

LGPL license. 5000+ rules via --config=auto.
Falls back gracefully if semgrep is not installed. Never raises —
security scanning must not block the commit flow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_semgrep_available: bool = bool(shutil.which("semgrep"))

_SUPPORTED_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb", ".php"}


@dataclass
class SecurityFinding:
    rule_id: str
    severity: str  # "ERROR" | "WARNING" | "INFO"
    message: str
    file: str
    line: int
    fix: str = ""


async def scan_files(file_paths: list[str], repo_path: str) -> list[SecurityFinding]:
    """Run semgrep on a list of files. Returns structured findings.

    Never raises — returns [] on missing semgrep, timeout, or any error.
    """
    if not _semgrep_available or not file_paths:
        return []

    targets = [
        f
        for f in file_paths
        if os.path.splitext(f)[1] in _SUPPORTED_EXTS and os.path.exists(os.path.join(repo_path, f))
    ]
    if not targets:
        return []

    cmd = [
        "semgrep",
        "--config=auto",
        "--config=p/owasp-top-ten",
        "--json",
        "--quiet",
        "--no-git-ignore",
        "--timeout=30",
    ] + [os.path.join(repo_path, t) for t in targets]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        if not stdout:
            return []
        data = json.loads(stdout)
        findings = _parse_results(data.get("results", []), repo_path)
        logger.info("Security scan: %d files → %d findings", len(targets), len(findings))
        return findings
    except Exception as exc:
        logger.debug("Semgrep scan failed (non-fatal): %s", exc)
        return []


def _parse_results(raw: list[dict], repo_path: str) -> list[SecurityFinding]:
    findings = []
    for r in raw:
        try:
            path = r.get("path", "").replace(repo_path.rstrip("/") + "/", "")
            findings.append(
                SecurityFinding(
                    rule_id=r.get("check_id", "unknown"),
                    severity=r.get("extra", {}).get("severity", "WARNING"),
                    message=r.get("extra", {}).get("message", ""),
                    file=path,
                    line=r.get("start", {}).get("line", 0),
                    fix=r.get("extra", {}).get("fix", ""),
                )
            )
        except Exception:
            continue
    return findings


def findings_to_intelligence(findings: list[SecurityFinding]) -> str:
    """Format findings as an intelligence context string for ACE's security loader."""
    if not findings:
        return ""
    lines = ["## Security Findings (Semgrep)"]
    for f in findings:
        lines.append(f"- [{f.severity}] {f.file}:{f.line} — {f.message} ({f.rule_id})")
    return "\n".join(lines)
