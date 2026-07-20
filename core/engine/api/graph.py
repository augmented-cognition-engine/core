# engine/api/graph.py
"""Graph API — synapse visualization and proposal management."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool
from core.engine.graph.assertions import inspect_assertion
from core.engine.graph.proposals import confirm_proposal, dismiss_proposal, list_proposals

router = APIRouter(tags=["graph"])


@router.get("/assertions/{assertion_id:path}")
async def get_assertion(assertion_id: str, user: dict = Depends(get_current_user)):
    """Inspect one assertion, its evidence/proposals/reviews/history, and projection."""
    result = await inspect_assertion(assertion_id)
    return result or {"error": "assertion_not_found", "assertion_id": assertion_id}


class GraphResponse(BaseModel):
    nodes: list[dict] = []
    edges: list[dict] = []


@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    product: str = Query(..., description="Organization ID"),
    user: dict = Depends(get_current_user),
):
    """Return graph nodes (subdomains) and edges (synapses) for visualization."""
    async with pool.connection() as db:
        nodes_result = await db.query(
            """
            SELECT
                id, slug, name, domain.slug AS domain,
                count(SELECT id FROM insight WHERE (subdomain = $parent.id OR domain_path CONTAINS $parent.slug) AND status = 'active' AND product = <record>$product) AS insight_count,
                count(SELECT id FROM task WHERE domain_path CONTAINS slug AND product = <record>$product AND created_at > time::now() - 7d) AS recent_tasks,
                (SELECT phase FROM maturation WHERE node_id = $parent.id AND product = <record>$product LIMIT 1)[0].phase AS maturation_phase
            FROM subdomain
            """,
            {"product": product},
        )

        edges_result = await db.query(
            "SELECT * FROM synapse WHERE product = <record>$product ORDER BY strength DESC",
            {"product": product},
        )

    nodes_raw = parse_rows(nodes_result)
    # Filter out empty nodes — only show subdomains with insights or recent activity
    nodes_raw = [n for n in nodes_raw if (n.get("insight_count") or 0) > 0 or (n.get("recent_tasks") or 0) > 0]
    nodes = [{k: str(v) if hasattr(v, "table_name") else v for k, v in n.items()} for n in nodes_raw]
    edges_raw = parse_rows(edges_result)

    edges = []
    for e in edges_raw:
        edges.append(
            {
                "id": str(e.get("id", "")),
                "from": str(e.get("in", "")),
                "to": str(e.get("out", "")),
                "strength": e.get("strength", 0),
                "direction": e.get("direction", "bidirectional"),
                "interface_type": e.get("interface_type"),
                "origin": e.get("origin", ""),
                "confirmed": e.get("confirmed", False),
                "co_occurrence": e.get("co_occurrence", 0),
            }
        )

    return {"nodes": nodes, "edges": edges}


@router.get("/graph/{domain_path:path}")
async def get_graph_filtered(
    domain_path: str,
    product: str = Query(..., description="Organization ID"),
    user: dict = Depends(get_current_user),
):
    """Return graph filtered to connections involving a specific discipline or subdomain slug."""
    # domain_path is now a flat discipline string; support legacy dotted paths by taking the last segment
    slug = domain_path.split(".")[-1] if "." in domain_path else domain_path

    async with pool.connection() as db:
        sub_result = await db.query(
            "SELECT id FROM subdomain WHERE slug = <string>$slug LIMIT 1",
            {"slug": slug},
        )
        sub_rows = parse_rows(sub_result)

        if not sub_rows:
            return {"nodes": [], "edges": []}

        sub_id = sub_rows[0]["id"]

        edges_result = await db.query(
            """
            SELECT * FROM synapse
            WHERE (`in` = $sub OR `out` = $sub) AND product = <record>$product
            ORDER BY strength DESC
            """,
            {"sub": sub_id, "product": product},
        )

    edges_raw = parse_rows(edges_result)
    edges = [
        {
            "id": str(e.get("id", "")),
            "from": str(e.get("in", "")),
            "to": str(e.get("out", "")),
            "strength": e.get("strength", 0),
            "direction": e.get("direction", "bidirectional"),
            "interface_type": e.get("interface_type"),
            "origin": e.get("origin", ""),
            "confirmed": e.get("confirmed", False),
            "co_occurrence": e.get("co_occurrence", 0),
        }
        for e in edges_raw
    ]

    return {"nodes": sub_rows, "edges": edges}


@router.get("/proposals")
async def get_proposals(
    product: str = Query(..., description="Organization ID"),
    user: dict = Depends(get_current_user),
):
    """List pending synapse proposals."""
    proposals = await list_proposals(product)
    return {"proposals": proposals}


@router.post("/proposals/{synapse_id}/confirm")
async def confirm(
    synapse_id: str,
    user: dict = Depends(get_current_user),
):
    """Confirm a synapse proposal."""
    user_id = user.get("sub", "user:default")
    result = await confirm_proposal(synapse_id, user_id)
    return result


@router.post("/proposals/{synapse_id}/dismiss")
async def dismiss(
    synapse_id: str,
    user: dict = Depends(get_current_user),
):
    """Dismiss a synapse proposal (doubles threshold)."""
    result = await dismiss_proposal(synapse_id)
    return result
