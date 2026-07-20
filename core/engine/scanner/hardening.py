# engine/scanner/hardening.py
"""Static analysis hardening runner — orchestrates all security/quality tools.

Entry point: run_hardening(repo_path, stack, config) -> HardeningReport

Designed for:
- ace_scan_hardening MCP tool (full scan, store findings)
- Pre-commit hooks (fast subset: secrets + critical security only)
- CI integration via E3a (full scan on every merge)

Tool dispatch by stack:
    Always:  Semgrep (OWASP) + TruffleHog (secrets)
    Python:  + Bandit + Ruff + pip-audit
    Node:    + npm audit (v2)
    IaC:     + Checkov (v2 — tf/k8s detected)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

Severity = Literal["critical", "high", "medium", "low", "info"]
Discipline = Literal[
    "security",
    "testing",
    "performance",
    "code_conventions",
    "dependency_management",
    "configuration",
    "devops",
    "documentation",
    "architecture",
]

_SEVERITY_WEIGHT: dict[str, int] = {
    "critical": 100,
    "high": 40,
    "medium": 15,
    "low": 5,
    "info": 1,
}
_DISCIPLINE_PRIORITY: dict[str, int] = {
    "security": 10,
    "dependency_management": 9,
    "testing": 7,
    "performance": 6,
    "code_conventions": 4,
    "documentation": 2,
    "configuration": 5,
    "devops": 5,
    "architecture": 6,
}


@dataclass
class Finding:
    """Normalized finding from any static analysis tool."""

    discipline: str
    severity: str  # critical | high | medium | low | info
    file: str
    line: int | None
    message: str
    tool: str
    rule_id: str = ""
    fix_command: str = ""
    col: int | None = None


@dataclass
class HardeningReport:
    """Full output of a hardening scan."""

    findings: list[Finding]
    tools_run: list[str]
    tools_skipped: list[str]
    scan_id: str
    repo_path: str
    stack: list[str]
    duration_seconds: float
    summary: dict = field(default_factory=dict)


async def run_hardening(
    repo_path: str,
    stack: list[str] | None = None,
    fast: bool = False,
    config: dict | None = None,
) -> HardeningReport:
    """Run full static analysis suite for the given repo.

    Args:
        repo_path:  Absolute path to repo root.
        stack:      Override detected stack. If None, detect from graph_file DB.
        fast:       Fast mode — secrets + critical security only. For pre-commit.
        config:     Optional config dict (exclude_patterns, min_severity, etc.)

    Returns: HardeningReport with ranked findings and run metadata.
    """
    import time

    start = time.monotonic()
    scan_id = str(uuid.uuid4())
    cfg = config or {}

    if stack is None:
        stack = await _detect_stack(repo_path)

    # Build list of (name, coroutine) pairs to run
    tasks: list[tuple[str, object]] = []

    # Always run: Semgrep (OWASP) + TruffleHog
    from core.engine.scanner import trufflehog_runner

    tasks.append(("trufflehog", trufflehog_runner.run(repo_path, cfg)))

    if not fast:
        # Semgrep runs via hardening wrapper (full repo path, not file list)
        tasks.append(("semgrep", _run_semgrep_full(repo_path, cfg)))

        if "python" in stack:
            from core.engine.scanner import bandit_runner, pip_audit_runner, ruff_runner

            tasks.append(("bandit", bandit_runner.run(repo_path, cfg)))
            tasks.append(("ruff", ruff_runner.run(repo_path, cfg)))
            tasks.append(("pip_audit", pip_audit_runner.run(repo_path, cfg)))
    else:
        # Fast mode: Semgrep critical only
        tasks.append(("semgrep", _run_semgrep_full(repo_path, cfg, fast=True)))

    # Run all adapters concurrently
    names = [name for name, _ in tasks]
    coros = [coro for _, coro in tasks]

    results = await asyncio.gather(*coros, return_exceptions=True)

    all_findings: list[Finding] = []
    tools_run: list[str] = []
    tools_skipped: list[str] = []

    for name, result in zip(names, results):
        if isinstance(result, Exception):
            logger.debug("Adapter %s raised: %s", name, result)
            tools_skipped.append(name)
        elif result:
            all_findings.extend(result)
            tools_run.append(name)
        else:
            # Empty list — tool ran but found nothing (or isn't installed)
            tools_skipped.append(name)

    # Always mark trufflehog as run even if 0 findings (it ran)
    if "trufflehog" not in tools_run and "trufflehog" not in tools_skipped:
        tools_skipped.append("trufflehog")

    ranked = rank_findings(all_findings)

    # Apply min_severity filter if configured
    min_sev = cfg.get("min_severity")
    if min_sev:
        min_weight = _SEVERITY_WEIGHT.get(min_sev, 0)
        ranked = [f for f in ranked if _SEVERITY_WEIGHT.get(f.severity, 0) >= min_weight]

    summary = _build_summary(ranked)
    duration = time.monotonic() - start

    return HardeningReport(
        findings=ranked,
        tools_run=tools_run,
        tools_skipped=tools_skipped,
        scan_id=scan_id,
        repo_path=repo_path,
        stack=stack,
        duration_seconds=round(duration, 2),
        summary=summary,
    )


async def _run_semgrep_full(
    repo_path: str,
    config: dict | None = None,
    fast: bool = False,
) -> list[Finding]:
    """Run Semgrep against repo_path with OWASP ruleset.

    Wraps the existing security_scanner.scan_files() by discovering all
    supported files first, then running on the full set.
    """
    import os
    import shutil

    if not shutil.which("semgrep"):
        return []

    cfg = config or {}
    exclude_dirs = set(cfg.get("exclude_dirs", ["venv", ".venv", "node_modules", ".git", "__pycache__"]))

    from core.engine.scanner.security_scanner import _SUPPORTED_EXTS

    file_paths: list[str] = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if os.path.splitext(f)[1] in _SUPPORTED_EXTS:
                rel = os.path.relpath(os.path.join(root, f), repo_path)
                file_paths.append(rel)
        if len(file_paths) > 2000:
            break

    if not file_paths:
        return []

    cmd = [
        "semgrep",
        "--config=auto",
        "--config=p/owasp-top-ten",
        "--json",
        "--quiet",
        "--no-git-ignore",
        "--timeout=30",
    ]
    if fast:
        cmd += ["--severity=ERROR"]
    cmd += [os.path.join(repo_path, f) for f in file_paths]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
        import json as _json

        data = _json.loads(stdout or b"{}")
        findings = []
        for r in data.get("results", []):
            path = r.get("path", "").replace(repo_path.rstrip("/") + "/", "")
            sev_raw = r.get("extra", {}).get("severity", "WARNING")
            sev = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}.get(sev_raw, "low")
            findings.append(
                Finding(
                    discipline="security",
                    severity=sev,
                    file=path,
                    line=r.get("start", {}).get("line"),
                    message=r.get("extra", {}).get("message", "")[:200],
                    tool="semgrep",
                    rule_id=r.get("check_id", ""),
                )
            )
        return findings
    except Exception as exc:
        logger.debug("Semgrep hardening run failed (non-fatal): %s", exc)
        return []


async def _detect_stack(repo_path: str) -> list[str]:
    """Detect stack from graph_file.language in DB. Falls back to filesystem."""
    try:
        from core.engine.core.db import parse_rows, pool

        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT language, count() AS n FROM graph_file "
                    "WHERE graph_id = 'default' GROUP BY language ORDER BY n DESC"
                )
            )
        return [r["language"] for r in rows if r.get("language") and r.get("n", 0) > 2]
    except Exception:
        return _detect_stack_filesystem(repo_path)


def _detect_stack_filesystem(repo_path: str) -> list[str]:
    """Fallback stack detection via filesystem walk (no DB required)."""
    import os

    found: set[str] = set()
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in ("venv", ".venv", "node_modules", ".git")]
        for f in files:
            if f.endswith(".py"):
                found.add("python")
            elif f == "package.json":
                found.add("node")
            elif f.endswith(".tf"):
                found.add("terraform")
        if len(found) >= 3:
            break
    return list(found)


def rank_findings(findings: list[Finding]) -> list[Finding]:
    """Sort by severity weight × discipline priority. Critical security first."""

    def score(f: Finding) -> int:
        return _SEVERITY_WEIGHT.get(f.severity, 0) * _DISCIPLINE_PRIORITY.get(f.discipline, 1)

    return sorted(findings, key=score, reverse=True)


def _build_summary(findings: list[Finding]) -> dict:
    summary: dict[str, dict] = {}
    for f in findings:
        d = summary.setdefault(
            f.discipline,
            {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
        )
        d[f.severity] = d.get(f.severity, 0) + 1
    return summary


async def _link_finding_to_capability(finding: Finding, product_id: str) -> str | None:
    """Find capability ID for this finding via graph_file → realizes → capability.

    Returns capability ID string or None.
    """
    try:
        from core.engine.core.db import parse_rows, pool

        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT out AS cap FROM realizes
                       WHERE in = (
                           SELECT id FROM graph_file WHERE path = <string>$file LIMIT 1
                       ) LIMIT 1""",
                    {"file": finding.file},
                )
            )
        cap = rows[0].get("cap") if rows else None
        return str(cap) if cap else None
    except Exception:
        return None


