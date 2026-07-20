# engine/sentinel/engines/simplicity_audit.py
"""Simplicity audit sentinel engine — detect dormant/unjustified architectural complexity.

Runs weekly (Sunday 6 AM, after calibration at 5 AM). Analyzes:
1. Dormancy: which patterns, perspectives, engines, archetypes are registered but unused
2. Complexity justification: do active layers improve outcomes vs simpler alternatives
3. Recommendations: synthesize findings into actionable simplification proposals

Inspired by Anthropic's harness design article: "the space of interesting harness
combinations doesn't shrink as models improve. Instead, it moves."
"""

from __future__ import annotations

import logging
from collections import defaultdict

from core.engine.core.config import settings
from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import get_llm
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

# Known registered components (these are the architectural dimensions)
KNOWN_PATTERNS = ["independent", "pipeline", "adversarial", "fanout", "team"]
KNOWN_PERSPECTIVES = ["theorist", "practitioner", "strategist", "operator"]
KNOWN_ARCHETYPES = ["creator", "analyst", "executor", "researcher", "advisor", "sentinel"]
KNOWN_MODES = ["deliberative", "reactive", "exploratory", "conversational", "procedural", "reflective"]

_MIN_TASKS_FOR_AUDIT = 50  # skip if too little data


def _validate_simplicity_audit_inputs(product_id: str, budget: int = 100) -> None:
    """Validate simplicity audit inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for simplicity-audit: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="simplicity_audit",
    cron="0 6 * * sun",
    description="Weekly complexity audit — detect dormant patterns and unjustified layers",
)
async def run_simplicity_audit(product_id: str, budget: int = 10) -> dict:
    """Analyze system complexity and recommend simplifications.

    Three passes:
    1. Dormancy detection (pure SQL)
    2. Complexity justification (pure SQL)
    3. Recommendation synthesis (1 LLM call)

    Returns:
        Dict with dormant_count, low_value_count, justified_count,
        complexity_score, recommendations.
    """
    _validate_simplicity_audit_inputs(product_id, budget)
    async with pool.connection() as db:
        # Bootstrap guard: skip if insufficient data
        total_result = await db.query(
            """SELECT count() as cnt FROM orchestration_run
               WHERE product = <record>$product AND created_at > time::now() - 90d
               GROUP ALL""",
            {"product": product_id},
        )
        total_rows = parse_rows(total_result)
        total_runs = total_rows[0].get("cnt", 0) if total_rows else 0

        if total_runs < _MIN_TASKS_FOR_AUDIT:
            return {
                "skipped": True,
                "reason": f"Insufficient data ({total_runs} runs, need {_MIN_TASKS_FOR_AUDIT})",
                "dormant_count": 0,
                "low_value_count": 0,
                "justified_count": 0,
                "complexity_score": 0.0,
                "recommendations": [],
            }

        # ── Pass 1: Dormancy detection ───────────────────────
        dormant = []

        # Patterns: which orchestration patterns have 0 runs in 90 days
        pattern_result = await db.query(
            """SELECT pattern, count() as cnt
               FROM orchestration_run
               WHERE product = <record>$product AND created_at > time::now() - 90d
               GROUP BY pattern""",
            {"product": product_id},
        )
        used_patterns = {r["pattern"]: r["cnt"] for r in parse_rows(pattern_result)}
        for p in KNOWN_PATTERNS:
            if p not in used_patterns:
                dormant.append({"component": p, "category": "pattern", "usage": 0})

        # Perspectives: count from composition_signal
        perspective_result = await db.query(
            """SELECT perspectives
               FROM composition_signal
               WHERE product = <record>$product AND created_at > time::now() - 90d
               LIMIT 500""",
            {"product": product_id},
        )
        perspective_counts = defaultdict(int)
        total_perspective_usage = 0
        for row in parse_rows(perspective_result):
            for p in row.get("perspectives", []):
                perspective_counts[p] += 1
                total_perspective_usage += 1

        if total_perspective_usage > 0:
            for p in KNOWN_PERSPECTIVES:
                share = perspective_counts.get(p, 0) / total_perspective_usage
                if share < 0.05:  # <5% usage
                    dormant.append(
                        {
                            "component": p,
                            "category": "perspective",
                            "usage": perspective_counts.get(p, 0),
                            "share": round(share, 3),
                        }
                    )

        # Sentinel engines: check engine_run for 0 completed runs
        engine_result = await db.query(
            """SELECT engine, count() as cnt
               FROM engine_run
               WHERE product = <record>$product
                 AND status = 'completed'
                 AND created_at > time::now() - 90d
               GROUP BY engine""",
            {"product": product_id},
        )
        used_engines = {r["engine"]: r["cnt"] for r in parse_rows(engine_result)}

        try:
            from core.engine.sentinel.registry import list_engines

            registered = list_engines()
            for e in registered:
                name = e.get("name", "")
                if name and name not in used_engines:
                    dormant.append({"component": name, "category": "engine", "usage": 0})
        except Exception:
            pass  # registry not available — skip engine check

        # Archetypes: count from composition_signal
        archetype_result = await db.query(
            """SELECT archetype, count() as cnt
               FROM composition_signal
               WHERE product = <record>$product AND created_at > time::now() - 90d
               GROUP BY archetype""",
            {"product": product_id},
        )
        archetype_counts = {r["archetype"]: r["cnt"] for r in parse_rows(archetype_result)}
        total_archetype = sum(archetype_counts.values()) or 1
        for a in KNOWN_ARCHETYPES:
            share = archetype_counts.get(a, 0) / total_archetype
            if share < 0.02:  # <2% usage
                dormant.append(
                    {
                        "component": a,
                        "category": "archetype",
                        "usage": archetype_counts.get(a, 0),
                        "share": round(share, 3),
                    }
                )

        # ── Pass 2: Complexity justification ─────────────────
        low_value = []
        justified = []

        # For each active perspective: acceptance rate WITH vs WITHOUT
        for p in KNOWN_PERSPECTIVES:
            if perspective_counts.get(p, 0) == 0:
                continue  # already dormant

            with_result = await db.query(
                """SELECT count() as total,
                          math::sum(IF feedback = 'accepted' THEN 1 ELSE 0 END) as accepted
                   FROM composition_signal
                   WHERE product = <record>$product
                     AND created_at > time::now() - 90d
                     AND perspectives CONTAINS $perspective
                   GROUP ALL""",
                {"product": product_id, "perspective": p},
            )
            with_rows = parse_rows(with_result)
            with_total = with_rows[0].get("total", 0) if with_rows else 0
            with_accepted = with_rows[0].get("accepted", 0) if with_rows else 0

            without_result = await db.query(
                """SELECT count() as total,
                          math::sum(IF feedback = 'accepted' THEN 1 ELSE 0 END) as accepted
                   FROM composition_signal
                   WHERE product = <record>$product
                     AND created_at > time::now() - 90d
                     AND perspectives CONTAINSNOT $perspective
                   GROUP ALL""",
                {"product": product_id, "perspective": p},
            )
            without_rows = parse_rows(without_result)
            without_total = without_rows[0].get("total", 0) if without_rows else 0
            without_accepted = without_rows[0].get("accepted", 0) if without_rows else 0

            with_rate = with_accepted / with_total if with_total > 0 else 0
            without_rate = without_accepted / without_total if without_total > 0 else 0

            if with_rate < without_rate and with_total >= 5:
                low_value.append(
                    {
                        "component": p,
                        "category": "perspective",
                        "with_rate": round(with_rate, 3),
                        "without_rate": round(without_rate, 3),
                        "delta": round(with_rate - without_rate, 3),
                    }
                )
            elif with_total >= 5:
                justified.append(
                    {
                        "component": p,
                        "category": "perspective",
                        "with_rate": round(with_rate, 3),
                        "without_rate": round(without_rate, 3),
                    }
                )

        # For each active pattern: success rate comparison
        for p_name, p_count in used_patterns.items():
            if p_count < 3:
                continue

            p_result = await db.query(
                """SELECT count() as total,
                          math::sum(IF status = 'completed' THEN 1 ELSE 0 END) as successes
                   FROM orchestration_run
                   WHERE product = <record>$product
                     AND pattern = $pattern
                     AND created_at > time::now() - 90d
                   GROUP ALL""",
                {"product": product_id, "pattern": p_name},
            )
            p_rows = parse_rows(p_result)
            p_total = p_rows[0].get("total", 0) if p_rows else 0
            p_successes = p_rows[0].get("successes", 0) if p_rows else 0
            success_rate = p_successes / p_total if p_total > 0 else 0

            if success_rate < 0.5:
                low_value.append(
                    {
                        "component": p_name,
                        "category": "pattern",
                        "success_rate": round(success_rate, 3),
                        "runs": p_count,
                    }
                )
            else:
                justified.append(
                    {
                        "component": p_name,
                        "category": "pattern",
                        "success_rate": round(success_rate, 3),
                        "runs": p_count,
                    }
                )

        # ── Pass 3: Recommendations (1 LLM call) ────────────
        recommendations = []
        total_components = len(KNOWN_PATTERNS) + len(KNOWN_PERSPECTIVES) + len(KNOWN_ARCHETYPES)
        justified_count = len(justified)
        complexity_score = (total_components - justified_count) / total_components if total_components else 0

        if dormant or low_value:
            try:
                llm = get_llm()
                prompt = f"""You are auditing an AI orchestration system for unnecessary complexity.

