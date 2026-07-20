# engine/graph/insight_writer.py
"""Graph insight write helper — write insight edges to real tables.

Called from synthesizer and sentinel engines after writing to the insight table.
Shadow graph_insight table is retired (Phase 3); only real-table edges are written.
All writes are best-effort: errors must never propagate to callers.
"""

from __future__ import annotations

import logging
import re

from surrealdb import RecordID

from core.engine.core.db import parse_one, pool

logger = logging.getLogger(__name__)


def _slugify_id(insight_id: str) -> str:
    """Derive a stable slug from a SurrealDB record ID string.

    Examples:
      "insight:abc123"  -> "insight_abc123"
      "insight:⟨abc-123⟩" -> "insight_abc_123"
    """
    # Strip table prefix if present
    if ":" in insight_id:
        _, _, record_part = insight_id.partition(":")
    else:
        record_part = insight_id

    # Strip SurrealDB angle-bracket escaping: ⟨...⟩ or <...>
    record_part = record_part.strip("⟨⟩<>")

    # Replace non-alphanumeric chars with underscores
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", record_part).strip("_")
    return slug or "unknown"


async def write_insight_to_graph(
    insight_id: str,
    content: str,
    insight_type: str,
    confidence: float,
    source: str,  # "capture", "scanner", "agent", "overnight"
    tags: list[str],
    specialty_slug: str | None = None,
    task_id: str | None = None,
    graph_id: str = "default",
    db_pool=None,
) -> dict | None:
    """Write insight edges to the graph (real tables only).

    Creates:
    - If specialty_slug provided: RELATE insight -> informed_by -> specialty

    The graph_insight shadow table and graph_task -> produced -> graph_insight
    edges are retired (Phase 3).

    Args:
        insight_id:     The insight record ID (e.g. "insight:abc123").
        content:        The insight text.
        insight_type:   Type: solution, problem, error, fix, code_pattern,
                        fact, pattern, decision, correction, preference, convention, discovery.
        confidence:     Float 0.0-1.0.
        source:         Provenance tag -- "capture", "scanner", "agent", "overnight".
        tags:           List of tag strings.
        specialty_slug: If set, RELATE the insight as informed_by this specialty.
        task_id:        Retained for API compatibility (no longer writes edges).
        graph_id:       Graph partition identifier (default "default").
        db_pool:        Optional pool override (uses global pool when None).

    Returns:
        A dict with the insight_id and edges written, or None on failure.
    """
    _pool = db_pool or pool

    try:
        async with _pool.connection() as db:
            edges: list[str] = []

            # RELATE insight -> informed_by -> specialty (if specialty_slug)
            if specialty_slug:
                spec_real = await db.query(
                    "SELECT id FROM specialty WHERE slug = <string>$slug LIMIT 1",
                    {"slug": specialty_slug},
                )
                spec_real_row = parse_one(spec_real)
                if spec_real_row:
                    table, _, key = str(insight_id).partition(":")
                    await db.query(
                        "RELATE $insight -> informed_by -> $spec SET source = 'capture', created_at = time::now()",
                        {"insight": RecordID(table, key), "spec": spec_real_row["id"]},
                    )
                    edges.append("informed_by")
                else:
                    logger.debug("specialty not found for slug=%s -- skipping edge", specialty_slug)

            return {
                "insight_id": insight_id,
                "edges": edges,
            }

    except Exception as exc:
        logger.warning("write_insight_to_graph failed for insight_id=%s: %s", insight_id, exc)
        return None
