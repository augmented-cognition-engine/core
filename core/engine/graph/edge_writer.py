# engine/graph/edge_writer.py
"""Centralized edge creation — all new RELATION edges go through here.

Best-effort: never raises, never blocks the caller.
Deduplicates: checks for existing edge before creating.
Timestamped: adds created_at to every edge.
"""

from __future__ import annotations

import logging
from typing import Any

from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _validate_edge_inputs(edge_type: str, from_id: str, to_id: str) -> None:
    """Validate edge creation inputs before issuing SurrealDB RELATE queries.

    Raises ValidationError for empty or whitespace-only identifiers — a blank
    edge_type would make the RELATE statement syntactically invalid, and blank
    node IDs would create dangling edges that break graph traversal queries.
    """
    if not edge_type or not edge_type.strip():
        raise ValidationError("edge_type must be non-empty")
    if not from_id or not from_id.strip():
        raise ValidationError("from_id must be non-empty")
    if not to_id or not to_id.strip():
        raise ValidationError("to_id must be non-empty")


async def create_edge(
    edge_type: str,
    from_id: str,
    to_id: str,
    metadata: dict[str, Any] | None = None,
    pool=None,
) -> dict | None:
    """Create a single RELATION edge. Returns the created edge or None.

    - Deduplicates: skips if edge already exists between from_id and to_id.
    - Best-effort: catches all exceptions, logs at DEBUG.
    - Timestamped: always sets created_at = time::now().
    """
    try:
        _validate_edge_inputs(edge_type, from_id, to_id)
    except ValidationError as exc:
        logger.debug("Skipping invalid edge (%s -> %s): %s", from_id, to_id, exc)
        return None

    if pool is None:
        from core.engine.core.db import pool as default_pool

        pool = default_pool

    try:
        async with pool.connection() as db:
            # Check for existing edge
            from core.engine.core.db import parse_record_id, parse_rows

            # SurrealDB v3 rejects `RELATE <record>$param` (parse error: unexpected
            # `<`) and does not coerce string params to record refs. Bind RecordID
            # objects and drop the cast — the RELATE endpoints MUST be records.
            # (atomic_capture_write already does this; create_edge was the straggler
            # still using <record>$x, so every edge it wrote silently no-op'd.)
            from_rec = parse_record_id(from_id)
            to_rec = parse_record_id(to_id)

            existing = await db.query(
                f"SELECT id FROM {edge_type} WHERE in = $from_id AND out = $to_id LIMIT 1",
                {"from_id": from_rec, "to_id": to_rec},
            )
            if parse_rows(existing):
                logger.debug("Edge %s already exists: %s -> %s", edge_type, from_id, to_id)
                return None

            # Build SET clause
            set_parts = ["created_at = time::now()"]
            params: dict[str, Any] = {"from_id": from_rec, "to_id": to_rec}

            if metadata:
                for key, value in metadata.items():
                    set_parts.append(f"{key} = ${key}")
                    params[key] = value

            set_clause = ", ".join(set_parts)
            result = await db.query(
                f"RELATE $from_id -> {edge_type} -> $to_id SET {set_clause}",
                params,
            )
            from core.engine.core.db import parse_one

            return parse_one(result)

    except Exception as exc:
        logger.debug("Edge creation failed (%s: %s -> %s): %s", edge_type, from_id, to_id, exc)
        return None


async def create_edges(
    edges: list[tuple[str, str, str]],
    metadata: dict[str, Any] | None = None,
    pool=None,
) -> None:
    """Create multiple edges. Each tuple is (edge_type, from_id, to_id).

    Best-effort per edge — failures don't stop remaining edges.
    """
    for edge_type, from_id, to_id in edges:
        await create_edge(edge_type, from_id, to_id, metadata=metadata, pool=pool)
