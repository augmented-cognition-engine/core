# engine/orchestrator/loader.py
"""Load intelligence from the graph for a given discipline.

Filters insights by discipline tag + optional specialty tags.
Temporal read model: cognitive mode determines which pipeline tiers are read.
Returns a snapshot dict stored on the task record.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.graph.insight_neighbors import expand_snapshot_relationships
from core.engine.orchestrator.trust_ranking import trust_weighted

logger = logging.getLogger(__name__)

_MAX_PER_TIER = 10

_TEMPORAL_MODES = {"deliberative", "exploratory", "reflective", "conversational"}
_MEMORY_MODES = {"exploratory"}


async def load_intelligence(
    discipline: str = "",
    product_id: str = "",
    mode: str = "reactive",
    specialties: list[str] | None = None,
    # Keep backward compat — if domain_path passed, convert
    domain_path: str = "",
    # Confidence routing: when discipline confidence is low, also load these
    adjacent_disciplines: list[str] | None = None,
    # Topical filter: FTS on tags field (insight_tags_search index, v084)
    topic_filter: str | None = None,
) -> dict:
    """Load relevant insights for a discipline. Mode determines read depth.

    - reactive/procedural: insights + specialties only (proven knowledge)
    - deliberative/reflective/conversational: + recent observations (unverified)
    - exploratory: + raw memory (maximum context)

    Backward compat: if domain_path is provided and discipline is empty,
    discipline is derived from the first segment of domain_path.
    """
    # Backward compat: derive discipline from domain_path when not explicitly set
    if not discipline and domain_path:
        discipline = domain_path.split(".")[0]

    # Confidence routing: expand query to adjacent disciplines when provided
    discipline_filter = [discipline] if discipline else []
    if adjacent_disciplines:
        discipline_filter.extend(d for d in adjacent_disciplines if d not in discipline_filter)

    # Build optional topic clause (FTS on tags — insight_tags_search index, v084)
    topic_clause = "AND tags @@ $topic" if topic_filter else ""

    async with pool.connection() as db:
        if specialties:
            # Load insights tagged with any of the specialty slugs OR discipline(s)
            result = await db.query(
                f"""SELECT *, confidence FROM insight
                   WHERE product = <record>$product
                     AND status = 'active'
                     AND (tags CONTAINSANY $specialties OR tags CONTAINSANY $disciplines)
                     {topic_clause}
                   ORDER BY confidence DESC
                   LIMIT $limit""",
                {
                    "product": product_id,
                    "specialties": specialties,
                    "disciplines": discipline_filter,
                    "limit": _MAX_PER_TIER * 4,
                    **({"topic": topic_filter} if topic_filter else {}),
                },
            )
        else:
            # Filter by discipline tag(s) — expanded when adjacent_disciplines provided
            result = await db.query(
                f"""SELECT *, confidence FROM insight
                   WHERE product = <record>$product
                     AND status = 'active'
                     AND tags CONTAINSANY $disciplines
                     {topic_clause}
                   ORDER BY confidence DESC
                   LIMIT $limit""",
                {
                    "product": product_id,
                    "disciplines": discipline_filter,
                    "limit": _MAX_PER_TIER * 4,
                    **({"topic": topic_filter} if topic_filter else {}),
                },
            )

        # SurrealDB v3 returns a flat list of dicts (not nested [[...]])
        if isinstance(result, list) and result and isinstance(result[0], dict) and "result" not in result[0]:
            insights = result
        elif isinstance(result, list) and result and isinstance(result[0], list):
            insights = result[0]  # legacy nested format
        else:
            insights = []

    # Trust-weighted ranking: the SQL fetched a generous candidate set by confidence; re-rank by
    # confidence × trust so insights explicitly scored low-trust (self-generated reasoning conclusions)
    # rank below trusted human/external evidence. trust=None (un-reconciled) is neutral, so this only
    # ever demotes known-low-trust content; a stable sort preserves SQL confidence order within ties.
    insights.sort(key=lambda i: trust_weighted(i.get("confidence", 0.0), i.get("trust")), reverse=True)

    # Track which specialty slugs actually contributed at least one insight
    matched_specialties: set[str] = set()
    if specialties:
        for insight in insights:
            tags = insight.get("tags", [])
            for tag in tags:
                if tag in specialties:
                    matched_specialties.add(tag)

    loaded = {
        "discipline": discipline,
        "adjacent_disciplines": adjacent_disciplines or [],
        "disciplines_loaded": discipline_filter,
        "specialties": specialties or [],
        "insights": [
            {
                "id": str(i.get("id", "")),
                "content": i.get("content", ""),
                "confidence": i.get("confidence", 0),
                "tier": i.get("tier", ""),
                "insight_type": i.get("insight_type", ""),
                "product": str(i.get("product") or product_id),
                "trust": i.get("trust"),
                "status": i.get("status", "active"),
                "created_at": i.get("created_at"),
                "source_observations": i.get("source_observations") or [],
            }
            for i in insights[: _MAX_PER_TIER * 4]
        ],
        "total_count": len(insights),
        "recent_signals": [],
        "raw_context": [],
        "specialties_loaded": list(matched_specialties),
    }

    # Relationship-aware expansion (1-hop Cognify edges) — same shared helper as
    # dual_loader, so ace_load and the reactive loader surface synapses too.
    await expand_snapshot_relationships(loaded, product_id)

    # Temporal reads: based on cognitive mode
    if mode in _TEMPORAL_MODES:
        try:
            loaded["recent_signals"] = await _load_recent_observations(discipline, product_id)
        except Exception as exc:
            logger.warning("Temporal observation load failed: %s", exc)

    if mode in _MEMORY_MODES:
        try:
            loaded["raw_context"] = await _load_recent_memory(product_id)
        except Exception as exc:
            logger.warning("Temporal memory load failed: %s", exc)

    # Failure memory: Reflexion-style context from past failures on similar tasks
    loaded["failure_memory"] = []
    try:
        loaded["failure_memory"] = await _load_failure_memory(discipline, product_id)
    except Exception as exc:
        logger.warning("Failure memory load failed (non-fatal): %s", exc)

    # STaR traces: top-3 successful reasoning patterns for this discipline
    loaded["star_traces"] = await _load_star_traces(pool, product_id, discipline)

    # Recent decisions: discipline-matched first, recency padding
    loaded["decisions"] = []
    try:
        loaded["decisions"] = await _load_recent_decisions(product_id, discipline=discipline)
    except Exception as exc:
        logger.warning("Decision history load failed (non-fatal): %s", exc)

    # Calibration weights: per-archetype scores from closed predictions (reconciler output)
    loaded["calibration_weights"] = {}
    try:
        loaded["calibration_weights"] = await _load_calibration_weights(discipline, product_id)
    except Exception as exc:
        logger.warning("Calibration weight load failed (non-fatal): %s", exc)

    # Architectural memory: cross-session recall of architecture/trade_off decisions
    loaded["arch_decisions"] = []
    try:
        loaded["arch_decisions"] = await _load_arch_decisions(product_id)
    except Exception as exc:
        logger.warning("Architectural memory load failed (non-fatal): %s", exc)

    # Human corrections/preferences are durable control inputs, not transient
    # activity. ace_load surfaces them after synthesis; task reasoning must too.
    # This deliberately runs after the established tier reads so older mocked
    # query sequences and degradation behavior remain stable.
    try:
        guidance = await _load_durable_human_guidance(discipline, product_id)
        seen = {(item.get("content"), item.get("insight_type")) for item in loaded["insights"]}
        for item in guidance:
            key = (item.get("content"), item.get("insight_type"))
            if key not in seen:
                loaded["insights"].append(item)
                seen.add(key)
        loaded["total_count"] = len(loaded["insights"])
    except Exception as exc:
        logger.warning("Durable human-guidance load failed (non-fatal): %s", exc)

    return loaded


async def _load_calibration_weights(discipline: str, product_id: str) -> dict[str, float]:
    """Load per-archetype calibration scores for this discipline.

    Returns {archetype: score} — empty dict when no data or on error.
    Populated by engine/foresight/reconciler.py when predictions are closed.
    """
    async with pool.connection() as db:
        result = await db.query(
            """SELECT archetype, calibration_score FROM archetype_calibration
               WHERE product = <record>$product AND discipline = $discipline
               ORDER BY calibration_score DESC""",
            {"product": product_id, "discipline": discipline},
        )
    rows = parse_rows(result)
    return {
        row["archetype"]: float(row["calibration_score"])
        for row in rows
        if "archetype" in row and "calibration_score" in row
    }


async def _load_star_traces(pool, product_id: str, discipline: str) -> list[dict]:
    """Load top-3 successful reasoning traces for this discipline. Returns [] on error."""
    try:
        from core.engine.cognition.star_trace import load_star_traces

        return await load_star_traces(pool, product_id, discipline, limit=3)
    except Exception:
        return []


async def _load_failure_memory(
    discipline: str,
    product_id: str,
    limit: int = 20,
    top_n: int = 7,
) -> list[dict]:
    """Load and aggregate failure patterns for this discipline (Reflexion read path).

    Aggregates gaps across recent failures and returns top recurring patterns
    with occurrence counts instead of raw entries.

    Returns: [{"pattern": str, "count": int}, ...] sorted by count desc.
    """
    async with pool.connection() as db:
        result = await db.query(
            """SELECT gaps, verdict, discipline, created_at FROM failure_memory
               WHERE product = <record>$product
                 AND discipline = $discipline
               ORDER BY created_at DESC
               LIMIT $limit""",
            {"product": product_id, "discipline": discipline, "limit": limit},
        )
        entries = parse_rows(result)

    if not entries:
        return []

    gap_counts: dict[str, int] = {}
    for entry in entries:
        for gap in entry.get("gaps", []):
            gap_str = gap.strip()
            if gap_str:
                gap_counts[gap_str] = gap_counts.get(gap_str, 0) + 1

    return [
        {"pattern": gap, "count": count} for gap, count in sorted(gap_counts.items(), key=lambda x: x[1], reverse=True)
    ][:top_n]


async def _load_recent_decisions(
    product_id: str,
    discipline: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Load relevant decisions for this product, discipline-matched when possible.

    Precedence: discipline_hint match first (most relevant), then recency padding
    to fill the limit. Deduplicates by id to prevent double-loading.
    """
    async with pool.connection() as db:
        results: list[dict] = []
        seen_ids: set[str] = set()

        # 1. Discipline-matched decisions (highest relevance)
        if discipline:
            disc_result = await db.query(
                """SELECT title, decision_type, rationale, outcome, discipline_hint, created_at, id
                   FROM decision
                   WHERE product = <record>$product
                     AND discipline_hint = $discipline
                     AND outcome != 'superseded'
                   ORDER BY created_at DESC
                   LIMIT $limit""",
                {"product": product_id, "discipline": discipline, "limit": limit},
            )
            for row in parse_rows(disc_result):
                row_id = str(row.get("id", ""))
                if row_id not in seen_ids:
                    seen_ids.add(row_id)
                    results.append(row)

        # 2. Recency padding — fill remaining slots from recent decisions
        remaining = limit - len(results)
        if remaining > 0:
            recent_result = await db.query(
                """SELECT title, decision_type, rationale, outcome, discipline_hint, created_at, id
                   FROM decision
                   WHERE product = <record>$product
                     AND outcome != 'superseded'
                   ORDER BY created_at DESC
                   LIMIT $pad""",
                {"product": product_id, "pad": limit * 2},  # over-fetch to account for dedup
            )
            for row in parse_rows(recent_result):
                if len(results) >= limit:
                    break
                row_id = str(row.get("id", ""))
                if row_id not in seen_ids:
                    seen_ids.add(row_id)
                    results.append(row)

        return results


