"""Roadmap staleness — decay (recommendation_decay) + supersession (Graph Tensions edges)."""

from __future__ import annotations

import logging

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.product.recommendation_decay import apply_decay
from core.engine.product.roadmap_models import RoadmapItem, RoadmapStaleness

logger = logging.getLogger(__name__)

_DECAY_DROP_THRESHOLD = 0.15  # rank lost to decay beyond which an item is "stale at the top"


def assess_decay(item: RoadmapItem) -> RoadmapStaleness:
    """Pure: DECAYED if repeated surfacing has eroded the rank past the threshold."""
    decayed_rank = apply_decay(item.rank, item.cbt)
    if (item.rank - decayed_rank) >= _DECAY_DROP_THRESHOLD:
        return RoadmapStaleness.DECAYED
    return RoadmapStaleness.FRESH


async def lookup_spec_status(item: RoadmapItem, db) -> tuple[str | None, bool]:
    """Return (spec_status, superseded). Non-fatal → (None, False).

    agent_spec has a direct `capability` field (record<capability>).
    Capabilities are keyed by slug; the item's capability_slug is that slug
    (e.g. "closed-loop-learning"), NOT the dimension ("error_handling").
    Superseded = the spec has an incoming reverts/supersedes/breaks edge.

    Schema notes (confirmed against core/schema/):
      - agent_spec.status: string DEFAULT 'draft' (draft|approved|building|shipped|superseded)
      - specified_by: in=record<agent_spec>, out=record (generic; capability has no pillar/discipline)
      - agent_spec.capability: option<record<capability>> — direct foreign key to capability record
      - capability.slug: string — used as the lookup key (matches item.capability_slug)
    """
    try:
        slug = item.capability_slug or ""
        if not slug:
            return None, False

        rows = parse_rows(
            await db.query(
                "SELECT id, status FROM agent_spec WHERE capability.slug = <string>$slug LIMIT 1",
                {"slug": slug},
            )
        )
        if not rows:
            return None, False

        spec_id_raw = str(rows[0].get("id", ""))
        status = rows[0].get("status")
        superseded = False

        if spec_id_raw:
            spec_rid = parse_record_id(spec_id_raw)
            for et in ("reverts", "supersedes", "breaks"):
                hit = parse_rows(
                    await db.query(
                        f"SELECT id FROM {et} WHERE out = $sid LIMIT 1",
                        {"sid": spec_rid},
                    )
                )
                if hit:
                    superseded = True
                    break

        return status, superseded
    except Exception as exc:
        logger.debug("roadmap spec lookup failed (non-fatal): %s", exc)
        return None, False
