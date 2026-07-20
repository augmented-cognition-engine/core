"""Loop visibility timeline API — /portal/loop/{product_id}.

Cohort B #5. Renders ACE's working pattern across time as a vertical stack
of "iteration cards" — each card a partner-voice summary of a contiguous
burst of journey_event activity (events within ITERATION_GAP_SECONDS of
each other belong together).

Substrate is the existing journey_event stream — no new tables, no new
instrumentation. This endpoint just clusters and narrates.

Pure helpers live in engine/cognition/loop_iterations.py so clustering is
unit-testable without DB. This file owns query + auth + response shape.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends

from core.engine.api._portal_security import verify_product_access
from core.engine.cognition.loop_iterations import (
    cluster_events,
    compose_iteration_phrase,
    summarize_topics,
)
from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal/loop", tags=["loop"])


# Window → SurrealDB duration literal. SurrealDB v3 rejects BETWEEN, so we
# use occurred_at >= time::now() - <interval>. "today" maps to 24h for v1
# (timezone-aware "since 00:00 today" is a post-v1 polish).
_WINDOW_TO_INTERVAL: dict[str, str | None] = {
    "today": "1d",
    "day": "1d",
    "week": "7d",
    "all": None,
}


@router.get("/{product_id}")
async def get_loop_timeline(
    product_id: str,
    window: Literal["today", "day", "week", "all"] = "day",
    limit: int | None = None,
    user: dict = Depends(verify_product_access),
) -> dict:
    """Return iteration cards for a product's recent journey activity.

    Query params:
      window: today | day | week | all  (default: day)
      limit:  optional cap on the number of iterations returned. When set,
              we keep the most-recent `limit` iterations (the tail of the
              ASC-ordered list). Used by the Today-page tile.

    Response shape:
      {
        "iterations": [
          {started_at, ended_at, event_count, event_ids,
           topic_summary, phrase},
          ...
        ],
        "window": str,
        "generated_at": iso8601 str,
        "product_id": str,
      }
    """
    interval = _WINDOW_TO_INTERVAL.get(window)

    async with pool.connection() as db:
        # SurrealDB v3 traps:
        #   - ORDER BY column must appear in SELECT → include occurred_at.
        #   - Use >= (not BETWEEN) for the time bound.
        # ASC ordering is required by cluster_events(), which assumes the
        # input list is sorted by occurred_at ascending.
        if interval:
            query = (
                "SELECT id, topic, occurred_at "
                "FROM journey_event "
                "WHERE product = <record>$pid "
                f"AND occurred_at >= time::now() - {interval} "
                "ORDER BY occurred_at ASC"
            )
        else:
            query = (
                "SELECT id, topic, occurred_at FROM journey_event WHERE product = <record>$pid ORDER BY occurred_at ASC"
            )
        rows = parse_rows(await db.query(query, {"pid": product_id}))

    # Normalize row shape for cluster_events: {id, occurred_at (iso str), topic}.
    normalized: list[dict] = []
    for r in rows:
        occurred = r.get("occurred_at")
        if hasattr(occurred, "isoformat"):
            occurred_iso = occurred.isoformat()
        else:
            occurred_iso = str(occurred) if occurred is not None else ""
        normalized.append(
            {
                "id": str(r.get("id", "")),
                "occurred_at": occurred_iso,
                "topic": r.get("topic") or "activity",
            }
        )

    iterations = cluster_events(normalized)

    # Tail-limit when caller asks for a small N (Today-tile use case).
    # Input is ASC, so most-recent iterations are at the end.
    if limit is not None and limit >= 0:
        iterations = iterations[-limit:] if limit > 0 else []

    cards: list[dict] = []
    for it in iterations:
        topics = it.get("topics") or {}
        cards.append(
            {
                "started_at": it.get("started_at", ""),
                "ended_at": it.get("ended_at", ""),
                "event_count": len(it.get("event_ids") or []),
                "event_ids": list(it.get("event_ids") or []),
                "topic_summary": summarize_topics(topics),
                "phrase": compose_iteration_phrase(it),
            }
        )

    return {
        "iterations": cards,
        "window": window,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_id": product_id,
    }
