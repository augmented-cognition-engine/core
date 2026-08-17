"""Bounded readers for the canonical operational relationship projection.

Operational relationships are usable only while their source assertion remains
accepted and projection-eligible.  Keeping that rule here prevents individual
consumers from accidentally reviving stale Cognify v1 relation-table reads or
dropping product and provenance fences.
"""

from __future__ import annotations

from typing import Any, Collection

from core.engine.core.db import parse_rows, pool
from core.engine.graph.ontology import RELATIONSHIPS

MAX_OPERATIONAL_RELATIONSHIPS = 1_000


def _bounded_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    return min(MAX_OPERATIONAL_RELATIONSHIPS, max(1, limit))


def _predicate_filter(predicates: Collection[str]) -> tuple[str, ...]:
    return tuple(sorted({predicate for predicate in predicates if predicate in RELATIONSHIPS}))


async def load_operational_relationships(
    product_id: str,
    *,
    predicates: Collection[str],
    limit: int = MAX_OPERATIONAL_RELATIONSHIPS,
    db: Any | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic, provenance-bearing canonical edges for one product.

    The database predicate is intentionally fixed here.  Python repeats the
    lifecycle, product, endpoint, and predicate checks so malformed fixtures or
    stale projections also fail closed.
    """
    if not isinstance(product_id, str) or not product_id.startswith("product:") or len(product_id) <= 8:
        raise ValueError("product_id must be a product record id")
    selected_predicates = _predicate_filter(predicates)
    if not selected_predicates:
        return []
    bounded_limit = _bounded_limit(limit)

    if db is None:
        async with pool.connection() as connection:
            return await load_operational_relationships(
                product_id,
                predicates=selected_predicates,
                limit=bounded_limit,
                db=connection,
            )

    rows = parse_rows(
        await db.query(
            """SELECT id, in, out, predicate, assertion_id,
                      evidence_refs, review_refs, ontology_version,
                      resolver_version, projection_version, projected_at,
                      assertion_id.product AS assertion_product,
                      assertion_id.status AS assertion_status,
                      assertion_id.projection_eligible AS assertion_projection_eligible,
                      assertion_id.subject AS assertion_subject,
                      assertion_id.object AS assertion_object,
                      assertion_id.predicate AS assertion_predicate,
                      assertion_id.proposal_confidence AS confidence,
                      in.source_domain AS in_source_domain,
                      out.source_domain AS out_source_domain,
                      in.domain_path AS in_domain_path,
                      out.domain_path AS out_domain_path
               FROM operational_relationship
               WHERE product = <record>$product
                 AND predicate IN $predicates
                 AND assertion_id.product = <record>$product
                 AND assertion_id.status = 'accepted'
                 AND assertion_id.projection_eligible = true
               ORDER BY predicate ASC, id ASC
               LIMIT $limit""",
            {"product": product_id, "predicates": list(selected_predicates), "limit": bounded_limit},
        )
    )

    selected: list[dict[str, Any]] = []
    for row in rows:
        edge_id = str(row.get("id") or "")
        assertion_id = str(row.get("assertion_id") or "")
        edge_in = str(row.get("in") or "")
        edge_out = str(row.get("out") or "")
        predicate = str(row.get("predicate") or "")
        if not edge_id or not assertion_id or predicate not in selected_predicates:
            continue
        if str(row.get("assertion_product") or "") != product_id:
            continue
        if row.get("assertion_status") != "accepted" or row.get("assertion_projection_eligible") is not True:
            continue
        if edge_in != str(row.get("assertion_subject") or ""):
            continue
        if edge_out != str(row.get("assertion_object") or ""):
            continue
        if predicate != str(row.get("assertion_predicate") or ""):
            continue

        selected.append(
            {
                "id": edge_id,
                "in": edge_in,
                "out": edge_out,
                "predicate": predicate,
                "assertion_id": assertion_id,
                "confidence": float(row.get("confidence") or 0.0),
                "in_source_domain": row.get("in_source_domain"),
                "out_source_domain": row.get("out_source_domain"),
                "in_domain_path": row.get("in_domain_path"),
                "out_domain_path": row.get("out_domain_path"),
                "ontology_version": row.get("ontology_version"),
                "resolver_version": row.get("resolver_version"),
                "projection_version": row.get("projection_version"),
                "projected_at": row.get("projected_at"),
                "provenance": {
                    "record_refs": [edge_id, assertion_id],
                    "evidence_refs": sorted(str(ref) for ref in row.get("evidence_refs", []) or []),
                    "review_refs": sorted(str(ref) for ref in row.get("review_refs", []) or []),
                    "source_family": "operational_relationship",
                },
            }
        )
        if len(selected) >= bounded_limit:
            break
    return selected


__all__ = ["MAX_OPERATIONAL_RELATIONSHIPS", "load_operational_relationships"]
