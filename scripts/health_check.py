#!/usr/bin/env python3
"""Health check script — finds dangling record links and stuck engine runs.

Usage: uv run python scripts/health_check.py
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_dangling_links(db) -> list[dict]:
    """Find record links pointing to non-existent records."""
    checks = [
        ("insight", "domain", "domain"),
        ("synapse", "in", "subdomain"),
        ("synapse", "out", "subdomain"),
    ]
    dangling = []
    for table, field, target_table in checks:
        try:
            result = await db.query(
                f"""
                SELECT id, {field} FROM {table}
                WHERE {field} IS NOT NONE
                  AND {field} NOT IN (SELECT id FROM {target_table})
                """,
            )
            rows = result[0] if result and isinstance(result[0], list) else []
            rows = [r for r in rows if isinstance(r, dict)]
            if rows:
                dangling.append({"table": table, "field": field, "count": len(rows)})
        except Exception as exc:
            logger.warning("Skip check %s.%s: %s", table, field, exc)
    return dangling


async def check_stuck_engine_runs(db) -> list[dict]:
    """Find engine_run records stuck in 'running' state for >1 hour."""
    try:
        result = await db.query(
            """
            SELECT id, engine, started_at FROM engine_run
            WHERE status = 'running' AND started_at < time::now() - 1h
            """,
        )
        rows = result[0] if result and isinstance(result[0], list) else []
        return [r for r in rows if isinstance(r, dict)]
    except Exception:
        return []


async def main():
    from core.engine.core.db import pool

    await pool.init()

    async with pool.connection() as db:
        dangling = await check_dangling_links(db)
        stuck = await check_stuck_engine_runs(db)

    await pool.close()

    if dangling:
        for d in dangling:
            logger.warning("Dangling links: %s.%s → %d records", d["table"], d["field"], d["count"])
    else:
        logger.info("No dangling record links found")

    if stuck:
        for s in stuck:
            logger.warning("Stuck engine run: %s (%s, started %s)", s["id"], s["engine"], s["started_at"])
    else:
        logger.info("No stuck engine runs found")


if __name__ == "__main__":
    asyncio.run(main())
