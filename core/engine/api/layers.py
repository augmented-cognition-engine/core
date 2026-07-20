"""Cross-layer composite endpoints — join data from CODE, PRODUCT, WORK, LIVE."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

router = APIRouter(tags=["layers"])


@router.get("/layers/live-status")
async def live_status(user=Depends(get_current_user)):
    """Aggregated LIVE layer state — active agents, edits, locks."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        agents = parse_rows(
            await db.query(
                """SELECT id, state, work_item, progress_pct, capabilities_touched, started_at
            FROM agent_session
            WHERE product = <record>$product AND state IN ['starting', 'active', 'blocked', 'completing']
            ORDER BY started_at DESC""",
                {"product": product_id},
            )
        )
        edits_count = parse_rows(
            await db.query(
                "SELECT count() AS cnt FROM active_edit WHERE product = <record>$product AND state IN ['claimed', 'editing', 'committing'] GROUP ALL",
                {"product": product_id},
            )
        )
        conflicts_count = parse_rows(
            await db.query(
                "SELECT count() AS cnt FROM active_edit WHERE product = <record>$product AND state = 'conflict' GROUP ALL",
                {"product": product_id},
            )
        )
        locks_count = parse_rows(
            await db.query(
                "SELECT count() AS cnt FROM resource_lock WHERE product = <record>$product AND state IN ['acquired', 'held'] GROUP ALL",
                {"product": product_id},
            )
        )

    active = [a for a in agents if a.get("state") == "active"]
    blocked = [a for a in agents if a.get("state") == "blocked"]

    return {
        "active_agents": active,
        "blocked_agents": blocked,
        "all_agents": agents,
        "active_edits": edits_count[0].get("cnt", 0) if edits_count else 0,
        "conflicts": conflicts_count[0].get("cnt", 0) if conflicts_count else 0,
        "locks_held": locks_count[0].get("cnt", 0) if locks_count else 0,
    }


@router.get("/layers/capability-activity/{slug}")
async def capability_activity(slug: str, user=Depends(get_current_user)):
    """Full capability view — PRODUCT + CODE + LIVE + WORK."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        cap = parse_one(
            await db.query(
                "SELECT * FROM capability WHERE product = <record>$product AND slug = <string>$slug LIMIT 1",
                {"product": product_id, "slug": slug},
            )
        )
        if not cap:
            return {"error": "Capability not found"}

        cap_id = cap.get("id")

        quality = parse_rows(
            await db.query(
                "SELECT * FROM capability_quality WHERE capability = <record>$cap AND product = <record>$product",
                {"cap": cap_id, "product": product_id},
            )
        )
        files = parse_rows(
            await db.query(
                "SELECT *, in.path AS file_path FROM realizes WHERE out = <record>$cap",
                {"cap": cap_id},
            )
        )
        agents = parse_rows(
            await db.query(
                """SELECT * FROM agent_session
            WHERE product = <record>$product AND state IN ['active', 'blocked']
              AND capabilities_touched CONTAINS $slug""",
                {"product": product_id, "slug": slug},
            )
        )
        tasks = parse_rows(
            await db.query(
                """SELECT id, description, status, created_at FROM task
            WHERE product = <record>$product
            ORDER BY created_at DESC LIMIT 5""",
                {"product": product_id},
            )
        )
        gaps = [q for q in quality if q.get("score", 1.0) < 0.4 and q.get("gaps")]

    return {
        "capability": cap,
        "quality": quality,
        "files": files,
        "active_agents": agents,
        "recent_tasks": tasks,
        "open_gaps": gaps,
    }


@router.get("/layers/work-progress/{initiative_id}")
async def work_progress(initiative_id: str, user=Depends(get_current_user)):
    """Initiative detail — WORK + LIVE layers."""
    async with pool.connection() as db:
        initiative = parse_one(
            await db.query(
                "SELECT * FROM ONLY <record>$id",
                {"id": initiative_id},
            )
        )
        if not initiative:
            return {"error": "Initiative not found"}

        milestones = parse_rows(
            await db.query(
                "SELECT * FROM milestone WHERE initiative = <record>$init ORDER BY sequence",
                {"init": initiative_id},
            )
        )

        for ms in milestones:
            ms_id = ms.get("id")
            items = parse_rows(
                await db.query(
                    "SELECT * FROM work_item WHERE milestone = <record>$ms",
                    {"ms": ms_id},
                )
            )
            for item in items:
                sessions = parse_rows(
                    await db.query(
                        """SELECT id, state, progress_pct FROM agent_session
                    WHERE work_item = <record>$wi AND state NOT IN ['done', 'failed', 'abandoned']
                    LIMIT 1""",
                        {"wi": item.get("id")},
                    )
                )
                item["agent"] = sessions[0] if sessions else None
            ms["work_items"] = items

    return {
        "initiative": initiative,
        "milestones": milestones,
    }
