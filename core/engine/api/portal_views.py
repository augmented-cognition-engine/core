# engine/api/portal_views.py
import logging

from fastapi import APIRouter, Depends, Query

from core.engine.core.auth import get_current_user, verify_ownership
from core.engine.core.db import parse_one, parse_rows, pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/activity")
async def get_activity(
    product: str = Query(...),
    user: dict = Depends(get_current_user),
):
    async with pool.connection() as db:
        tasks = await db.query(
            """
            SELECT id, description, domain_path, status, feedback_human, created_at
            FROM task WHERE product = <record>$product
            ORDER BY created_at DESC LIMIT 10
            """,
            {"product": product},
        )

        insights_count = await db.query(
            "SELECT count() AS n FROM insight WHERE product = <record>$product AND status = 'active' GROUP ALL",
            {"product": product},
        )

        top_domains = await db.query(
            """
            SELECT domain_path, count() AS insight_count
            FROM insight WHERE product = <record>$product AND status = 'active'
            GROUP BY domain_path
            ORDER BY insight_count DESC LIMIT 5
            """,
            {"product": product},
        )

    task_rows = [r for r in parse_rows(tasks) if isinstance(r, dict)]
    count_row = parse_one(insights_count)
    domain_rows = [r for r in parse_rows(top_domains) if isinstance(r, dict)]

    return {
        "recent_tasks": task_rows,
        "total_insights": count_row.get("n", 0) if count_row else 0,
        "top_domains": domain_rows,
    }


