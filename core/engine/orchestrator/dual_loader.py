# engine/orchestrator/dual_loader.py
"""Dual-graph intelligence loader — specialty graph + org graph, merged with provenance.

Queries both knowledge graphs independently and tags every insight with its
origin so downstream consumers can weight or filter by graph.

Step 0  — Resolve specialty slugs to DB records; flag sparse ones as gaps.
Step 1  — Load specialty insights (universal, no clearance filter).
Step 2  — Load org insights (clearance-filtered per org_context domain slugs).
Step 3  — Merge into a unified snapshot with backward-compat shape.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_record_id, parse_record_ids, parse_rows, pool
from core.engine.flow.clearance import clearance_where_clause
from core.engine.graph.insight_neighbors import expand_snapshot_relationships
from core.engine.orchestrator.trust_ranking import trust_weighted

logger = logging.getLogger(__name__)

_MAX_SPECIALTY = 20
_MAX_ORG = 20
_MIN_INSIGHT_THRESHOLD = 3  # specialties below this count are reported as gaps

_UTILIZATION_DEFAULT = 0.5  # neutral score for insights with no utilization history
_CONFIDENCE_WEIGHT = 0.7
_UTILIZATION_WEIGHT = 0.3


# ---------------------------------------------------------------------------
# Utilization re-ranking
# ---------------------------------------------------------------------------


def _blend_score(confidence: float, utilization_score: float, trust: float | None = None) -> float:
    """Blended relevance: (confidence × 0.7 + utilization × 0.3) × trust.

    Trust is a believability multiplier on the whole blend — a low-trust insight is demoted regardless
    of how confident or well-utilized it is (that's the point: a self-generated conclusion shouldn't
    out-rank a trusted human capture). trust=None (un-reconciled) is neutral (×1.0)."""
    base = confidence * _CONFIDENCE_WEIGHT + utilization_score * _UTILIZATION_WEIGHT
    return trust_weighted(base, trust)


async def _rerank_by_utilization(
    insights: list[dict],
    product_id: str,
) -> list[dict]:
    """Re-rank insights by blending static confidence with live utilization score.

    Fetches utilization_score from insight_utilization for all insight IDs.
    Insights with no utilization record get the neutral default (0.5) — they
    are neither penalised nor boosted relative to their raw confidence.

    Non-fatal: if the DB query fails, the original order is preserved.
    """
    if not insights:
        return insights

    insight_ids = [i["id"] for i in insights if i.get("id")]
    score_map: dict[str, float] = {}

    try:
        parsed_ids = parse_record_ids(insight_ids)
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT insight, utilization_score
                       FROM insight_utilization
                       WHERE product = <record>$product
                         AND insight IN $ids""",
                    {"product": product_id, "ids": parsed_ids},
                )
            )
        for row in rows:
            iid = str(row.get("insight", ""))
            score = row.get("utilization_score")
            if iid and score is not None:
                score_map[iid] = float(score)
    except Exception as exc:
        logger.warning("_rerank_by_utilization: utilization fetch failed (non-fatal): %s", exc)
        return insights

    annotated = []
    for insight in insights:
        util_score = score_map.get(insight["id"], _UTILIZATION_DEFAULT)
        blended = _blend_score(insight.get("confidence", 0.0), util_score, insight.get("trust"))
        annotated.append({**insight, "utilization_score": util_score, "_blended_score": blended})

    annotated.sort(key=lambda x: x["_blended_score"], reverse=True)

    for item in annotated:
        del item["_blended_score"]

    return annotated


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def load_dual_intelligence(
    specialties: list[str],
    product_id: str,
    org_context: list[str] | None = None,
    mode: str = "reactive",
    budget_multiplier: float = 1.0,
    discipline: str = "",
) -> dict:
    """Query specialty and org graphs, merge results with provenance tags.

    Parameters
    ----------
    specialties:
        Specialty slugs to load from the specialty graph.
    product_id:
        SurrealDB record ID of the org (e.g. ``"org:acme"``).
    org_context:
        Domain/subdomain slugs that scope the org-graph query.  When *None*
        or empty, the org graph query is skipped.
    mode:
        Cognitive mode — reserved for future temporal-read expansion.
    budget_multiplier:
        Scales the maximum number of insights loaded from each graph.
        A value of 0.3 loads ``max(3, int(20 * 0.3)) = 6`` insights instead
        of the default 20.  Always at least 3 to ensure some intelligence
        is loaded.  Defaults to 1.0 (no scaling).
    discipline:
        Classifier discipline string (e.g. "architecture"). Used to load
        failure_memory and recent_decisions alongside specialty insights.
        When empty, failure_memory is skipped.

    Returns
    -------
    dict
        Snapshot with ``insights`` (combined, tagged list), ``specialty_insights``,
        ``org_insights``, ``total_count``, ``gaps``, ``recent_signals``,
        ``raw_context``, ``specialties_loaded``, ``org_context_loaded``,
        ``failure_memory``, ``decisions``.
    """
    specialty_insights: list[dict] = []
    org_insights: list[dict] = []
    gaps: list[str] = []
    specialties_loaded: list[str] = []
    org_context_loaded: list[str] = org_context or []

    # Coerce product_id string → RecordID so SurrealDB v3 SCHEMAFULL record<product> comparisons work
    org_record = parse_record_id(product_id)
    platform_record = parse_record_id("product:platform")

    # ------------------------------------------------------------------
    # Step 0 — Resolve specialty slugs
    # ------------------------------------------------------------------
    resolved_ids: list[str] = []
    spec_rows: list[dict] = []

    if specialties:
        try:
            async with pool.connection() as db:
                result = await db.query(
                    """
                    SELECT id, slug, insight_count
                    FROM specialty
                    WHERE slug IN $slugs
                    """,
                    {"slugs": specialties, "product": org_record, "platform": platform_record},
                )
            spec_rows = parse_rows(result)

            for row in spec_rows:
                slug = row.get("slug", "")
                count = row.get("insight_count", 0) or 0
                if count < _MIN_INSIGHT_THRESHOLD:
                    if slug:
                        gaps.append(slug)
                else:
                    # Store as RecordID so SurrealDB v3 IN $ids comparison works on record<specialty> fields
                    resolved_ids.append(parse_record_id(str(row["id"])))
                    if slug:
                        specialties_loaded.append(slug)

            # Any requested slug that had NO matching record is also a gap
            resolved_slugs = {r.get("slug", "") for r in spec_rows}
            for slug in specialties:
                if slug not in resolved_slugs and slug not in gaps:
                    gaps.append(slug)

        except Exception as exc:
            logger.warning("Specialty slug resolution failed: %s", exc)

    # Compute budget-scaled limits (minimum 3 to always load some intelligence)
    specialty_limit = max(3, int(_MAX_SPECIALTY * budget_multiplier))
    org_limit = max(3, int(_MAX_ORG * budget_multiplier))

    # ------------------------------------------------------------------
    # Step 1 — Specialty insights (universal — no clearance filter)
    # ------------------------------------------------------------------
    if resolved_ids:
        try:
            async with pool.connection() as db:
                result = await db.query(
                    """
                    SELECT *, confidence FROM insight
                    WHERE specialty IN $ids
                      AND status = 'active'
                    ORDER BY confidence DESC
                    LIMIT $limit
                    """,
                    {"ids": resolved_ids, "limit": specialty_limit},
                )
            rows = parse_rows(result)
            specialty_insights = [
                {
                    "id": str(r.get("id", "")),
                    "content": r.get("content", ""),
                    "confidence": r.get("confidence", 0),
                    "tier": r.get("tier", ""),
                    "insight_type": r.get("insight_type", ""),
                    "trust": r.get("trust"),
                    "product": str(r.get("product") or "product:platform"),
                    "status": r.get("status", "active"),
                    "created_at": r.get("created_at"),
                    "source_observations": r.get("source_observations") or [],
                    "source_graph": "specialty",
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Specialty insight load failed: %s", exc)

    # ------------------------------------------------------------------
    # Step 1b — Affinity supplementary loading (fills gaps)
    # ------------------------------------------------------------------
    if gaps:
        try:
            from core.engine.intelligence.affinities import get_affinities_for_specialties

            gap_ids = [str(r["id"]) for r in spec_rows if r.get("slug") in gaps]
            if gap_ids:
                affinities = await get_affinities_for_specialties(gap_ids, product_id)
                supplement_ids: set[str] = set()
                loaded_ids = {str(r["id"]) for r in spec_rows}
                for aff in affinities:
                    a_str = str(aff.get("specialty_a", ""))
                    b_str = str(aff.get("specialty_b", ""))
                    linked = b_str if a_str in gap_ids else a_str
                    if linked not in loaded_ids:
                        supplement_ids.add(linked)
                if supplement_ids:
                    supp_ids_parsed = [parse_record_id(sid) for sid in supplement_ids]
                    async with pool.connection() as db:
                        supp_result = await db.query(
                            """SELECT *, confidence FROM insight
                               WHERE specialty IN $ids AND status = 'active'
                               ORDER BY confidence DESC LIMIT 10""",
                            {"ids": supp_ids_parsed},
                        )
                    supp_insights = parse_rows(supp_result)
                    specialty_insights.extend(
                        {
                            "id": str(r.get("id", "")),
                            "content": r.get("content", ""),
                            "confidence": r.get("confidence", 0),
                            "tier": r.get("tier", ""),
                            "insight_type": r.get("insight_type", ""),
                            "trust": r.get("trust"),
                            "product": str(r.get("product") or "product:platform"),
                            "status": r.get("status", "active"),
                            "created_at": r.get("created_at"),
                            "source_observations": r.get("source_observations") or [],
                            "source_graph": "specialty",
                        }
                        for r in supp_insights
                    )
        except Exception as exc:
            logger.warning("Affinity supplementary loading failed: %s", exc)

    # ------------------------------------------------------------------
    # Step 2 — Org insights (clearance-filtered)
    # ------------------------------------------------------------------
    if org_context:
        first_domain = org_context[0]
        clearance_filter, clearance_params = clearance_where_clause(first_domain, None)
        try:
            async with pool.connection() as db:
                result = await db.query(
                    f"""
                    SELECT *, confidence FROM insight
                    WHERE product = <record>$product
                      AND status = 'active'
                      AND (domain.slug IN $slugs OR subdomain.slug IN $slugs)
                      AND {clearance_filter}
                    ORDER BY confidence DESC
                    LIMIT $limit
                    """,
                    {
                        "product": org_record,
                        "slugs": org_context,
                        "limit": org_limit,
                        **clearance_params,
                    },
                )
            rows = parse_rows(result)
            org_insights = [
                {
                    "id": str(r.get("id", "")),
                    "content": r.get("content", ""),
                    "confidence": r.get("confidence", 0),
                    "tier": r.get("tier", ""),
                    "insight_type": r.get("insight_type", ""),
                    "trust": r.get("trust"),
                    "product": str(r.get("product") or product_id),
                    "status": r.get("status", "active"),
                    "created_at": r.get("created_at"),
                    "source_observations": r.get("source_observations") or [],
                    "source_graph": "org",
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Org insight load failed: %s", exc)

    # ------------------------------------------------------------------
    # Step 3 — Merge
    # ------------------------------------------------------------------
    snapshot = _merge_snapshot(
        specialty_insights=specialty_insights,
        org_insights=org_insights,
        specialties_loaded=specialties_loaded,
        org_context_loaded=org_context_loaded,
        gaps=gaps,
    )

    # ------------------------------------------------------------------
    # Step 3b — Re-rank merged insights by utilization score
    # ------------------------------------------------------------------
    snapshot["insights"] = await _rerank_by_utilization(snapshot["insights"], product_id)

    # ------------------------------------------------------------------
    # Step 3c — Relationship-aware expansion (1-hop Cognify edges)
    # ------------------------------------------------------------------
    await expand_snapshot_relationships(snapshot, product_id)

    # ------------------------------------------------------------------
    # Step 4 — Augment: failure memory + recent decisions
    # These match the keys that load_intelligence() provides so both
    # execution paths produce identical snapshot shapes.
    # ------------------------------------------------------------------
    from core.engine.orchestrator.loader import (
        _load_durable_human_guidance,
        _load_failure_memory,
        _load_recent_decisions,
    )

    # Keep the specialty path semantically aligned with load_intelligence:
    # human preferences/corrections must not disappear merely because the
    # classifier also resolved specialty slugs.
    if discipline:
        try:
            guidance = await _load_durable_human_guidance(discipline, product_id)
            seen = {(item.get("content"), item.get("insight_type")) for item in snapshot["insights"]}
            for item in guidance:
                key = (item.get("content"), item.get("insight_type"))
                if key not in seen:
                    snapshot["insights"].append({**item, "source_graph": "human"})
                    seen.add(key)
            snapshot["total_count"] = len(snapshot["insights"])
        except Exception as exc:
            logger.warning("Dual-loader durable-guidance load failed (non-fatal): %s", exc)

    snapshot["failure_memory"] = []
    if discipline:
        try:
            snapshot["failure_memory"] = await _load_failure_memory(discipline, product_id)
        except Exception as exc:
            logger.warning("Dual-loader failure_memory load failed (non-fatal): %s", exc)

    snapshot["decisions"] = []
    try:
        snapshot["decisions"] = await _load_recent_decisions(product_id, discipline=discipline)
    except Exception as exc:
        logger.warning("Dual-loader decisions load failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Step 4b — STaR traces: proven reasoning patterns for this discipline
    # ------------------------------------------------------------------
    snapshot["star_traces"] = []
    if discipline:
        try:
            from core.engine.orchestrator.loader import _load_star_traces

            snapshot["star_traces"] = await _load_star_traces(pool, product_id, discipline)
        except Exception as exc:
            logger.warning("Dual-loader star_traces load failed (non-fatal): %s", exc)

    return snapshot


# ---------------------------------------------------------------------------
# Pure merge function (also exported for unit testing)
# ---------------------------------------------------------------------------


def _merge_snapshot(
    specialty_insights: list[dict],
    org_insights: list[dict],
    specialties_loaded: list[str],
    org_context_loaded: list[str],
    gaps: list[str],
) -> dict:
    """Merge specialty and org insights into a unified snapshot dict.

    The returned dict is backward-compatible with the existing executor's
    expectations: ``insights``, ``total_count``, ``recent_signals``,
    ``raw_context`` are always present.
    """
    # Deduplicate by id, specialty insights take precedence
    seen: set[str] = set()
    merged: list[dict] = []

    for item in specialty_insights + org_insights:
        item_id = item.get("id", "")
        if item_id and item_id in seen:
            continue
        seen.add(item_id)
        merged.append(
            {
                "id": item_id,
                "content": item.get("content", ""),
                "confidence": item.get("confidence", 0),
                "tier": item.get("tier", ""),
                "insight_type": item.get("insight_type", ""),
                "trust": item.get("trust"),  # carry through so _rerank_by_utilization can trust-weight
                "source_graph": item.get("source_graph", ""),
            }
        )

    return {
        # Backward-compat keys (same shape as loader.py output)
        "insights": merged,
        "total_count": len(merged),
        "recent_signals": [],
        "raw_context": [],
        # Pipeline keys — populated by load_dual_intelligence() after merge
        "failure_memory": [],
        "decisions": [],
        # Dual-graph specific keys
        "specialty_insights": specialty_insights,
        "org_insights": org_insights,
        "specialties_loaded": specialties_loaded,
        "org_context_loaded": org_context_loaded,
        "gaps": gaps,
    }
