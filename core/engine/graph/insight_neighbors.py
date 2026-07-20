# core/engine/graph/insight_neighbors.py
"""Relationship-aware retrieval — read the canonical operational projection.

Given seed insight ids (the top retrieval matches), traverse the typed
insight<->insight edges Cognify writes (source='cognify') and return the
neighbors, each tagged with the relationship, direction, and why it surfaced.
Read-only, no LLM, fully non-fatal — the read half of the synapse loop.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import parse_record_id, parse_rows, pool

logger = logging.getLogger(__name__)

__all__ = ["load_insight_neighbors", "expand_snapshot_relationships", "classify_tensions"]

# Relationship taxonomy — single source of truth for tension/consequence classification.
_TENSION_RELATIONSHIPS = frozenset({"breaks", "reverts"})
_CONSEQUENCE_RELATIONSHIPS = frozenset({"causes"})


async def load_insight_neighbors(
    seed_insight_ids: list[str],
    product_id: str,
    neighbors_per_seed: int = 3,
    total_cap: int = 10,
    min_edge_confidence: float = 0.0,
) -> list[dict]:
    """Return 1-hop Cognify-edge neighbors of the seed insights. Non-fatal → []."""
    if not seed_insight_ids:
        return []
    seed_strs = [str(s) for s in seed_insight_ids]
    seed_set = set(seed_strs)  # STRINGS — parse_rows stringifies in/out, so Python-side compares stay string-vs-string
    seed_records = [parse_record_id(s) for s in seed_strs]  # RecordIDs — for the SQL binding only

    try:
        # (neighbor_id, relationship, direction, via_insight, edge_confidence)
        candidates: list[tuple[str, str, str, str, float]] = []
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT in, out, predicate, assertion_id, "
                    "assertion_id.evidence_strength AS confidence FROM operational_relationship "
                    "WHERE in IN $seeds OR out IN $seeds ORDER BY confidence DESC LIMIT $cap",
                    {"seeds": seed_records, "cap": total_cap},
                )
            )
            for r in rows:
                e_in, e_out = str(r.get("in", "")), str(r.get("out", ""))
                edge_type = str(r.get("predicate", ""))
                conf = float(r.get("confidence", 0) or 0)
                if conf < min_edge_confidence:
                    continue
                if e_in in seed_set and e_out not in seed_set:
                    candidates.append((e_out, edge_type, "outgoing", e_in, conf))
                elif e_out in seed_set and e_in not in seed_set:
                    candidates.append((e_in, edge_type, "incoming", e_out, conf))

            # Rank by edge confidence; apply per-seed + total caps + dedupe.
            candidates.sort(key=lambda c: c[4], reverse=True)
            per_seed: dict[str, int] = {}
            chosen: dict[str, dict] = {}
            for neighbor, rel, direction, via, conf in candidates:
                if neighbor in seed_set or neighbor in chosen:
                    continue
                if per_seed.get(via, 0) >= neighbors_per_seed:
                    continue
                if len(chosen) >= total_cap:
                    break
                chosen[neighbor] = {
                    "insight_id": neighbor,
                    "relationship": rel,
                    "direction": direction,
                    "via_insight": via,
                    "edge_confidence": conf,
                }
                per_seed[via] = per_seed.get(via, 0) + 1

            if not chosen:
                return []

            content_rows = parse_rows(
                await db.query(
                    "SELECT id, content, confidence, insight_type, domain_path, source_domain FROM insight "
                    "WHERE id IN $ids AND status = 'active' AND clearance = 'open' "
                    "AND product = <record>$product",
                    {"ids": [parse_record_id(k) for k in chosen.keys()], "product": product_id},
                )
            )
            by_id = {str(r.get("id", "")): r for r in content_rows}

        out: list[dict] = []
        for nid, tag in chosen.items():
            ins = by_id.get(nid)
            if not ins:
                continue  # neighbor not active/open/in-product → drop
            out.append(
                {
                    **tag,
                    "content": ins.get("content", ""),
                    "confidence": ins.get("confidence", 0),
                    "insight_type": ins.get("insight_type", ""),
                    "domain_path": ins.get("domain_path", "") or "",
                    "source_domain": ins.get("source_domain", "") or "",
                }
            )
        return out
    except Exception as exc:  # read-only, never break retrieval
        logger.debug("insight neighbor load failed (non-fatal): %s", exc)
        return []


async def expand_snapshot_relationships(snapshot: dict, product_id: str) -> None:
    """Fold 1-hop Cognify-edge neighbors of the top insights into a loader snapshot.

    Shared by every loader (dual_loader, load_intelligence) and ace_load so the
    synapses surface consistently. Read-only, non-fatal, gated. Always sets
    snapshot["relationship_neighbors"] (empty when gated off or nothing found) so
    consumers never branch on the key; folds fresh neighbors into snapshot["insights"]
    tagged source_graph="graph_neighbor" with their relationship + via label.
    """
    snapshot.setdefault("relationship_neighbors", [])
    snapshot.setdefault("graph_tensions", {"tensions": [], "consequences": []})
    if not settings.graph_expansion_enabled:
        return
    insights = snapshot.get("insights", [])
    loaded_ids = {str(i.get("id", "")) for i in insights if i.get("id")}
    seed_ids = [str(i.get("id", "")) for i in insights[: settings.graph_expansion_seed_count] if i.get("id")]
    if not seed_ids:
        return
    try:
        neighbors = await load_insight_neighbors(
            seed_ids,
            product_id,
            neighbors_per_seed=settings.graph_expansion_neighbors_per_seed,
            total_cap=settings.graph_expansion_total_cap,
        )
    except Exception as exc:
        logger.warning("relationship expansion failed (non-fatal): %s", exc)
        return
    fresh = [n for n in neighbors if str(n.get("insight_id", "")) and str(n["insight_id"]) not in loaded_ids]
    snapshot["relationship_neighbors"] = fresh
    buckets = classify_tensions(fresh)
    snapshot["graph_tensions"] = {"tensions": buckets["tensions"], "consequences": buckets["consequences"]}
    for n in fresh:
        insights.append(
            {
                "id": n["insight_id"],
                "content": n.get("content", ""),
                "confidence": n.get("confidence", 0),
                "tier": "",
                "insight_type": n.get("insight_type", ""),
                "source_graph": "graph_neighbor",
                "relationship": n.get("relationship", ""),
                "via_insight": n.get("via_insight", ""),
            }
        )


def classify_tensions(neighbors: list[dict]) -> dict:
    """Partition relationship-neighbors by semantics. Pure, no I/O.

    tensions: breaks/reverts (contradicts a prior decision) · consequences: causes
    (led to / will lead to) · support: everything else (the existing flat behavior).
    """
    buckets: dict[str, list[dict]] = {"tensions": [], "consequences": [], "support": []}
    for n in neighbors:
        rel = n.get("relationship", "")
        if rel in _TENSION_RELATIONSHIPS:
            buckets["tensions"].append(n)
        elif rel in _CONSEQUENCE_RELATIONSHIPS:
            buckets["consequences"].append(n)
        else:
            buckets["support"].append(n)
    return buckets
