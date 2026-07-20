# core/engine/sentinel/engines/provenance_reconciler.py
"""Populates structured provenance (source_kind, source_ref, trust) for any active
insight that lacks it (trust IS NONE), derived from the source_domain every writer
already sets. Path-agnostic (covers all 6 insight writers), self-healing, idempotent.

No embedding/model work — pure-function compute — so it fetches and updates in one
connection (unlike the embedding reconciler, which must release the pool across
slow inference).

See docs/superpowers/specs/2026-06-15-ace-structured-provenance-trust-design.md
"""

from __future__ import annotations

import logging

from core.engine.capture.provenance import parse_source, trust_score
from core.engine.core.db import parse_rows, pool
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


async def reconcile_missing_provenance(limit: int = 500) -> int:
    """Score provenance for up to `limit` unscored active insights. Returns count."""
    scored = 0
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT id, source_domain FROM insight WHERE trust = NONE AND status = 'active' LIMIT $lim",
                {"lim": limit},
            )
        )
        for row in rows:
            kind, ref = parse_source(row.get("source_domain") or "")
            trust = trust_score(kind)
            try:
                await db.query(
                    "UPDATE <record>$id SET source_kind = $k, source_ref = $r, trust = $t, updated_at = time::now()",
                    {"id": str(row["id"]), "k": kind, "r": ref, "t": trust},
                )
                scored += 1
            except Exception:
                logger.warning("provenance reconcile failed for %s", row.get("id"), exc_info=True)
    return scored


@register_engine(
    name="provenance_reconciler",
    cron="*/15 * * * *",
    description="Derives structured provenance + trust for unscored insights (every 15 min)",
)
async def run(product_id: str) -> dict:
    """Sentinel entry point — global sweep ignores product_id."""
    n = await reconcile_missing_provenance()
    return {"scored": n}
