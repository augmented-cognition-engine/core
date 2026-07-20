# engine/scanner/pip_audit_runner.py
"""pip-audit dependency vulnerability adapter.

pip-audit --format json --output -

CVE severity mapping (conservative — precise CVSS triage in E2 v2):
    Known fix available → high (upgrade is clear, impact is real)
    No fix yet         → medium (known vuln, no clear fix path)
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil

from core.engine.scanner.hardening import Finding

logger = logging.getLogger(__name__)

_available: bool = bool(shutil.which("pip-audit"))


async def run(repo_path: str, config: dict | None = None) -> list[Finding]:
    """Run pip-audit in repo_path context. Returns [] gracefully if not installed."""
    if not _available:
        return []

    cmd = ["pip-audit", "--format", "json", "--output", "-"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=repo_path,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        data = json.loads(stdout or b"[]")
        return _parse(data, repo_path)
    except Exception as exc:
        logger.debug("pip-audit failed (non-fatal): %s", exc)
        return []


def _parse(raw: list[dict], repo_path: str) -> list[Finding]:  # noqa: ARG001
    out: list[Finding] = []
    for pkg in raw:
        name = pkg.get("name", "unknown")
        version = pkg.get("version", "?")
        for vuln in pkg.get("vulns", []):
            vid = vuln.get("id", "")
            fix_versions = vuln.get("fix_versions", [])
            # Conservative: high if fix available, medium if no fix path
            sev = "high" if fix_versions else "medium"
            fix_cmd = f"pip install '{name}>={fix_versions[0]}'" if fix_versions else f"pip install --upgrade {name}"
            desc = vuln.get("description", "")[:120]
            out.append(
                Finding(
                    discipline="dependency_management",
                    severity=sev,
                    file="requirements.txt",
                    line=None,
                    message=f"{name}=={version} has known vulnerability {vid}: {desc}",
                    tool="pip_audit",
                    rule_id=vid,
                    fix_command=fix_cmd,
                )
            )
    return out
