# engine/sentinel/findings.py
"""D1 — Sentinel-layer findings writer.

Bridges static analysis output (E2) into the diagnostics layer.
Resolves file paths to capabilities via realizes edges, then writes
normalized findings to capability_finding table.

Used by the gap_analyzer integration path and the ace_scan_hardening
post-processing pipeline.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def write_findings(
    findings: list[dict],
    product_id: str,
    db_pool=None,
) -> int:
    """Write normalized static analysis findings to capability_finding table.

    Each finding dict: {discipline, severity, file, line, col, message,
                        fix_command, tool, rule_id, scan_id}

    Resolves capability from file path via graph_file → realizes → capability.
    Silently skips findings whose file path has no realizes edge (logs warning).

    Args:
        findings:    List of normalized finding dicts (from E2 hardening runner).
        product_id:  Product context for capability linking.
        db_pool:     Optional pool override (defaults to engine.core.db.pool).

    Returns: count written
    """
    if not findings:
        return 0

    if db_pool is None:
        from core.engine.core.db import pool as db_pool  # type: ignore[assignment]

    written = 0
    skipped = 0

    async with db_pool.connection() as db:
        for f in findings:
            file_path = f.get("file", "")
            cap_id = await _resolve_capability(file_path, db)

            if not cap_id:
                skipped += 1
                logger.debug("findings.write_findings: no capability for file %r — skipped", file_path)
                continue

            await db.query(
                """CREATE capability_finding SET
                    product      = <record>$product,
                    capability   = <record>$capability,
                    discipline   = $discipline,
                    severity     = $severity,
                    file         = $file,
                    line         = $line,
                    col          = $col,
                    message      = $message,
                    rule_id      = $rule_id,
                    fix_command  = $fix_command,
                    tool         = $tool,
                    scan_id      = $scan_id,
                    created_at   = time::now()
                """,
                {
                    "product": product_id,
                    "capability": cap_id,
                    "discipline": f.get("discipline", ""),
                    "severity": f.get("severity", "low"),
                    "file": file_path,
                    "line": f.get("line"),
                    "col": f.get("col"),
                    "message": (f.get("message") or "")[:500],
                    "rule_id": f.get("rule_id") or None,
                    "fix_command": f.get("fix_command") or None,
                    "tool": f.get("tool", "unknown"),
                    "scan_id": f.get("scan_id", ""),
                },
            )
            written += 1

    if skipped:
        logger.info("write_findings: wrote %d, skipped %d (no realizes edge)", written, skipped)
    return written


async def _resolve_capability(file_path: str, db) -> str | None:
    """Find capability ID for a file path via graph_file → realizes → capability.

    SELECT out AS cap FROM realizes
    WHERE in = (SELECT id FROM graph_file WHERE path = $file LIMIT 1) LIMIT 1

    Returns capability ID string or None.
    """
    if not file_path:
        return None
    try:
        from core.engine.core.db import parse_rows

        rows = parse_rows(
            await db.query(
                """SELECT out AS cap FROM realizes
                   WHERE in = (
                       SELECT id FROM graph_file WHERE path = <string>$file LIMIT 1
                   ) LIMIT 1""",
                {"file": file_path},
            )
        )
        cap = rows[0].get("cap") if rows else None
        return str(cap) if cap else None
    except Exception as exc:
        logger.debug("_resolve_capability failed for %r: %s", file_path, exc)
        return None