async def _load_recent_observations(
    discipline: str,
    product_id: str,
    window_minutes: int = 60,
    limit: int = 10,
) -> list[dict]:
    """Load unsynthesized observations from the last N minutes matching discipline hint."""
    async with pool.connection() as db:
        result = await db.query(
            """SELECT content, observation_type, confidence, created_at
               FROM observation
               WHERE product = <record>$product
                 AND status = 'pending'
                 AND (discipline_hint CONTAINS $discipline OR domain_hint CONTAINS $discipline)
                 AND created_at > time::now() - $window
               ORDER BY confidence DESC
               LIMIT $limit""",
            {"product": product_id, "discipline": discipline, "window": f"{window_minutes}m", "limit": limit},
        )
        return parse_rows(result)


async def _load_durable_human_guidance(
    discipline: str,
    product_id: str,
    limit: int = 10,
) -> list[dict]:
    """Load human corrections/preferences even after synthesis processed them."""
    async with pool.connection() as db:
        result = await db.query(
            """SELECT content, observation_type AS insight_type, confidence, created_at, id
               FROM observation
               WHERE product = <record>$product
                 AND observation_type IN ['correction', 'preference']
                 AND (discipline_hint CONTAINS $discipline
                      OR domain_path CONTAINS $discipline
                      OR domain_hint CONTAINS $discipline)
               ORDER BY created_at DESC
               LIMIT $limit""",
            {"product": product_id, "discipline": discipline, "limit": limit},
        )
    return [
        {
            "id": str(row.get("id", "")),
            "content": row.get("content", ""),
            "confidence": row.get("confidence", 0),
            "tier": "human_guidance",
            "insight_type": row.get("insight_type", ""),
        }
        for row in parse_rows(result)
    ]


