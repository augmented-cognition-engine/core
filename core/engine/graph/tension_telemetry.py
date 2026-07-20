# core/engine/graph/tension_telemetry.py
"""Telemetry for surfaced graph tensions — the ROI / intelligence-curve substrate.

Every surfacing writes a trace-linked graph_tension_event row, increments a
Prometheus counter, and emits an event. Fully non-fatal — a failed record never
affects the surface that produced it.
"""

from __future__ import annotations

import logging

from core.engine.core.db import pool
from core.engine.core.metrics import graph_tension_surfaced_total
from core.engine.events.bus import bus

logger = logging.getLogger(__name__)


async def record_tension_surfaces(graph_tensions: dict, surface: str, product_id: str) -> int:
    """Record each surfaced tension/consequence (table + metric + event). Returns count. Non-fatal."""
    items = [n for bucket in ("tensions", "consequences") for n in graph_tensions.get(bucket, [])]
    if not items:
        return 0
    try:
        from core.engine.core.otel import current_trace_id

        _tid = current_trace_id()
        trace_id = _tid if _tid not in ("-", "") else None
    except Exception:
        trace_id = None

    recorded = 0
    for n in items:
        rel = str(n.get("relationship", ""))
        frm = str(n.get("via_insight", ""))
        to = str(n.get("insight_id", ""))
        try:
            graph_tension_surfaced_total.labels(relationship=rel, surface=surface).inc()
        except Exception:
            pass
        try:
            async with pool.connection() as db:
                await db.query(
                    "CREATE graph_tension_event SET from_insight = $f, to_insight = $t, "
                    "relationship = $r, surface = $s, product = $p, trace_id = $tr, created_at = time::now()",
                    {"f": frm, "t": to, "r": rel, "s": surface, "p": product_id, "tr": trace_id},
                )
            recorded += 1
        except Exception as exc:
            logger.debug("tension telemetry row failed (non-fatal): %s", exc)
            continue
        try:
            await bus.emit(
                "graph.tension.surfaced",
                {"from": frm, "to": to, "relationship": rel, "surface": surface, "product_id": product_id},
            )
        except Exception:
            pass
    return recorded
