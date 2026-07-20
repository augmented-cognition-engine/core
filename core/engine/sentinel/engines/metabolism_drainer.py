"""Sentinel engine: Grounding Metabolism Drainer.

Drains the reeval_request queue every 15 minutes. Each pending request is a
belief whose canvas ground shifted (enqueued by persistence.upsert_artifact when
a grounded canvas_artifact changes); draining marks the belief freshness-stale so
it surfaces as needing re-evaluation. This engine is the unattended half of the
grounding metabolism — the enqueue side is event-driven, the drain side is this.

Spec: docs/superpowers/specs/2026-07-15-grounding-metabolism-design.md
"""

from __future__ import annotations

import logging

from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


@register_engine(
    "metabolism_drainer",
    "*/15 * * * *",
    "Drain the grounding re-evaluation queue — mark beliefs whose canvas ground shifted freshness-stale",
)
async def run_metabolism_drainer(product_id: str = "product:platform") -> dict:
    """Drain pending re-evaluation requests.

    Global — the queue is not product-scoped (beliefs and canvas objects span
    products), and the drain is idempotent, so per-product invocations after the
    first in a sweep are no-ops.
    """
    from core.engine.graph.metabolism import drain_reeval

    drained = await drain_reeval()
    if drained:
        logger.info("metabolism_drainer: drained %d re-evaluation request(s)", drained)
    return {"drained": drained}
