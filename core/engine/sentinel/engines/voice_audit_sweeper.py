"""Sentinel engine: voice audit sweeper. Runs every 30 minutes per active product."""

from __future__ import annotations

import logging

from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


@register_engine(
    "voice_audit_sweeper",
    "*/30 * * * *",
    "Run voice consistency audit per product every 30 minutes",
)
async def run_voice_audit_sweeper(product_id: str = "product:platform") -> dict:
    from core.engine.core.db import pool
    from core.engine.voice.audit_runner import run_audit

    summary = await run_audit(pool, product_id, trigger="sweeper", persist=True)
    logger.info(
        "voice_audit_sweeper: %s — overall %s, violations %d",
        product_id,
        summary["overall_score"],
        len(summary["violations"]),
    )
    return summary
