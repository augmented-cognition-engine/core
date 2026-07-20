# engine/api/atc.py
"""ATC API — flight registry and radar data for the portal."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(prefix="/atc", tags=["atc"])


@router.get("/flights")
async def list_flights(status: str | None = None, user=Depends(get_current_user)):
    """List ATC flights with optional status filter."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        if status:
            result = await db.query(
                """SELECT * FROM atc_flight
                WHERE product = <record>$product AND status = $status
                ORDER BY priority ASC, created_at DESC""",
                {"product": product_id, "status": status},
            )
        else:
            result = await db.query(
                """SELECT * FROM atc_flight
                WHERE product = <record>$product AND status NOT IN ['landed', 'cancelled']
                ORDER BY priority ASC, created_at DESC
                LIMIT 50""",
                {"product": product_id},
            )
    flights = parse_rows(result)
    return {"flights": flights, "count": len(flights)}


@router.get("/flights/holding")
async def list_holding(user=Depends(get_current_user)):
    """List flights in holding pattern with blocker info."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        result = await db.query(
            """SELECT *,
                blocked_by.title AS blocker_title,
                blocked_by.source AS blocker_source,
                blocked_by.capabilities AS blocker_capabilities
            FROM atc_flight
            WHERE product = <record>$product AND status = 'holding'
            ORDER BY priority ASC""",
            {"product": product_id},
        )
    flights = parse_rows(result)
    return {"holding": flights, "count": len(flights)}


@router.get("/capabilities")
async def list_capabilities(user=Depends(get_current_user)):
    """List capabilities with their current occupancy (which flights hold them)."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        # Get all capabilities
        caps_result = await db.query(
            """SELECT slug, status, name, description FROM capability
            WHERE product = <record>$product
            ORDER BY slug""",
            {"product": product_id},
        )
        caps = parse_rows(caps_result)

        # Get active flights with their capabilities
        flights_result = await db.query(
            """SELECT id, title, source, source_id, capabilities, status FROM atc_flight
            WHERE product = <record>$product AND status IN ['cleared', 'active', 'landing']""",
            {"product": product_id},
        )
        flights = parse_rows(flights_result)

    # Map: capability slug → list of flights occupying it
    occupancy: dict[str, list] = {}
    for f in flights:
        for cap in f.get("capabilities", []):
            if cap not in occupancy:
                occupancy[cap] = []
            occupancy[cap].append(
                {
                    "flight_id": str(f.get("id", "")),
                    "title": f.get("title", ""),
                    "source": f.get("source", ""),
                    "status": f.get("status", ""),
                }
            )

    sectors = []
    for cap in caps:
        slug = cap.get("slug", "")
        flights_here = occupancy.get(slug, [])
        sectors.append(
            {
                "slug": slug,
                "name": cap.get("name", slug),
                "status": "occupied" if flights_here else "clear",
                "flights": flights_here,
                "flight_count": len(flights_here),
            }
        )

    return {"sectors": sectors, "total": len(sectors)}


@router.get("/radar")
async def radar_data(user=Depends(get_current_user)):
    """Combined radar data: active flights, holding, sectors, landing queue."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        active = parse_rows(
            await db.query(
                """SELECT * FROM atc_flight
            WHERE product = <record>$product AND status IN ['cleared', 'active']
            ORDER BY priority ASC""",
                {"product": product_id},
            )
        )
        holding = parse_rows(
            await db.query(
                """SELECT *,
                blocked_by.title AS blocker_title,
                blocked_by.source AS blocker_source
            FROM atc_flight
            WHERE product = <record>$product AND status = 'holding'
            ORDER BY priority ASC""",
                {"product": product_id},
            )
        )
        landing = parse_rows(
            await db.query(
                """SELECT * FROM atc_flight
            WHERE product = <record>$product AND status = 'landing'
            ORDER BY updated_at ASC""",
                {"product": product_id},
            )
        )
        recent_landed = parse_rows(
            await db.query(
                """SELECT * FROM atc_flight
            WHERE product = <record>$product AND status = 'landed'
            ORDER BY landed_at DESC LIMIT 5""",
                {"product": product_id},
            )
        )

    return {
        "active": active,
        "holding": holding,
        "landing": landing,
        "recent_landed": recent_landed,
        "counts": {
            "active": len(active),
            "holding": len(holding),
            "landing": len(landing),
        },
    }