@router.get("/attention")
async def get_attention(
    product: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Attention items: conflicts, proposals, ready ideas, paused initiatives."""
    verify_ownership({"product": product}, user)
    items = []
    async with pool.connection() as db:
        # Pending conflicts
        try:
            result = await db.query(
                "SELECT id, explanation FROM conflict WHERE product = <record>$product AND status = 'pending' LIMIT 5",
                {"product": product},
            )
            rows = parse_rows(result)
            for r in rows:
                items.append(
                    {
                        "type": "conflict",
                        "id": str(r.get("id", "")),
                        "title": "Intelligence conflict",
                        "link": "/conflicts",
                        "detail": str(r.get("explanation", ""))[:100],
                    }
                )
        except Exception as exc:
            logger.warning("Attention query failed: %s", exc)

        # Ready ideas
        try:
            result = await db.query(
                "SELECT id, title FROM idea WHERE product = <record>$product AND status = 'ready' LIMIT 5",
                {"product": product},
            )
            rows = parse_rows(result)
            for r in rows:
                items.append(
                    {
                        "type": "idea_ready",
                        "id": str(r.get("id", "")),
                        "title": f"Idea ready: {r.get('title', '')}",
                        "link": "/ideas",
                    }
                )
        except Exception as exc:
            logger.warning("Attention query failed: %s", exc)

        # Paused initiatives
        try:
            result = await db.query(
                "SELECT id, title FROM initiative WHERE product = <record>$product AND status = 'paused' LIMIT 5",
                {"product": product},
            )
            rows = parse_rows(result)
            for r in rows:
                items.append(
                    {
                        "type": "initiative_paused",
                        "id": str(r.get("id", "")),
                        "title": f"Paused: {r.get('title', '')}",
                        "link": "/initiatives",
                    }
                )
        except Exception as exc:
            logger.warning("Attention query failed: %s", exc)

        # Self-optimizer proposals
        try:
            result = await db.query(
                "SELECT id, name, description, evidence FROM self_optimizer_proposal WHERE product = <record>$product AND status = 'proposed' LIMIT 5",
                {"product": product},
            )
            rows = parse_rows(result)
            for r in rows:
                items.append(
                    {
                        "type": "self_optimizer_proposal",
                        "title": r.get("name", ""),
                        "description": r.get("description", ""),
                        "id": str(r.get("id", "")),
                        "evidence": r.get("evidence"),
                    }
                )
        except Exception as exc:
            logger.warning("Attention query failed: %s", exc)

        # Perspective gaps from latest engine run
        try:
            result = await db.query(
                "SELECT results, completed_at FROM engine_run WHERE engine = 'perspective_gap_detector' AND product = <record>$product ORDER BY completed_at DESC LIMIT 1",
                {"product": product},
            )
            rows = parse_rows(result)
            if rows:
                gap_details = (rows[0].get("results") or {}).get("gap_details", [])
                for gap in gap_details:
                    items.append(
                        {
                            "type": "perspective_gap",
                            "title": f"{gap.get('perspective', '')} perspective unused",
                            "description": gap.get("prompt", ""),
                            "perspective": gap.get("perspective", ""),
                        }
                    )
        except Exception as exc:
            logger.warning("Attention query failed: %s", exc)

    return {"items": items, "count": len(items)}


@router.get("/cross-product-signals")
async def get_cross_product_signals(
    user: dict = Depends(get_current_user),
):
    """Aggregate signals across all products for the authenticated tenant."""
    product_id = user.get("product", "")
    now_items: list[dict] = []
    next_items: list[dict] = []

    async with pool.connection() as db:
        # Resolve tenant from the user's current product
        t_result = await db.query(
            "SELECT tenant FROM product WHERE id = <record>$product LIMIT 1",
            {"product": product_id},
        )
        t_rows = parse_rows(t_result)
        tenant = str(t_rows[0]["tenant"]) if t_rows and t_rows[0].get("tenant") else "tenant:default"

        # All products for this tenant
        p_result = await db.query(
            "SELECT id, name FROM product WHERE tenant = <record>$tenant",
            {"tenant": tenant},
        )
        products = parse_rows(p_result)
        product_name_map = {str(p["id"]): p.get("name", "Unknown") for p in products}

        if not products:
            return {
                "now": [],
                "next": [],
                "pulse": {"gates_waiting": 0, "initiatives_active": 0, "engagements_at_risk": 0},
            }

        # NOW: pending gates across all products
        try:
            result = await db.query(
                """
                SELECT id, entity_type, entity_id, product, created_at
                FROM gate_evaluation
                WHERE product INSIDE (SELECT VALUE id FROM product WHERE tenant = <record>$tenant)
                AND status = 'pending'
                ORDER BY created_at DESC LIMIT 20
                """,
                {"tenant": tenant},
            )
            for r in parse_rows(result):
                pid = str(r.get("product", ""))
                now_items.append(
                    {
                        "id": str(r.get("id", "")),
                        "type": "gate",
                        "title": f"Gate pending: {r.get('entity_type', '')} decision",
                        "product_id": pid,
                        "product_name": product_name_map.get(pid, "Unknown"),
                        "created_at": str(r.get("created_at", "")),
                    }
                )
        except Exception as exc:
            logger.warning("Cross-product gates query failed: %s", exc)

        # NOW: paused initiatives (at risk)
        try:
            result = await db.query(
                """
                SELECT id, title, product, updated_at FROM initiative
                WHERE product INSIDE (SELECT VALUE id FROM product WHERE tenant = <record>$tenant)
                AND status IN ['paused', 'blocked']
                ORDER BY updated_at DESC LIMIT 10
                """,
                {"tenant": tenant},
            )
            for r in parse_rows(result):
                pid = str(r.get("product", ""))
                now_items.append(
                    {
                        "id": str(r.get("id", "")),
                        "type": "risk",
                        "title": r.get("title", "Untitled initiative"),
                        "product_id": pid,
                        "product_name": product_name_map.get(pid, "Unknown"),
                        "created_at": str(r.get("updated_at", "")),
                    }
                )
        except Exception as exc:
            logger.warning("Cross-product paused query failed: %s", exc)

        # NEXT: recommended ideas (ready for action)
        try:
            result = await db.query(
                """
                SELECT id, title, product, created_at FROM idea
                WHERE product INSIDE (SELECT VALUE id FROM product WHERE tenant = <record>$tenant)
                AND status = 'ready'
                ORDER BY created_at DESC LIMIT 10
                """,
                {"tenant": tenant},
            )
            for r in parse_rows(result):
                pid = str(r.get("product", ""))
                next_items.append(
                    {
                        "id": str(r.get("id", "")),
                        "type": "recommended",
                        "title": r.get("title", "Untitled idea"),
                        "product_id": pid,
                        "product_name": product_name_map.get(pid, "Unknown"),
                        "due_at": None,
                    }
                )
        except Exception as exc:
            logger.warning("Cross-product ideas query failed: %s", exc)

        # Pulse counters
        gates_waiting = len([i for i in now_items if i["type"] == "gate"])
        try:
            active_result = await db.query(
                """
                SELECT count() AS n FROM initiative
                WHERE product INSIDE (SELECT VALUE id FROM product WHERE tenant = <record>$tenant)
                AND status = 'active' GROUP ALL
                """,
                {"tenant": tenant},
            )
            active_rows = parse_rows(active_result)
            initiatives_active = int(active_rows[0].get("n", 0) or 0) if active_rows else 0
        except Exception as exc:
            logger.warning("Cross-product active count failed: %s", exc)
            initiatives_active = 0

        engagements_at_risk = len({i["product_id"] for i in now_items if i["type"] == "risk"})

    return {
        "now": now_items,
        "next": next_items,
        "pulse": {
            "gates_waiting": gates_waiting,
            "initiatives_active": initiatives_active,
            "engagements_at_risk": engagements_at_risk,
        },
    }


@router.get("/active-work")
async def get_active_work(
    product: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Running initiatives with milestone progress."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT id, title, status, priority, total_cost, cost_budget, created_at
            FROM initiative
            WHERE product = <record>$product AND status IN ['active', 'planning']
            ORDER BY created_at DESC
            LIMIT 10
            """,
            {"product": product},
        )
        rows = parse_rows(result)

        # Count running ideas
        idea_result = await db.query(
            "SELECT count() AS n FROM idea WHERE product = <record>$product AND status IN ['incubating', 'qualifying'] GROUP ALL",
            {"product": product},
        )
        idea_row = parse_one(idea_result)
        incubating_count = idea_row.get("n", 0) if idea_row else 0

    return {
        "initiatives": rows,
        "incubating_ideas": incubating_count,
    }


