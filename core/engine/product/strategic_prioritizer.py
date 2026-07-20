# engine/product/strategic_prioritizer.py
"""S4 — Strategic Prioritization: 5-dimension scoring that blends quality gaps
with competitive intelligence, market timing, and compounding opportunity data.

Extends ProductPrioritizer with:
    gap_severity  × 0.25  — lower quality score = higher urgency (unchanged)
    defensibility × 0.20  — pain depth × low competitor coverage proxy
    market_timing × 0.20  — whitespace timing coefficient + signal density
    leverage      × 0.20  — blast radius proxy (cross-capability dependencies)
    compounding   × 0.15  — whitespace score as compounding potential signal

Activates via ace_recommend() when whitespace + competitive data is present.
Falls back to base 3-dimension scoring gracefully when no enrichment data exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.engine.core.db import parse_rows
from core.engine.product.prioritizer import ProductPrioritizer

logger = logging.getLogger(__name__)


@dataclass
class RankedRecommendation:
    pillar: str
    discipline: Optional[str]
    score: float
    floor: float
    gap: float
    ambition_relevance: float
    rank: float
    blocking_patterns: list[str] = field(default_factory=list)
    rationale: str = ""
    consecutive_briefings_at_top: int = 0


STRATEGIC_WEIGHTS = {
    "gap_severity": 0.25,
    "ambition_relevance": 0.20,
    "defensibility": 0.15,
    "market_timing": 0.15,
    "leverage": 0.15,
    "compounding": 0.10,
}


def _dedup_by_pillar_discipline(enriched: list[dict]) -> list[dict]:
    """Collapse multiple capability-rows that share a (pillar, discipline) tuple.

    Without dedup, briefing top_recommendations renders the same discipline
    repeatedly (e.g. five "experience.accessibility" lines for five capabilities
    each below floor). The voice surface needs one line per (pillar, discipline)
    pair — pick the worst gap as the representative, since that's what the
    rationale should call out.

    Pure function: takes the post-enrichment dicts, returns a deduped list.
    Sort order is restored by the caller.
    """
    by_key: dict[tuple[str, str], dict] = {}
    for row in enriched:
        key = (row.get("pillar", ""), row.get("discipline") or "")
        existing = by_key.get(key)
        if existing is None or row.get("gap", 0.0) > existing.get("gap", 0.0):
            by_key[key] = row
    return list(by_key.values())


class StrategicPrioritizer(ProductPrioritizer):
    """5-dimension strategic scorer for ace_recommend().

    Extends the base 3-dimension prioritizer by pulling enrichment data
    (whitespace opportunities, competitive signals) in one query pass,
    then blending them into a richer strategic score.

    Returned items include a 'dimensions' dict showing the per-dimension
    breakdown so callers can explain why something is ranked highly.
    """

    async def prioritize(self, product_id: str) -> list[dict]:
        """Score and rank work items by strategic priority.

        Behind the `phase_aware_ranking_enabled` feature flag, results are
        re-scored with floor-based gap_severity, ambition_relevance, and decay,
        and enriched with pillar/floor/gap/rank/blocking_patterns/rationale.

        With the flag off (default), returns the legacy 5-dimension output.
        """
        legacy_results = await self._legacy_prioritize(product_id)

        from core.engine.product.feature_flags import is_phase_aware_ranking_enabled

        if not await is_phase_aware_ranking_enabled(self._pool, product_id):
            return legacy_results

        return await self._phase_aware_rerank(product_id, legacy_results)

    async def _phase_aware_rerank(self, product_id: str, legacy_results: list[dict]) -> list[dict]:
        """Re-score legacy results with floor + ambition_relevance + decay."""
        from core.engine.product.ambition import AmbitionRepository
        from core.engine.product.ambition_relevance import compute_ambition_relevance
        from core.engine.product.phase_floors import effective_floor
        from core.engine.product.pillars import LEGACY_DIM_TO_PILLAR
        from core.engine.product.recommendation_decay import (
            apply_decay,
            get_decay_state,
        )

        repo = AmbitionRepository(self._pool)
        ambition = await repo.get(product_id)
        if ambition is None or ambition.phase is None:
            return legacy_results

        async with self._pool.connection() as db:
            prod_rows = parse_rows(
                await db.query(
                    "SELECT product_type, product_scale FROM <record>$pid",
                    {"pid": product_id},
                )
            )
        pt = prod_rows[0].get("product_type", "ai_native") if prod_rows else "ai_native"
        scale = prod_rows[0].get("product_scale", "application") if prod_rows else "application"

        required_patterns = (
            ambition.target.demo_target.required_patterns if ambition.target and ambition.target.demo_target else []
        )

        enriched = []
        for r in legacy_results:
            dim = r.get("dimension", "")
            pillar_enum = LEGACY_DIM_TO_PILLAR.get(dim)
            if pillar_enum is None:
                continue
            floor = effective_floor(pillar_enum, ambition.phase.current, pt, scale)
            score = float(r.get("current_score", 0.0) or 0.0)
            gap = max(0.0, floor - score)
            gap_severity = (gap / max(0.01, floor)) if floor > 0.0 else 0.0
            amb_rel = await compute_ambition_relevance(self._pool, pillar_enum.value, None, required_patterns)
            dims = r.get("dimensions", {}) or {}
            rank = (
                STRATEGIC_WEIGHTS["gap_severity"] * gap_severity
                + STRATEGIC_WEIGHTS["ambition_relevance"] * amb_rel
                + STRATEGIC_WEIGHTS["defensibility"] * float(dims.get("defensibility", 0.0))
                + STRATEGIC_WEIGHTS["market_timing"] * float(dims.get("market_timing", 0.0))
                + STRATEGIC_WEIGHTS["leverage"] * float(dims.get("leverage", 0.0))
                + STRATEGIC_WEIGHTS["compounding"] * float(dims.get("compounding", 0.0))
            )
            rec_id = f"{product_id}:{dim}"
            decay_state = await get_decay_state(self._pool, rec_id, product_id)
            rank = apply_decay(rank, decay_state.consecutive_briefings_at_top)

            blocking_patterns = list(required_patterns) if amb_rel > 0.5 else []
            rationale = (
                f"{pillar_enum.value} below {ambition.phase.current.upper()} floor; "
                f"blocks {', '.join(blocking_patterns) if blocking_patterns else 'no demo pattern'}; "
                f"floor {floor:.2f}, score {score:.2f}, gap {gap:.2f}"
            )
            enriched.append(
                {
                    **r,
                    "pillar": pillar_enum.value,
                    "discipline": dim,
                    "floor": floor,
                    "gap": gap,
                    "ambition_relevance": amb_rel,
                    "rank": rank,
                    "blocking_patterns": blocking_patterns,
                    "rationale": rationale,
                    "consecutive_briefings_at_top": decay_state.consecutive_briefings_at_top,
                }
            )

        deduped = _dedup_by_pillar_discipline(enriched)
        deduped.sort(key=lambda x: (x["rank"], x["gap"]), reverse=True)
        return deduped

    async def _legacy_prioritize(self, product_id: str) -> list[dict]:
        """Original 5-dimension scorer; preserved for shadow-mode and flag-off path."""
        self._validate_product_id(product_id)

        try:
            async with self._pool.connection() as db:
                cap_result = await db.query(
                    "SELECT * FROM capability WHERE product = <record>$product AND status != 'deprecated'",
                    {"product": product_id},
                )
                capabilities = parse_rows(cap_result)
                cap_by_id = {str(c["id"]): c for c in capabilities}

                gap_result = await db.query(
                    "SELECT * FROM capability_quality WHERE product = <record>$product AND score < 0.6 ORDER BY score",
                    {"product": product_id},
                )
                gaps = parse_rows(gap_result)

                # Load enrichment data in parallel with gap query
                whitespace_by_slug = await _load_whitespace(product_id, db)
                signal_density = await _load_signal_density(product_id, db)

        except Exception as exc:
            from core.engine.core.exceptions import DatabaseError

            raise DatabaseError(f"Failed to load strategic prioritization data for {product_id}: {exc}") from exc

        scored = []
        for gap in gaps:
            cap_id = str(gap.get("capability", ""))
            cap = cap_by_id.get(cap_id, {})
            slug = cap.get("slug", "")

            ws_data = whitespace_by_slug.get(slug, {})
            signal_score = signal_density.get(slug, 0.0)

            # blast_radius from existing gap data
            gap_count = len(gap.get("gaps", []))
            leverage = min(1.0, gap_count / 5.0)

            score, dimensions = _strategic_score(
                gap=gap,
                capability=cap,
                ws_data=ws_data,
                signal_score=signal_score,
                leverage=leverage,
            )

            scored.append(
                {
                    "type": "gap",
                    "capability_slug": slug or "unknown",
                    "dimension": gap.get("dimension", "unknown"),
                    "current_score": gap.get("score", 0),
                    "gaps": gap.get("gaps", []),
                    "priority_score": score,
                    "dimensions": dimensions,
                }
            )

        scored.sort(key=lambda x: x["priority_score"], reverse=True)
        logger.debug(
            "Strategic prioritization: %d gaps for product=%s (top: %s %.3f)",
            len(scored),
            product_id,
            scored[0]["capability_slug"] if scored else "none",
            scored[0]["priority_score"] if scored else 0.0,
        )
        return scored


async def _load_whitespace(product_id: str, db) -> dict:
    """Return {slug: {pain_intensity, timing_coefficient, whitespace_score}} from whitespace_opportunity."""
    try:
        rows = parse_rows(
            await db.query(
                """SELECT slug, pain_intensity, timing_coefficient, whitespace_score
                   FROM whitespace_opportunity
                   WHERE product = <record>$product""",
                {"product": product_id},
            )
        )
        return {r["slug"]: r for r in rows if r.get("slug")}
    except Exception:
        return {}


async def _load_signal_density(product_id: str, db) -> dict:
    """Return {slug_keyword: 0.0-1.0} based on recent competitive signal volume.

    A high signal count for a topic means the market is moving, boosting market_timing.
    Maps signal titles (lowercased, underscored) to a normalized density 0-1.
    """
    try:
        rows = parse_rows(
            await db.query(
                """SELECT title, count() AS signal_count
                   FROM competitive_signal
                   WHERE product = <record>$product
                     AND created_at > time::now() - 30d
                   GROUP BY title
                   LIMIT 50""",
                {"product": product_id},
            )
        )
        return {
            r.get("title", "").lower().replace(" ", "_"): min(1.0, (r.get("signal_count") or 0) / 5.0)
            for r in rows
            if r.get("title")
        }
    except Exception:
        return {}


def _strategic_score(
    gap: dict,
    capability: dict,
    ws_data: dict,
    signal_score: float,
    leverage: float,
) -> tuple[float, dict]:
    """Compute 5-dimension strategic score.

    Returns (score, dimensions_dict) so callers can surface breakdowns.
    All inputs are clamped to [0, 1] to defend against bad data.
    """
    # D1: gap_severity — same as base scorer
    raw_score = gap.get("score", 0.5)
    quality_score = max(0.0, min(1.0, float(raw_score) if raw_score is not None else 0.5))
    gap_severity = 1.0 - quality_score

    # D2: defensibility — pain depth weighted by low competitor coverage
    # High pain + competitor not covering it = defensible market position
    pain = float(ws_data.get("pain_intensity") or 0.5)
    ws_score_raw = float(ws_data.get("whitespace_score") or 0.0)
    defensibility = max(0.0, min(1.0, pain * 0.6 + ws_score_raw * 0.4))

    # D3: market_timing — whitespace timing_coefficient boosted by live signal density
    ws_timing = float(ws_data.get("timing_coefficient") or 0.5)
    market_timing = max(0.0, min(1.0, max(ws_timing, signal_score)))

    # D4: leverage — blast radius proxy from gap count (foundational caps have many gaps)
    leverage_score = max(0.0, min(1.0, leverage))

    # D5: compounding — whitespace score is the best single proxy for "makes others better"
    compounding = max(0.0, min(1.0, ws_score_raw))

    score = (
        gap_severity * STRATEGIC_WEIGHTS["gap_severity"]
        + defensibility * STRATEGIC_WEIGHTS["defensibility"]
        + market_timing * STRATEGIC_WEIGHTS["market_timing"]
        + leverage_score * STRATEGIC_WEIGHTS["leverage"]
        + compounding * STRATEGIC_WEIGHTS["compounding"]
    )

    dimensions = {
        "gap_severity": round(gap_severity, 3),
        "defensibility": round(defensibility, 3),
        "market_timing": round(market_timing, 3),
        "leverage": round(leverage_score, 3),
        "compounding": round(compounding, 3),
    }

    logger.debug(
        "Strategic scored %s/%s: sev=%.2f def=%.2f tim=%.2f lev=%.2f cmp=%.2f → %.3f",
        capability.get("slug", "?"),
        gap.get("dimension", "?"),
        gap_severity,
        defensibility,
        market_timing,
        leverage_score,
        compounding,
        score,
    )

    return round(score, 4), dimensions
