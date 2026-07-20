"""ace_product_pulse — the open extension's read-only MCP tool.

Answers the question every PM wakes up asking: "what's worth working on for my
product right now?" Sources from existing kernel data (product health + recent
decisions + pending gaps). No new tables, no LLM calls, no side-effects.

Adopter value > slot-filler. Each item carries a brief rationale so the answer
is actionable, not just a list.
"""

from __future__ import annotations

from typing import Any

DEFAULT_ORG = "product:platform"
PULSE_LIMIT = 5


async def _load_product_health(product_id: str) -> dict[str, Any]:
    """Pull the kernel's product-health summary. Best-effort; returns {} on error."""
    try:
        from core.engine.core.db import pool
        from core.engine.product.map import ProductMap

        return await ProductMap(pool).health_summary(product_id) or {}
    except Exception:
        return {}


async def _load_recent_decisions(product_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Pull recent decisions for the product. Best-effort; returns [] on error."""
    try:
        from core.engine.core.db import pool
        from core.engine.product.decisions import list_decisions

        return await list_decisions(product_id, limit=limit, pool=pool) or []
    except Exception:
        return []


async def _load_pending_gaps(product_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Pull pending capability gaps for the product. Best-effort; returns []."""
    try:
        from core.engine.core.db import parse_rows, pool

        async with pool.connection() as db:
            rows = await db.query(
                "SELECT capability, dimension, score, gaps "
                "FROM capability_quality "
                "WHERE capability IN (SELECT id FROM capability WHERE product = <record>$product) "
                "ORDER BY score ASC LIMIT $limit",
                {"product": product_id, "limit": limit},
            )
        return parse_rows(rows) or []
    except Exception:
        return []


async def ace_product_pulse(product_id: str = DEFAULT_ORG) -> dict[str, Any]:
    """Top 3-5 things worth working on for the product right now.

    Combines product health (the current focus), recent decisions (what's in
    motion), and pending gaps (what's underweight). Each item has:
      - title:     short label
      - source:    "health" | "decision" | "gap"
      - rationale: one-line "why this matters"
    """
    health = await _load_product_health(product_id)
    decisions = await _load_recent_decisions(product_id, limit=PULSE_LIMIT)
    gaps = await _load_pending_gaps(product_id, limit=PULSE_LIMIT)

    items: list[dict[str, Any]] = []

    if health.get("focus"):
        items.append(
            {
                "title": str(health["focus"]),
                "source": "health",
                "rationale": f"product health status: {health.get('status', 'unknown')}",
            }
        )

    for d in decisions[:2]:
        title = d.get("title") or "(untitled decision)"
        items.append(
            {
                "title": str(title),
                "source": "decision",
                "rationale": str(d.get("rationale") or "recent decision in motion"),
            }
        )

    for g in gaps[:2]:
        title = g.get("dimension") or g.get("title") or "(unspecified gap)"
        items.append(
            {
                "title": f"close gap: {title}",
                "source": "gap",
                "rationale": f"quality score {g.get('score', 0.0):.2f} — below threshold",
            }
        )

    return {"items": items[:PULSE_LIMIT]}