@router.get("/pulse")
async def get_pulse(
    product: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Intelligence pulse: insight count, specialties, connections, health."""
    async with pool.connection() as db:
        insight_count = await db.query(
            "SELECT count() AS n FROM insight WHERE product = <record>$product AND status = 'active' GROUP ALL",
            {"product": product},
        )
        specialty_count = await db.query(
            "SELECT count() AS n FROM specialty WHERE product = <record>$product GROUP ALL",
            {"product": product},
        )
        # Count all observed synapses, not just user-confirmed. Confirmation
        # is an internal proposal-promotion concept (cooccurrence threshold +
        # explicit confirm action); the user-facing "connections" metric
        # should reflect what ACE has actually discovered in the intelligence
        # graph, not just what a human has clicked "approve" on. Otherwise
        # the metric stays at 0 indefinitely even when real cooccurrence
        # activity is accumulating.
        synapse_count = await db.query(
            "SELECT count() AS n FROM synapse WHERE product = <record>$product GROUP ALL",
            {"product": product},
        )
        top_domains = await db.query(
            """
            SELECT domain_path, count() AS insight_count
            FROM insight WHERE product = <record>$product AND status = 'active'
            GROUP BY domain_path ORDER BY insight_count DESC LIMIT 8
            """,
            {"product": product},
        )

    def _extract_count(result):
        row = parse_one(result)
        return row.get("n", 0) if row else 0

    domain_rows = [r for r in parse_rows(top_domains) if isinstance(r, dict)]

    return {
        "insights": _extract_count(insight_count),
        "specialties": _extract_count(specialty_count),
        "connections": _extract_count(synapse_count),
        "domains": domain_rows,
    }