async def _write_findings(
    findings: list[Finding],
    scan_id: str,
    product_id: str,
) -> int:
    """Write normalized findings to capability_finding table.

    For each finding:
    1. Find capability via graph_file → realizes → capability (if path known)
    2. INSERT into capability_finding with scan_id for grouping

    Returns: count written
    """
    from core.engine.core.db import pool

    written = 0
    async with pool.connection() as db:
        for f in findings:
            cap_id = await _link_finding_to_capability(f, product_id)
            params = {
                "product": product_id,
                "capability": cap_id,
                "discipline": f.discipline,
                "severity": f.severity,
                "file": f.file,
                "line": f.line,
                "col": f.col,
                "message": f.message,
                "rule_id": f.rule_id or None,
                "fix_command": f.fix_command or None,
                "tool": f.tool,
                "scan_id": scan_id,
            }
            await db.query(
                """CREATE capability_finding SET
                    product = <record>$product,
                    capability = IF $capability THEN <record>$capability ELSE NONE END,
                    discipline = $discipline,
                    severity = $severity,
                    file = $file,
                    line = $line,
                    col = $col,
                    message = $message,
                    rule_id = $rule_id,
                    fix_command = $fix_command,
                    tool = $tool,
                    scan_id = $scan_id,
                    created_at = time::now()
                """,
                params,
            )
            written += 1
    return written
