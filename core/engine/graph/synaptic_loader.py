# engine/graph/synaptic_loader.py
"""Cross-domain intelligence loading via confirmed synapses.

Called by the orchestrator loader as step 5 (after local tier walk).
Read-only — queries synapse + insight tables, writes nothing.

Spec: docs/superpowers/specs/2026-03-21-phase2a-synaptic-graph.md §5
"""

from __future__ import annotations

import logging
from math import floor

from core.engine.core.db import pool

logger = logging.getLogger(__name__)

_CROSS_DOMAIN_CAP = 15


def calculate_budget(strength: float) -> int:
    """Budget = max(1, floor(strength * 5)). Minimum 1 for any confirmed synapse."""
    return max(1, floor(strength * 5))


def apply_cross_domain_cap(insights: list[dict]) -> list[dict]:
    """Cap total cross-domain insights at 15."""
    return insights[:_CROSS_DOMAIN_CAP]


async def load_synaptic_intelligence(subdomain_id: str, product_id: str) -> list[dict]:
    """Load cross-domain insights from confirmed synaptic neighbors."""
    all_cross_domain = []

    async with pool.connection() as db:
        synapses_result = await db.query(
            """
            SELECT * FROM synapse
            WHERE (`in` = $sub OR `out` = $sub)
              AND confirmed = true
              AND product = <record>$product
            ORDER BY strength DESC
            """,
            {"sub": subdomain_id, "product": product_id},
        )

        synapses = (
            synapses_result[0] if synapses_result and isinstance(synapses_result[0], list) else (synapses_result or [])
        )

        for synapse in synapses:
            if len(all_cross_domain) >= _CROSS_DOMAIN_CAP:
                break

            # `in` is a Python reserved keyword — use dict access
            syn_in = synapse["in"] if isinstance(synapse, dict) else getattr(synapse, "in_", None)
            syn_out = synapse["out"] if isinstance(synapse, dict) else getattr(synapse, "out", None)

            connected = syn_out if str(syn_in) == str(subdomain_id) else syn_in
            if not connected:
                continue

            budget = calculate_budget(synapse.get("strength", 0))
            remaining = _CROSS_DOMAIN_CAP - len(all_cross_domain)
            budget = min(budget, remaining)

            insights_result = await db.query(
                """
                SELECT id, content, confidence, insight_type, tier, domain_hint
                FROM insight
                WHERE subdomain = $connected
                  AND status = 'active'
                  AND product = <record>$product
                  AND clearance = 'open'
                ORDER BY confidence DESC
                LIMIT $limit
                """,
                {"connected": connected, "product": product_id, "limit": budget},
            )

            insights = (
                insights_result[0]
                if insights_result and isinstance(insights_result[0], list)
                else (insights_result or [])
            )

            slug_result = await db.query(
                "SELECT slug FROM subdomain WHERE id = $id LIMIT 1",
                {"id": connected},
            )
            slug_rows = slug_result[0] if slug_result and isinstance(slug_result[0], list) else (slug_result or [])
            connected_slug = slug_rows[0].get("slug", "unknown") if slug_rows else "unknown"

            for insight in insights:
                all_cross_domain.append(
                    {
                        "insight_id": str(insight.get("id", "")),
                        "content": insight.get("content", ""),
                        "confidence": insight.get("confidence", 0),
                        "source_subdomain": str(connected),
                        "source_subdomain_slug": connected_slug,
                        "synapse_id": str(synapse.get("id", "")),
                        "synapse_strength": synapse.get("strength", 0),
                    }
                )

    return apply_cross_domain_cap(all_cross_domain)
