# engine/flow/config.py
"""Read domain_flow_config from DB, return defaults when unconfigured."""

from __future__ import annotations

from dataclasses import dataclass

from core.engine.core.db import parse_one, parse_rows, pool


@dataclass
class FlowDefaults:
    default_clearance: str = "open"
    insight_propagation: bool = True
    consume_org_intelligence: bool = True
    contribute_org_intelligence: bool = True


async def get_flow_config(domain_id: str, product_id: str) -> FlowDefaults:
    """Get flow config for a domain. Returns defaults if no config exists."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT default_clearance, insight_propagation,
                   consume_org_intelligence, contribute_org_intelligence
            FROM domain_flow_config
            WHERE domain = $domain AND product = <record>$product
            LIMIT 1
            """,
            {"domain": domain_id, "product": product_id},
        )

    rows = parse_rows(result)
    if not rows:
        return FlowDefaults()

    row = rows[0]
    return FlowDefaults(
        default_clearance=row.get("default_clearance", "open"),
        insight_propagation=row.get("insight_propagation", True),
        consume_org_intelligence=row.get("consume_org_intelligence", True),
        contribute_org_intelligence=row.get("contribute_org_intelligence", True),
    )


async def upsert_flow_config(
    domain_id: str,
    product_id: str,
    default_clearance: str = "open",
    insight_propagation: bool = True,
    consume_org_intelligence: bool = True,
    contribute_org_intelligence: bool = True,
) -> dict:
    """Create or update flow config for a domain."""
    async with pool.connection() as db:
        result = await db.query(
            """
            UPSERT domain_flow_config SET
                product = <record>$product,
                domain = $domain,
                default_clearance = $clearance,
                insight_propagation = $propagation,
                consume_org_intelligence = $consume,
                contribute_org_intelligence = $contribute
            WHERE domain = $domain AND product = <record>$product
            """,
            {
                "domain": domain_id,
                "product": product_id,
                "clearance": default_clearance,
                "propagation": insight_propagation,
                "consume": consume_org_intelligence,
                "contribute": contribute_org_intelligence,
            },
        )
        row = parse_one(result)
    return row or {}
