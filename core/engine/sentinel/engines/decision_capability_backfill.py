"""Nightly decision capability backfill sentinel.

Drift-catcher: re-infers any decisions created in the last 24h that somehow
shipped without affected_capabilities tags.

Designed to catch bypasses around the synthesizer (e.g., tests, scripts, partner
integrations) that create decision rows without populating affected_capabilities.

Spec: docs/superpowers/specs/2026-05-14-layer5-context-assembly-design.md §6.8
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows
from core.engine.core.db import pool as default_pool
from core.engine.intelligence.decision_capability_inference import infer_capabilities_for_decisions
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


@register_engine(
    name="decision_capability_backfill",
    cron="0 4 * * *",
    description="Nightly decision capability backfill — re-infers any decisions created in the last 24h without affected_capabilities",
)
async def decision_capability_backfill(product_id: str = "product:platform") -> dict:
    """Nightly drift-catcher. Re-infers any decisions created in the last 24h
    that somehow shipped without affected_capabilities tags.

    This catches code paths that bypass the synthesizer (e.g. tests, scripts,
    partner integrations) and create decision rows without the required fields.

    Args:
        product_id: the scheduler contract — every engine fn is invoked as fn(product_id). The 24h
            drift query is global (not product-scoped), so the pool is acquired internally; the arg
            exists only to match the calling convention. (The prior `pool` signature was the bug that
            made every 04:00 cron fire AttributeError on `"product:platform".connection()`.)

    Returns:
        dict with "inferred" (count of rows processed) and "errors" (count of
        rows that had inference failures).
    """
    pool = default_pool
    async with pool.connection() as db:
        result = await db.query(
            """SELECT id, title, rationale, decision_type, discipline_hint, created_at
               FROM decision
               WHERE affected_capabilities_inferred_at IS NONE
                 AND created_at > time::now() - 24h"""
        )
    rows = parse_rows(result)
    if not rows:
        return {"inferred": 0, "errors": 0}

    inference = await infer_capabilities_for_decisions(decision_rows=rows, pool=pool)
    return {"inferred": inference.inferred, "errors": inference.errored}
