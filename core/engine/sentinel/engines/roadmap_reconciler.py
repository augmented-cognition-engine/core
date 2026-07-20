# core/engine/sentinel/engines/roadmap_reconciler.py
"""Keeps the canonical roadmap (strategy_ingest agent_specs + roadmap_phase) coherent.

Re-ingests the strategy docs->graph (idempotent + now status-monotonic, so it never regresses
live progress — see strategy_ingest.PROTECTED_STATUSES) and surfaces drift: how many specs are
draft/approved and may need human verification against shipped work. It does NOT guess "shipped"
from git (fuzzy, risky) — that's surfaced for review, not auto-applied (deepen-only-style safety).

Self-healing, idempotent, non-fatal. NOTE: the scheduler builds cron jobs from engine_registry at
start(), populated by the EXPLICIT import block in core/engine/api/main.py — so this module must be
imported there to actually run (pkgutil discovery in api/sentinels.py is lazy/post-start and
schedules nothing). It IS wired in main.py; tests/test_roadmap_reconciler.py guards that.

See docs/superpowers/specs/2026-06-22-roadmap-reconciler-design.md
"""

from __future__ import annotations

import logging
from collections import Counter

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.core.db import pool as default_pool
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

_OPEN_STATUSES = ("draft", "approved")  # may be shipped-but-unmarked — surfaced for review


async def _drift_summary(product_id: str, pool=None) -> dict:
    """Roadmap drift signal: strategy_ingest spec counts by status + the open-for-review count."""
    pool = pool or default_pool
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT status FROM agent_spec WHERE product = $p AND source = 'strategy_ingest'",
                {"p": parse_record_id(product_id)},
            )
        )
    by_status = dict(Counter((r.get("status") or "unknown") for r in rows))
    open_for_review = sum(v for k, v in by_status.items() if k in _OPEN_STATUSES)
    return {"total": len(rows), "by_status": by_status, "open_for_review": open_for_review}


@register_engine(
    name="roadmap_reconciler",
    cron="0 * * * *",
    description="Re-ingest strategy docs→graph (status-monotonic) + surface roadmap drift (hourly)",
)
async def run(product_id: str) -> dict:
    """Sentinel entry point — keep the roadmap synced + report drift. Fully non-fatal."""
    synced: dict = {}
    drift: dict = {}
    try:
        from core.engine.product.strategy_ingest import seed_session_strategy

        synced = await seed_session_strategy(product_id)
    except Exception as exc:
        logger.warning("roadmap_reconciler: docs→graph sync failed (non-fatal): %s", exc)
    try:
        drift = await _drift_summary(product_id)
    except Exception as exc:
        logger.warning("roadmap_reconciler: drift summary failed (non-fatal): %s", exc)
    return {"synced": synced, "drift": drift}
