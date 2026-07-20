"""Bind CoverageRow records to capabilities and persist as capability_coverage.

Pipeline:
1. For each CoverageRow: resolve file → capability via realizes edges
2. Aggregate per capability × dimension (line, branch, function)
3. UPSERT capability_coverage (current state) + INSERT capability_coverage_snapshot (history)
4. For each untested function: write capability_finding with tool='coverage'
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


@dataclass
class CapabilityCoverage:
    capability_id: str
    capability_slug: str
    line_pct: float
    branch_pct: float
    function_pct: float
    files_count: int
    untested_functions_count: int


async def bind_and_persist(
    rows: list,
    product_id: str,
    scan_id: str | None = None,
) -> dict:
    """Bind coverage rows to capabilities and persist results.

    Returns: {scan_id, capabilities_updated, findings_created, snapshots_written}
    """
    scan_id = scan_id or str(uuid.uuid4())
    file_to_cap = await _resolve_file_capabilities([r.file for r in rows], product_id)

    per_cap: dict[str, list] = defaultdict(list)
    for row in rows:
        cap_id = file_to_cap.get(row.file)
        if cap_id:
            per_cap[cap_id].append(row)

    capabilities_updated = 0
    snapshots_written = 0
    findings_created = 0

    async with pool.connection() as db:
        for cap_id, cap_rows in per_cap.items():
            agg = _aggregate(cap_rows)
            cov_slug = f"{cap_id.split(':')[-1]}__cov__{product_id.replace(':', '_')}"

            await db.query(
                """UPSERT type::record('capability_coverage', $slug) SET
                    capability = <record>$cap_id,
                    product = <record>$product,
                    line_pct = $line_pct,
                    branch_pct = $branch_pct,
                    function_pct = $function_pct,
                    files_count = $files,
                    untested_functions_count = $untested,
                    scan_id = $scan_id,
                    assessed_at = time::now()
                """,
                {
                    "slug": cov_slug,
                    "cap_id": cap_id,
                    "product": product_id,
                    "line_pct": agg["line_pct"],
                    "branch_pct": agg["branch_pct"],
                    "function_pct": agg["function_pct"],
                    "files": agg["files"],
                    "untested": agg["untested"],
                    "scan_id": scan_id,
                },
            )
            capabilities_updated += 1

            await db.query(
                """CREATE capability_coverage_snapshot SET
                    capability = <record>$cap_id,
                    product = <record>$product,
                    line_pct = $line_pct,
                    branch_pct = $branch_pct,
                    function_pct = $function_pct,
                    scan_id = $scan_id,
                    assessed_at = time::now()
                """,
                {
                    "cap_id": cap_id,
                    "product": product_id,
                    "line_pct": agg["line_pct"],
                    "branch_pct": agg["branch_pct"],
                    "function_pct": agg["function_pct"],
                    "scan_id": scan_id,
                },
            )
            snapshots_written += 1

            for cov_row in cap_rows:
                for fn_name in cov_row.untested_functions:
                    sev = _severity_for_untested(agg["function_pct"])
                    await db.query(
                        """CREATE capability_finding SET
                            product = <record>$product,
                            capability = <record>$cap_id,
                            discipline = 'testing',
                            severity = $sev,
                            file = $file,
                            line = NONE,
                            message = $msg,
                            rule_id = 'coverage:no-test-reference',
                            fix_command = $fix,
                            tool = 'coverage',
                            scan_id = $scan_id,
                            created_at = time::now()
                        """,
                        {
                            "product": product_id,
                            "cap_id": cap_id,
                            "sev": sev,
                            "file": cov_row.file,
                            "msg": f"Function {fn_name!r} has no test reference",
                            "fix": "ace_generate_tests(mode='priority')",
                            "scan_id": scan_id,
                        },
                    )
                    findings_created += 1

    return {
        "scan_id": scan_id,
        "capabilities_updated": capabilities_updated,
        "findings_created": findings_created,
        "snapshots_written": snapshots_written,
    }


async def _resolve_file_capabilities(files: list[str], product_id: str) -> dict[str, str]:
    """file path → capability id via graph_file → realizes → capability."""
    if not files:
        return {}
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT gf.path AS path, r.out AS cap_id
                FROM graph_file AS gf
                JOIN realizes AS r ON r.in = gf.id
                JOIN capability AS cap ON cap.id = r.out
                WHERE gf.path IN $files
                AND cap.product = <record>$product
                """,
                    {"files": files, "product": product_id},
                )
            )
        return {r["path"]: str(r["cap_id"]) for r in rows if r.get("cap_id")}
    except Exception as exc:
        logger.debug("File capability resolution failed: %s", exc)
        return {}


def _aggregate(rows: list) -> dict:
    """Aggregate per-file rows to a single capability-level dict."""
    lc = sum(r.lines_covered for r in rows)
    lt = sum(r.lines_total for r in rows)
    bc = sum(r.branches_covered for r in rows)
    bt = sum(r.branches_total for r in rows)
    fc = sum(r.functions_covered for r in rows)
    ft = sum(r.functions_total for r in rows)
    return {
        "line_pct": lc / lt if lt else 0.0,
        "branch_pct": bc / bt if bt else 0.0,
        "function_pct": fc / ft if ft else 0.0,
        "files": len(rows),
        "untested": sum(len(r.untested_functions) for r in rows),
    }


def _severity_for_untested(function_pct: float) -> str:
    """Untested functions are higher severity in already-poorly-covered capabilities."""
    if function_pct < 0.3:
        return "high"
    if function_pct < 0.6:
        return "medium"
    return "low"
