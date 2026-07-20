"""REST API for notification management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.engine.core.auth import get_current_user, verify_ownership
from core.engine.core.db import parse_rows, pool

router = APIRouter(tags=["notifications"])


class PrefUpdateRequest(BaseModel):
    tier: str
    channels: list[str]
    email: str | None = None
    webhook_url: str | None = None
    enabled: bool = True


@router.get("/notifications")
async def list_notifications(
    tier: str | None = None,
    unread: bool | None = None,
    project: str | None = None,
    limit: int = Query(default=20, le=100),
    user=Depends(get_current_user),
):
    """List notifications for current user."""
    product_id = user.get("product", "")
    conditions = ["product = <record>$product", "user = <record>$user"]
    params: dict = {"product": product_id, "user": user["sub"], "limit": limit}

    if tier:
        conditions.append("tier = $tier")
        params["tier"] = tier
    if unread is True:
        conditions.append("read = false")
    conditions.append("dismissed = false")

    project_clause = ""
    if project:
        # decision:6vacauzia2jc46hpvms8 — `= (SELECT VALUE ... LIMIT 1)` returns
        # empty in SurrealDB v3 (subquery yields 1-element array, not scalar).
        project_clause = " AND project IN (SELECT VALUE id FROM project WHERE product = <record>$product AND slug = <string>$project)"
        params["project"] = project

    where = " AND ".join(conditions)

    async with pool.connection() as db:
        result = await db.query(
            f"SELECT * FROM notification WHERE {where}{project_clause} ORDER BY created_at DESC LIMIT $limit",
            params,
        )
        rows = parse_rows(result)
        rows = [r for r in rows if isinstance(r, dict)]

        # Unread count
        count_result = await db.query(
            f"SELECT count() AS n FROM notification WHERE product = <record>$product AND user = <record>$user AND read = false AND dismissed = false{project_clause} GROUP ALL",
            {"product": product_id, "user": user["sub"], **({"project": project} if project else {})},
        )
        count_rows = parse_rows(count_result)
        count_rows = [r for r in count_rows if isinstance(r, dict)]
        unread_count = count_rows[0].get("n", 0) if count_rows else 0

    return {"notifications": rows, "unread_count": unread_count}


@router.patch("/notifications/{notification_id}/read")
async def mark_read(notification_id: str, user=Depends(get_current_user)):
    """Mark a notification as read."""
    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": notification_id})
        rows = parse_rows(result)
        if rows:
            verify_ownership(rows[0], user)
        await db.query("UPDATE <record>$id SET read = true", {"id": notification_id})
    return {"id": notification_id, "read": True}


@router.post("/notifications/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    """Mark all notifications as read."""
    async with pool.connection() as db:
        await db.query(
            "UPDATE notification SET read = true WHERE product = <record>$product AND user = <record>$user AND read = false",
            {"product": user.get("product", ""), "user": user["sub"]},
        )
    return {"status": "ok"}


@router.patch("/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str, user=Depends(get_current_user)):
    """Dismiss a notification."""
    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": notification_id})
        rows = parse_rows(result)
        if rows:
            verify_ownership(rows[0], user)
        await db.query("UPDATE <record>$id SET dismissed = true, read = true", {"id": notification_id})
    return {"id": notification_id, "dismissed": True}


@router.get("/notifications/preferences")
async def get_preferences(user=Depends(get_current_user)):
    """Get user notification preferences."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM notification_pref WHERE product = <record>$product AND user = <record>$user",
            {"product": user.get("product", ""), "user": user["sub"]},
        )
        rows = parse_rows(result)
    return {"preferences": rows}


@router.put("/notifications/preferences")
async def update_preferences(body: PrefUpdateRequest, user=Depends(get_current_user)):
    """Update notification preferences for a tier."""
    async with pool.connection() as db:
        await db.query(
            """
            UPSERT notification_pref SET
                product = <record>$product, user = <record>$user, tier = $tier,
                channels = $channels, email = $email,
                webhook_url = $webhook_url, enabled = $enabled
            WHERE product = <record>$product AND user = <record>$user AND tier = $tier
            """,
            {
                "product": user.get("product", ""),
                "user": user["sub"],
                "tier": body.tier,
                "channels": body.channels,
                "email": body.email,
                "webhook_url": body.webhook_url,
                "enabled": body.enabled,
            },
        )
    return {"tier": body.tier, "updated": True}
