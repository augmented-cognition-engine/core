# engine/scanner/trufflehog_runner.py
"""TruffleHog secret scanning adapter.

trufflehog filesystem --json --no-update <path>

Always runs regardless of stack — secrets are universal.
Severity: always critical (exposed secrets = critical by definition).
Credential values are redacted from the stored message.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

from core.engine.scanner.hardening import Finding

logger = logging.getLogger(__name__)

_binary: str | None = shutil.which("trufflehog") or shutil.which("trufflehog", path=str(Path.home() / ".local" / "bin"))


async def run(repo_path: str, config: dict | None = None) -> list[Finding]:
    """Run TruffleHog against repo_path. Returns [] gracefully if not installed."""
    if not _binary:
        return []

    cmd = [_binary, "filesystem", "--json", "--no-update", repo_path]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        return _parse(stdout or b"", repo_path)
    except Exception as exc:
        logger.debug("TruffleHog failed (non-fatal): %s", exc)
        return []


def _parse(raw: bytes, repo_path: str) -> list[Finding]:
    """TruffleHog outputs one JSON object per line (NDJSON)."""
    out: list[Finding] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            source = r.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {})
            path = source.get("file", "").replace(repo_path.rstrip("/") + "/", "")
            line_no = source.get("line")
            detector = r.get("DetectorName", "unknown")
            out.append(
                Finding(
                    discipline="security",
                    severity="critical",
                    file=path,
                    line=line_no,
                    # Credential value deliberately omitted — redacted for safety
                    message=f"Secret detected: {detector} — credential value redacted",
                    tool="trufflehog",
                    rule_id=detector,
                    fix_command="Remove credential from file and rotate immediately.",
                )
            )
        except Exception:
            continue
    return out
