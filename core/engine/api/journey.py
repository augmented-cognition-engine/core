"""Journey API — /portal/journey/{product_id} for the reasoning activity feed."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from core.engine.api._portal_security import verify_product_access
from core.engine.cognition.active_discipline import find_active_discipline
from core.engine.cognition.composition_headline import compose_headline
from core.engine.cognition.handoff import find_active_handoff
from core.engine.cognition.journey_voice import UnknownTopicError, render_summary
from core.engine.core.db import parse_record_id, parse_rows, pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal/journey", tags=["journey"])


_SINCE_TO_INTERVAL = {
    "day": "1d",
    "week": "7d",
    "month": "30d",
}


@router.get("/{product_id}")
async def get_journey(
    product_id: str,
    since: str = "month",
    topics: str | None = None,
    meta_skill: str | None = None,
    before: str | None = None,
    user=Depends(verify_product_access),
) -> dict:
    """Return the activity feed for a product. Pagination via `before=<event_id>` cursor."""
    interval = _SINCE_TO_INTERVAL.get(since, "30d")
    topic_filter = [t.strip() for t in topics.split(",")] if topics else None

    async with pool.connection() as db:
        # 1. journey_event rows in window (server-side filter)
        params: dict = {"pid": product_id}
        before_clause = ""
        if before:
            before_clause = "AND id < $before "
            params["before"] = parse_record_id(before)
        query = (
            "SELECT id, topic, payload, occurred_at, composition_trace "
            "FROM journey_event WHERE product = <record>$pid "
            f"AND occurred_at > time::now() - {interval} "
            f"{before_clause}"
            "ORDER BY occurred_at DESC LIMIT 200"
        )
        rows = parse_rows(await db.query(query, params))

        if topic_filter:
            rows = [r for r in rows if r["topic"] in topic_filter]
        if meta_skill:
            rows = [
                r
                for r in rows
                if r.get("composition_trace") and meta_skill in (r["composition_trace"].get("meta_skills") or [])
            ]

        # 2. Edges referencing any of these events
        event_ids = [str(r["id"]) for r in rows]
        edges_in: dict[str, list] = {eid: [] for eid in event_ids}
        edges_out: dict[str, list] = {eid: [] for eid in event_ids}
        if event_ids:
            edge_rows = parse_rows(
                await db.query(
                    "SELECT from_event, to_event, edge_type, confidence FROM reasoning_edge "
                    "WHERE product = <record>$pid",
                    {"pid": product_id},
                )
            )
            for e in edge_rows:
                fid, tid = str(e["from_event"]), str(e["to_event"])
                if tid in edges_in:
                    edges_in[tid].append(
                        {"from_event": fid, "edge_type": e["edge_type"], "confidence": e["confidence"]}
                    )
                if fid in edges_out:
                    edges_out[fid].append({"to_event": tid, "edge_type": e["edge_type"], "confidence": e["confidence"]})

    # Render summaries
    events_out = []
    for r in rows:
        eid = str(r["id"])
        try:
            summary = render_summary(r["topic"], r["payload"] or {}, r.get("composition_trace"))
        except UnknownTopicError:
            logger.warning("journey: unknown topic %s on event %s", r["topic"], eid)
            summary = f"[unknown topic: {r['topic']}]"
        trace = r.get("composition_trace")
        headline = None
        if trace:
            try:
                headline = compose_headline(trace)
            except ValueError:
                # Trace exists but doesn't satisfy compose_headline's contract;
                # render the structured detail without a headline.
                headline = None
        events_out.append(
            {
                "id": eid,
                "topic": r["topic"],
                "occurred_at": r["occurred_at"].isoformat()
                if hasattr(r["occurred_at"], "isoformat")
                else str(r["occurred_at"]),
                "summary": summary,
                "composition_trace": trace,
                "composition_headline": headline,
                "edges_in": edges_in[eid],
                "edges_out": edges_out[eid],
            }
        )

    active_discipline = find_active_discipline(events_out)
    active_handoff = find_active_handoff(events_out)

    return {
        "events": events_out,
        "active_discipline": active_discipline,
        "active_handoff": active_handoff,
    }