async def _load_recent_memory(
    product_id: str,
    window_minutes: int = 30,
    limit: int = 20,
) -> list[dict]:
    """Load recent unprocessed memory chunks."""
    async with pool.connection() as db:
        result = await db.query(
            """SELECT content, memory_type, source, created_at
               FROM memory
               WHERE product = <record>$product
                 AND processed = false
                 AND created_at > time::now() - $window
               ORDER BY created_at DESC
               LIMIT $limit""",
            {
                "product": product_id,
                "window": f"{window_minutes}m",
                "limit": limit,
            },
        )
        return parse_rows(result)


async def _load_arch_decisions(
    product_id: str,
    limit: int = 10,
) -> list[dict]:
    """Cross-session architectural memory — all architecture/trade_off decisions.

    No discipline filter: captures every architectural choice ever recorded,
    giving full recall rather than the discipline-scoped 5-item window that
    _load_recent_decisions provides. Ordered by recency so the latest thinking
    leads.
    """
    async with pool.connection() as db:
        result = await db.query(
            """SELECT title, decision_type, rationale, outcome, discipline_hint, created_at, id
               FROM decision
               WHERE product = <record>$product
                 AND decision_type IN ['architecture', 'trade_off']
                 AND outcome != 'superseded'
               ORDER BY created_at DESC
               LIMIT $limit""",
            {"product": product_id, "limit": limit},
        )
    return parse_rows(result)
