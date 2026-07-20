"""REST API for agent sessions, metrics, and config overrides."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

router = APIRouter(tags=["agents"])


class ConfigOverrideRequest(BaseModel):
    discipline: str
    override: dict


@router.get("/agents/sessions")
async def list_agent_sessions(
    status: str | None = None,
    project: str | None = None,
    limit: int = 20,
    user=Depends(get_current_user),
):
    """List agent sessions, optionally filtered by status and/or project."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        status_clause = " AND status = <string>$status" if status else ""
        project_clause = ""
        if project:
            # decision:6vacauzia2jc46hpvms8 — `= (SELECT VALUE ... LIMIT 1)` returns
            # empty in SurrealDB v3 (subquery yields a 1-element array, not scalar).
            project_clause = " AND project IN (SELECT VALUE id FROM project WHERE product = <record>$product AND slug = <string>$project)"
        result = await db.query(
            f"SELECT * FROM agent_session WHERE product = <record>$product{status_clause}{project_clause} ORDER BY started_at DESC LIMIT $limit",
            {"product": product_id, "status": status, "project": project, "limit": limit},
        )
        sessions = parse_rows(result)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/agents/metrics")
async def get_agent_metrics(user=Depends(get_current_user)):
    """Aggregate quality metrics by archetype and mode from the task table."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        archetype_result = await db.query(
            """SELECT archetype, count() AS total,
                      count(feedback_human = 'accepted' OR NULL) AS accepted
               FROM task WHERE product = <record>$product AND archetype != NONE
               GROUP BY archetype""",
            {"product": product_id},
        )
        mode_result = await db.query(
            """SELECT mode, count() AS total
               FROM task WHERE product = <record>$product AND mode != NONE
               GROUP BY mode""",
            {"product": product_id},
        )
        by_archetype = parse_rows(archetype_result)
        by_mode = parse_rows(mode_result)
    return {"by_archetype": by_archetype, "by_mode": by_mode}


@router.get("/agents/config")
async def list_agent_config(user=Depends(get_current_user)):
    """List all agent config overrides for the org."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM agent_config_override WHERE product = <record>$product ORDER BY discipline",
            {"product": product_id},
        )
        overrides = parse_rows(result)
    return {"overrides": overrides, "count": len(overrides)}


@router.put("/agents/config")
async def upsert_agent_config(body: ConfigOverrideRequest, user=Depends(get_current_user)):
    """Upsert a per-discipline agent config override."""
    product_id = user.get("product", "")
    user_id = user.get("sub", "user:default")
    async with pool.connection() as db:
        result = await db.query(
            """INSERT INTO agent_config_override (product, discipline, override, updated_by, updated_at)
               VALUES (<record>$product, <string>$discipline, $override, <record>$user_id, time::now())
               ON DUPLICATE KEY UPDATE
                 override = $override,
                 updated_by = <record>$user_id,
                 updated_at = time::now()""",
            {
                "product": product_id,
                "discipline": body.discipline,
                "override": body.override,
                "user_id": user_id,
            },
        )
        record = parse_one(result)
    return record or {"discipline": body.discipline, "updated": True}


@router.delete("/agents/config/{discipline}")
async def delete_agent_config(discipline: str, user=Depends(get_current_user)):
    """Delete a per-discipline agent config override."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        await db.query(
            "DELETE FROM agent_config_override WHERE product = <record>$product AND discipline = <string>$discipline",
            {"product": product_id, "discipline": discipline},
        )
    return {"discipline": discipline, "deleted": True}
