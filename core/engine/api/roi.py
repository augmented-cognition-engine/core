"""REST API for ROI tracking — intelligence value measurement."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(prefix="/roi", tags=["roi"])


@router.get("")
async def get_roi(product: str = Query(...), user=Depends(get_current_user)):
    """ROI summary: this_week, this_month, all_time with events and hours_saved."""
    async with pool.connection() as db:
        # This week
        week_result = await db.query(
            """
            SELECT event_type, count() AS count,
                   math::sum(estimated_time_saved_minutes) AS minutes_saved
            FROM roi_event
            WHERE product = <record>$product AND created_at > time::now() - 7d
            GROUP BY event_type
            """,
            {"product": product},
        )
        week_rows = parse_rows(week_result)

        # This month
        month_result = await db.query(
            """
            SELECT event_type, count() AS count,
                   math::sum(estimated_time_saved_minutes) AS minutes_saved
            FROM roi_event
            WHERE product = <record>$product AND created_at > time::now() - 30d
            GROUP BY event_type
            """,
            {"product": product},
        )
        month_rows = parse_rows(month_result)

        # All time
        all_result = await db.query(
            """
            SELECT event_type, count() AS count,
                   math::sum(estimated_time_saved_minutes) AS minutes_saved
            FROM roi_event
            WHERE product = <record>$product
            GROUP BY event_type
            """,
            {"product": product},
        )
        all_rows = parse_rows(all_result)

    def _summarize(rows):
        valid = [r for r in rows if isinstance(r, dict)]
        total_minutes = sum(r.get("minutes_saved", 0) or 0 for r in valid)
        return {
            "events": valid,
            "total_minutes_saved": total_minutes,
            "hours_saved": round(total_minutes / 60, 1),
        }

    return {
        "this_week": _summarize(week_rows),
        "this_month": _summarize(month_rows),
        "all_time": _summarize(all_rows),
    }


@router.get("/summary")
async def get_roi_summary(product: str = Query(...), user=Depends(get_current_user)):
    """Aggregate ROI summary across all time."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT event_type, count() AS count,
                   math::sum(estimated_time_saved_minutes) AS minutes_saved
            FROM roi_event
            WHERE product = <record>$product
            GROUP BY event_type
            """,
            {"product": product},
        )
        rows = parse_rows(result)

    summary = {
        "total_hours_saved": 0.0,
        "mistakes_prevented": 0,
        "gaps_filled": 0,
        "connections_surfaced": 0,
        "knowledge_reused": 0,
        "corrections_propagated": 0,
    }

    total_minutes = 0
    rows = [r for r in rows if isinstance(r, dict)]
    for row in rows:
        et = row.get("event_type", "")
        count = row.get("count", 0) or 0
        minutes = row.get("minutes_saved", 0) or 0
        total_minutes += minutes

        if et == "mistake_prevented":
            summary["mistakes_prevented"] = count
        elif et == "gap_filled":
            summary["gaps_filled"] = count
        elif et == "connection_surfaced":
            summary["connections_surfaced"] = count
        elif et == "knowledge_reused":
            summary["knowledge_reused"] = count
        elif et == "correction_propagated":
            summary["corrections_propagated"] = count

    summary["total_hours_saved"] = round(total_minutes / 60, 1)
    return summary