DORMANT COMPONENTS (registered but unused in 90 days):
{dormant[:15]}

LOW-VALUE COMPONENTS (active but underperforming alternatives):
{low_value[:10]}

JUSTIFIED COMPONENTS (active with measurable value):
{justified[:10]}

COMPLEXITY SCORE: {complexity_score:.2f} (0=simple, 1=fully unjustified)

Generate 1-3 actionable simplification recommendations.
Each recommendation should be specific and include the expected impact.

Return JSON: [{{"component": "name", "action": "remove|deprecate|merge|monitor",
                "reason": "why", "impact": "expected benefit"}}]"""

                recs = await llm.complete_json(prompt, model=settings.llm_budget_model)
                if isinstance(recs, list):
                    recommendations = recs[:3]
                elif isinstance(recs, dict):
                    recommendations = [recs]
            except Exception as exc:
                logger.warning("Simplicity audit recommendation generation failed: %s", exc)

        # ── Persist results ──────────────────────────────────
        try:
            await db.query(
                """CREATE simplicity_audit SET
                    dormant_components = $dormant,
                    low_value_components = $low_value,
                    justified_components = $justified,
                    recommendations = $recs,
                    complexity_score = $score""",
                {
                    "product": product_id,
                    "dormant": dormant,
                    "low_value": low_value,
                    "justified": justified,
                    "recs": recommendations,
                    "score": complexity_score,
                },
            )
        except Exception as exc:
            logger.warning("Failed to persist simplicity audit: %s", exc)

    return {
        "dormant_count": len(dormant),
        "low_value_count": len(low_value),
        "justified_count": justified_count,
        "complexity_score": round(complexity_score, 3),
        "recommendations": recommendations,
        "dormant": dormant,
        "low_value": low_value,
    }
