# engine/sentinel/engines/whitespace_engine.py
"""S2 — Whitespace Engine.

Scores market opportunities where ACE can differentiate by combining three
input streams:

1. Competitor blind spots  — capabilities in competitor_capability with low/no
   Tier-1 competitor coverage (low max_competitor_coverage)
2. User pain signals       — community scanner "opportunity" signals (high
   relevance_score = users are vocal about this pain)
3. Ecosystem gaps          — capabilities with poor quality scores (score < 0.4)
   and no tracked competitor covering them

Formula:
    whitespace_score = pain_intensity
                     × user_count
                     × (1 - max_competitor_coverage)
                     × feasibility_coefficient
                     × timing_coefficient

All coefficients are floats in [0, 1]. Runs Sunday 6 AM (after competitive
observer on Monday, but the weekly cycle starts Sunday).

Pre-seeded opportunities from the roadmap analysis are re-scored each run so
they benefit from live data as competitors evolve.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

# Pre-seeded top whitespace opportunities from roadmap analysis.
# These bootstrap the table before live competitive data arrives.
_SEEDED_OPPORTUNITIES: list[dict] = [
    {
        "slug": "cost_intelligence",
        "title": "Cost Intelligence from code patterns",
        "description": (
            "Analyze code patterns to predict infrastructure and API cost before deployment. "
            "No competitor connects code structure to runtime cost estimates."
        ),
        "source": "seeded",
        "pain_intensity": 0.92,
        "user_count": 0.75,
        "max_competitor_coverage": 0.05,
        "feasibility_coefficient": 0.80,
        "timing_coefficient": 0.85,
    },
    {
        "slug": "runtime_enforcement",
        "title": "Runtime enforcement (enforce before violation)",
        "description": (
            "Block architectural violations at PR time rather than discovering them post-merge. "
            "Competitors do static analysis but not proactive enforcement tied to decisions."
        ),
        "source": "seeded",
        "pain_intensity": 0.88,
        "user_count": 0.70,
        "max_competitor_coverage": 0.10,
        "feasibility_coefficient": 0.85,
        "timing_coefficient": 0.80,
    },
    {
        "slug": "cross_session_architectural_memory",
        "title": "Cross-session architectural memory with full recall",
        "description": (
            "Persistent memory of every architectural decision, rationale, and evolution across "
            "all sessions. Competitors reset context on every conversation."
        ),
        "source": "seeded",
        "pain_intensity": 0.85,
        "user_count": 0.80,
        "max_competitor_coverage": 0.08,
        "feasibility_coefficient": 0.90,
        "timing_coefficient": 0.75,
    },
    {
        "slug": "nl_iac_from_code_graph",
        "title": "Natural-language IaC generation from code graph",
        "description": (
            "Generate production-ready infrastructure code by reading the repo graph — "
            "no templates, no manual scaffolding. Competitors generate generic IaC from prompts."
        ),
        "source": "seeded",
        "pain_intensity": 0.80,
        "user_count": 0.60,
        "max_competitor_coverage": 0.15,
        "feasibility_coefficient": 0.75,
        "timing_coefficient": 0.70,
    },
]


def _compute_score(opp: dict) -> float:
    """Compute whitespace score from coefficients."""
    return round(
        opp.get("pain_intensity", 0.5)
        * opp.get("user_count", 0.5)
        * (1.0 - opp.get("max_competitor_coverage", 0.0))
        * opp.get("feasibility_coefficient", 0.7)
        * opp.get("timing_coefficient", 0.6),
        4,
    )


async def _load_competitor_coverage(product_id: str, db) -> dict[str, float]:
    """Return {capability_slug: max_coverage_float} across Tier 1 competitors.

    Coverage mapping: "full" → 1.0, "partial" → 0.5, "none" → 0.0.
    Only Tier 1 competitors count — adjacent/aspirational don't define the bar.
    """
    _COVERAGE_MAP = {"full": 1.0, "partial": 0.5, "none": 0.0}

    try:
        rows = parse_rows(
            await db.query(
                """SELECT cc.capability_slug AS slug, cc.coverage AS coverage
                   FROM competitor_capability AS cc
                   JOIN competitor AS c ON c.name = cc.competitor AND c.product = cc.product
                   WHERE cc.product = <record>$product AND c.tier = 1""",
                {"product": product_id},
            )
        )
    except Exception as exc:
        logger.debug("whitespace_engine: coverage load failed: %s", exc)
        return {}

    coverage: dict[str, float] = {}
    for row in rows:
        slug = row.get("slug", "")
        val = _COVERAGE_MAP.get(row.get("coverage", "none"), 0.0)
        if slug:
            coverage[slug] = max(coverage.get(slug, 0.0), val)
    return coverage


async def _load_pain_signals(product_id: str, db) -> dict[str, float]:
    """Return {capability_slug: pain_intensity} from 'opportunity' community signals.

    Approximates user pain by mapping competitor complaints to capability domains.
    Uses average relevance_score of recent opportunity signals per competitor.
    """
    try:
        rows = parse_rows(
            await db.query(
                """SELECT competitor, relevance_score
                   FROM competitive_signal
                   WHERE product = <record>$product
                   AND relevance = 'opportunity'
                   AND created_at > time::now() - 60d""",
                {"product": product_id},
            )
        )
    except Exception as exc:
        logger.debug("whitespace_engine: pain signals load failed: %s", exc)
        return {}

    # Aggregate by competitor → avg relevance score → proxy for pain intensity
    by_comp: dict[str, list[float]] = {}
    for row in rows:
        comp = row.get("competitor", "")
        score = float(row.get("relevance_score", 0.5))
        if comp:
            by_comp.setdefault(comp, []).append(score)

    # We don't have capability→competitor mapping yet, return global pain signal
    if not by_comp:
        return {}

    all_scores = [s for scores in by_comp.values() for s in scores]
    global_pain = round(sum(all_scores) / len(all_scores), 4) if all_scores else 0.5
    return {"__global__": global_pain}


async def _upsert_opportunity(product_id: str, opp: dict, db) -> None:
    """Upsert a whitespace opportunity record."""
    score = _compute_score(opp)
    await db.query(
        """INSERT INTO whitespace_opportunity (
               product, slug, title, description, source,
               pain_intensity, user_count, max_competitor_coverage,
               feasibility_coefficient, timing_coefficient, whitespace_score
           ) VALUES (
               <record>$product, $slug, $title, $description, $source,
               $pain_intensity, $user_count, $max_competitor_coverage,
               $feasibility_coefficient, $timing_coefficient, $score
           )
           ON DUPLICATE KEY UPDATE
               title                  = $title,
               description            = $description,
               pain_intensity         = $pain_intensity,
               user_count             = $user_count,
               max_competitor_coverage = $max_competitor_coverage,
               feasibility_coefficient = $feasibility_coefficient,
               timing_coefficient     = $timing_coefficient,
               whitespace_score       = $score
        """,
        {
            "product": product_id,
            "slug": opp["slug"],
            "title": opp["title"],
            "description": opp.get("description", ""),
            "source": opp.get("source", "seeded"),
            "pain_intensity": opp.get("pain_intensity", 0.5),
            "user_count": opp.get("user_count", 0.5),
            "max_competitor_coverage": opp.get("max_competitor_coverage", 0.0),
            "feasibility_coefficient": opp.get("feasibility_coefficient", 0.7),
            "timing_coefficient": opp.get("timing_coefficient", 0.6),
            "score": score,
        },
    )


@register_engine(
    name="whitespace_engine",
    cron="0 6 * * sun",
    description="Compute whitespace opportunity scores from competitor coverage + community pain signals.",
)
async def run_whitespace_engine(product_id: str) -> dict:
    """Score market whitespace opportunities by combining:
    - Competitor blind spots (capability matrix, Tier 1 only)
    - User pain signals (community scanner opportunity signals)
    - Pre-seeded opportunities from roadmap analysis

    Writes/updates whitespace_opportunity records with computed scores.

    Returns: {opportunities_scored, top_score, top_slug}
    """
    results: dict = {"opportunities_scored": 0, "top_score": 0.0, "top_slug": ""}

    async with pool.connection() as db:
        coverage = await _load_competitor_coverage(product_id, db)
        pain_signals = await _load_pain_signals(product_id, db)
        global_pain = pain_signals.get("__global__", 0.5)

        # Score and upsert pre-seeded opportunities, enriched with live coverage
        for opp in _SEEDED_OPPORTUNITIES:
            enriched = dict(opp)
            slug = opp["slug"]

            # Override max_competitor_coverage from live matrix if available
            if slug in coverage:
                enriched["max_competitor_coverage"] = coverage[slug]

            # Nudge pain_intensity up if we have live community signals
            if global_pain > 0.5:
                enriched["pain_intensity"] = min(1.0, opp["pain_intensity"] + (global_pain - 0.5) * 0.1)

            await _upsert_opportunity(product_id, enriched, db)
            score = _compute_score(enriched)
            results["opportunities_scored"] += 1
            if score > results["top_score"]:
                results["top_score"] = score
                results["top_slug"] = slug

        # Score competitor blind spots from capability matrix (low/no coverage)
        for slug, max_cov in coverage.items():
            if max_cov < 0.3:  # competitor does this poorly — potential whitespace
                opp = {
                    "slug": f"blindspot__{slug}",
                    "title": f"Competitor blind spot: {slug.replace('_', ' ')}",
                    "description": f"No Tier-1 competitor provides strong {slug} support.",
                    "source": "competitor_blindspot",
                    "pain_intensity": 0.6,
                    "user_count": 0.5,
                    "max_competitor_coverage": max_cov,
                    "feasibility_coefficient": 0.7,
                    "timing_coefficient": 0.65,
                }
                await _upsert_opportunity(product_id, opp, db)
                score = _compute_score(opp)
                results["opportunities_scored"] += 1
                if score > results["top_score"]:
                    results["top_score"] = score
                    results["top_slug"] = slug

    results["top_score"] = round(results["top_score"], 4)
    logger.info(
        "whitespace_engine: %s — %d opportunities, top=%s (%.3f)",
        product_id,
        results["opportunities_scored"],
        results["top_slug"],
        results["top_score"],
    )
    return results
