"""Sentinel engine: Domain Research Agent — the 4-stage experimentation loop.

THE CORE DIFFERENTIATOR. Runs nightly at 5 AM.
1. Research: find relevant external findings scoped to org's actual tools
2. Synthesize: generate realistic tasks using org's vocabulary
3. Experiment: A/B test current vs proposed intelligence (Welch's t-test)
4. Commit: winners to graph, losers to log

After 6 months: 180 runs/domain, 3,600 evaluations/domain.
The accumulated experimental evidence is irreproducible.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.intelligence.statistics import is_significant, welch_t_test
from core.engine.intelligence.synthetic_runner import run_synthetic_task, score_output
from core.engine.sentinel.engines import write_engine_insight
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

MIN_TASKS_FOR_DOMAIN = 10
SYNTHETIC_TASK_COUNT = 20
SIGNIFICANCE_THRESHOLD = 0.05
MIN_EFFECT_SIZE = 0.02


def _validate_research_inputs(product_id: str) -> None:
    """Validate domain research inputs before querying specialties.

    Raises ValidationError for malformed product_id so the nightly research
    loop fails fast with a clear error rather than running through all stages
    against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for domain research: {product_id!r}")


SEARCH_QUERY_PROMPT = """Given these high-confidence insights for the domain "{domain}":
{insights}

Generate 3-5 web search queries to find updates, corrections, or improvements
to this intelligence. Focus on what this specific organization uses.

Return JSON array of strings: ["query1", "query2", ...]"""

SYNTHESIZE_PROMPT = """Based on these real tasks from domain "{domain}":
{real_tasks}

Generate {count} realistic synthetic tasks that match this organization's vocabulary,
tools, and conventions. Each task should have complexity similar to real ones.

Return JSON array: [{{"description": "...", "expected_quality_signals": ["signal1", "signal2"], "discipline": "{domain}", "complexity": "simple|moderate|complex"}}]"""

VARIANT_PROMPT = """Given this research finding:
"{finding}"

And these existing insights in domain "{domain}":
{existing_insights}

Propose an intelligence variant — a new or updated insight that incorporates
this finding. Be specific and actionable.

Return JSON: {{"content": "the proposed insight text", "insight_type": "fact|pattern|convention|correction", "confidence": 0.0-1.0}}"""


# ── Stage 1: Research ──────────────────────────────────────────────


async def research_domain(domain: str, product_id: str, db, llm_client) -> list[dict]:
    """Find relevant external findings for a domain."""
    from core.engine.core.search import web_search

    # Get existing high-confidence insights
    result = await db.query(
        """
        SELECT content, insight_type, confidence FROM insight
        WHERE product = <record>$product AND tags CONTAINS $discipline AND status = 'active' AND confidence > 0.7
        ORDER BY confidence DESC LIMIT 15
        """,
        {"product": product_id, "discipline": domain},
    )
    rows = result[0] if result and isinstance(result[0], list) else (result or [])
    insight_text = "\n".join(f"- [{r.get('insight_type', '?')}] {r.get('content', '')[:100]}" for r in rows[:10])

    if not insight_text:
        return []

    # Generate search queries
    try:
        queries = await llm_client.complete_json(
            SEARCH_QUERY_PROMPT.format(domain=domain, insights=insight_text),
            model=settings.llm_budget_model,
        )
        if not isinstance(queries, list):
            queries = []
    except Exception as exc:
        logger.warning("Search query generation failed: %s", exc)
        return []

    # Execute searches
    findings = []
    for query in queries[:5]:
        try:
            results = await web_search(str(query), max_results=3)
            for r in results:
                if r.get("relevance_score", 0) >= 0.5:
                    findings.append(
                        {
                            "query": str(query),
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": r.get("snippet", ""),
                        }
                    )
        except Exception:
            pass

    return findings[:10]


# ── Stage 2: Synthesize ───────────────────────────────────────────


async def synthesize_test_tasks(domain: str, product_id: str, count: int, db, llm_client) -> list[dict]:
    """Generate synthetic tasks from org's real task history."""
    result = await db.query(
        """
        SELECT description, created_at FROM task
        WHERE product = <record>$product AND discipline = $discipline AND status = 'completed'
        ORDER BY created_at DESC LIMIT 50
        """,
        {"product": product_id, "discipline": domain},
    )
    rows = result[0] if result and isinstance(result[0], list) else (result or [])
    real_tasks = "\n".join(f"- {r.get('description', '')[:100]}" for r in rows[:20])

    if not real_tasks:
        return []

    try:
        tasks = await llm_client.complete_json(
            SYNTHESIZE_PROMPT.format(domain=domain, real_tasks=real_tasks, count=count),
            model=settings.llm_budget_model,
        )
        if not isinstance(tasks, list):
            return []
        return tasks[:count]
    except Exception as exc:
        logger.warning("Synthetic task generation failed: %s", exc)
        return []


# ── Stage 3: Experiment ───────────────────────────────────────────


async def run_experiment(
    domain: str,
    product_id: str,
    findings: list[dict],
    synthetic_tasks: list[dict],
    db,
    llm_client,
) -> list[dict]:
    """A/B test intelligence variants against current intelligence."""
    if not synthetic_tasks or not findings:
        return []

    # Load current intelligence as control context
    result = await db.query(
        """
        SELECT content, insight_type, confidence FROM insight
        WHERE product = <record>$product AND tags CONTAINS $discipline AND status = 'active'
        ORDER BY confidence DESC LIMIT 20
        """,
        {"product": product_id, "discipline": domain},
    )
    rows = result[0] if result and isinstance(result[0], list) else (result or [])
    control_context = (
        "\n".join(
            "## Intelligence\n" + "\n".join(f"- [{r.get('insight_type', '')}] {r.get('content', '')}" for r in rows)
        )
        if rows
        else "No existing intelligence."
    )

    experiments = []

    for finding in findings[:5]:  # Limit experiments per run
        # Generate variant
        try:
            variant = await llm_client.complete_json(
                VARIANT_PROMPT.format(
                    finding=finding.get("snippet", "")[:300],
                    domain=domain,
                    existing_insights=control_context[:1000],
                ),
                model=settings.llm_budget_model,
            )
            if not isinstance(variant, dict) or not variant.get("content"):
                continue
        except Exception:
            continue

        variant_context = control_context + f"\n- [proposed] {variant['content']}"

        # Run all synthetic tasks with control and variant
        control_scores = []
        variant_scores = []
        control_tokens = []
        variant_tokens = []

        for task in synthetic_tasks[:SYNTHETIC_TASK_COUNT]:
            desc = task.get("description", "")
            signals = task.get("expected_quality_signals", [])
            if not desc:
                continue

            try:
                control_output, c_tokens = await run_synthetic_task(desc, control_context, domain, llm_client)
                variant_output, v_tokens = await run_synthetic_task(desc, variant_context, domain, llm_client)

                c_score = await score_output(desc, control_output, signals, llm_client)
                v_score = await score_output(desc, variant_output, signals, llm_client)

                control_scores.append(c_score)
                variant_scores.append(v_score)
                control_tokens.append(c_tokens)
                variant_tokens.append(v_tokens)
            except Exception as exc:
                logger.warning("Synthetic task execution failed: %s", exc)

        if len(control_scores) < 5 or len(variant_scores) < 5:
            continue

        # Statistical test
        t_stat, p_value = welch_t_test(control_scores, variant_scores)
        control_mean = sum(control_scores) / len(control_scores)
        variant_mean = sum(variant_scores) / len(variant_scores)
        improvement = variant_mean - control_mean
        significant = is_significant(control_scores, variant_scores, SIGNIFICANCE_THRESHOLD, MIN_EFFECT_SIZE)

        experiments.append(
            {
                "finding": finding,
                "variant": variant,
                "control_mean": round(control_mean, 4),
                "variant_mean": round(variant_mean, 4),
                "improvement": round(improvement, 4),
                "p_value": p_value,
                "significant": significant,
                "synthetic_task_count": len(control_scores),
            }
        )

        # Update token baseline with per-experiment data
        if control_tokens and variant_tokens:
            try:
                from core.engine.intelligence.token_baseline import update_baseline

                avg_control = sum(control_tokens) / len(control_tokens)
                avg_variant = sum(variant_tokens) / len(variant_tokens)
                await update_baseline(domain, "moderate", product_id, int(avg_control), int(avg_variant))
            except Exception as exc:
                logger.warning("Failed to update token baseline: %s", exc)

    return experiments


# ── Stage 4: Commit ───────────────────────────────────────────────


async def commit_results(
    domain: str,
    product_id: str,
    experiments: list[dict],
    db,
) -> dict:
    """Commit winning variants to intelligence graph. Log all results."""
    winners = 0
    losers = 0
    inconclusive = 0

    for exp in experiments:
        variant = exp.get("variant", {})
        finding = exp.get("finding", {})
        significant = exp.get("significant", False)
        improvement = exp.get("improvement", 0)

        # Log to experiment_log (ALL results)
        try:
            await db.query(
                """
                CREATE experiment_log SET
                    domain = $domain,
                    experiment_type = 'intelligence_variant',
                    control_description = $control_desc,
                    variant_description = $variant_desc,
                    synthetic_task_count = $task_count,
                    control_mean = $control_mean,
                    variant_mean = $variant_mean,
                    improvement = $improvement,
                    p_value = $p_value,
                    significant = $significant,
                    committed = $committed,
                    details = $details,
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "domain": domain,
                    "control_desc": f"Current intelligence for {domain}",
                    "variant_desc": variant.get("content", "")[:500],
                    "task_count": exp.get("synthetic_task_count", 0),
                    "control_mean": exp.get("control_mean", 0),
                    "variant_mean": exp.get("variant_mean", 0),
                    "improvement": improvement,
                    "p_value": exp.get("p_value", 1.0),
                    "significant": significant,
                    "committed": significant and improvement > 0,
                    "details": {
                        "finding_url": finding.get("url", ""),
                        "finding_snippet": finding.get("snippet", "")[:200],
                        "variant_type": variant.get("insight_type", ""),
                        "variant_confidence": variant.get("confidence", 0),
                    },
                },
            )
        except Exception as exc:
            logger.warning("Failed to log experiment: %s", exc)

        # Commit winners to intelligence graph
        if significant and improvement > 0:
            try:
                await write_engine_insight(
                    db,
                    product_id=product_id,
                    content=variant.get("content", ""),
                    insight_type=variant.get("insight_type", "fact"),
                    tier="subdomain",
                    discipline=domain,
                    source_domain="sentinel.domain_research",
                    confidence=min(0.85, variant.get("confidence", 0.7)),
                    tags=["experiment", "domain-research", f"improvement:{improvement:.3f}"],
                )
                winners += 1
            except Exception as exc:
                logger.warning("Failed to commit experiment winner: %s", exc)
        elif significant and improvement <= 0:
            losers += 1
        else:
            inconclusive += 1

    return {"winners": winners, "losers": losers, "inconclusive": inconclusive}


# ── Specialty Eligibility ─────────────────────────────────────────


async def _get_eligible_specialties(product_id: str, db) -> dict[str, list[dict]]:
    """Get specialties grouped by discipline with sufficient task history.

    Two-step: task counts from specialties_loaded arrays, then resolve to specialty records.
    """
    # Step 1: Task counts from specialties_loaded arrays
    task_result = await db.query(
        """
        SELECT specialties_loaded, count() as task_count
        FROM task
        WHERE product = <record>$product AND created_at > time::now() - 90d
          AND specialties_loaded IS NOT NONE
        GROUP BY specialties_loaded
        """,
        {"product": product_id},
    )
    rows = task_result[0] if task_result and isinstance(task_result[0], list) else (task_result or [])

    # Flatten per-slug counts
    slug_counts: dict[str, int] = {}
    for row in rows:
        for slug in row.get("specialties_loaded") or []:
            slug_counts[slug] = slug_counts.get(slug, 0) + row.get("task_count", 0)

    eligible_slugs = [s for s, c in slug_counts.items() if c >= MIN_TASKS_FOR_DOMAIN]
    if not eligible_slugs:
        return {}

    # Step 2: Resolve to specialty records grouped by discipline
    spec_result = await db.query(
        """
        SELECT *, discipline.slug as discipline_slug
        FROM specialty
        WHERE slug IN $slugs AND product = <record>$product AND status = 'active'
        """,
        {"slugs": eligible_slugs, "product": product_id},
    )
    spec_rows = spec_result[0] if spec_result and isinstance(spec_result[0], list) else (spec_result or [])

    grouped: dict[str, list[dict]] = {}
    for spec in spec_rows:
        disc = spec.get("discipline_slug") or "uncategorized"
        grouped.setdefault(disc, []).append(spec)

    return grouped


# ── Stage 5: Cross-Pollination ────────────────────────────────────


def _is_similar(a: str, b: str, threshold: float = 0.8) -> bool:
    """Check if two strings are similar enough to be considered duplicates."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


_AFFINITY_THRESHOLD = 0.6


async def _get_affinity_targets(specialty_slug: str, product_id: str, db) -> list[str]:
    """Find cross-discipline specialties with strong learned affinities."""
    result = await db.query(
        """
        SELECT specialty_a.slug as slug_a, specialty_b.slug as slug_b, strength
        FROM specialty_affinity
        WHERE product = <record>$product
          AND (specialty_a.slug = $slug OR specialty_b.slug = $slug)
          AND strength >= $threshold
        """,
        {"product": product_id, "slug": specialty_slug, "threshold": _AFFINITY_THRESHOLD},
    )
    rows = result[0] if result and isinstance(result[0], list) else (result or [])

    targets = []
    for row in rows:
        slug_a = row.get("slug_a", "")
        slug_b = row.get("slug_b", "")
        strength = row.get("strength", 0.0)
        if strength < _AFFINITY_THRESHOLD:
            continue
        target = slug_b if slug_a == specialty_slug else slug_a
        if target and target != specialty_slug:
            targets.append(target)

    return targets


async def cross_pollinate(
    discipline: str,
    winners: list[dict],
    product_id: str,
    db,
    llm_client,
) -> dict:
    """Stage 5: Test winning insights in sibling specialties."""
    if not winners:
        return {"attempted": 0, "winners": 0, "already_present": 0, "by_specialty": []}

    attempted = 0
    won = 0
    already_present = 0
    by_specialty = []

    for winner in winners:
        origin_slug = winner["specialty_slug"]
        variant = winner["variant"]
        variant_content = variant.get("content", "")

        # Find sibling specialties in same discipline
        sibling_result = await db.query(
            """
            SELECT slug, id FROM specialty
            WHERE discipline.slug = $discipline
              AND product = <record>$product
              AND slug != $origin
              AND status = 'active'
            """,
            {"discipline": discipline, "product": product_id, "origin": origin_slug},
        )
        siblings = (
            sibling_result[0] if sibling_result and isinstance(sibling_result[0], list) else (sibling_result or [])
        )

        for sibling in siblings:
            sibling_slug = sibling.get("slug", "")
            if not sibling_slug:
                continue

            # Dedup check — look for similar existing insights
            existing_result = await db.query(
                """
                SELECT content, confidence FROM insight
                WHERE product = <record>$product AND tags CONTAINS $discipline AND status = 'active'
                ORDER BY confidence DESC LIMIT 50
                """,
                {"product": product_id, "discipline": sibling_slug},
            )
            existing_rows = (
                existing_result[0]
                if existing_result and isinstance(existing_result[0], list)
                else (existing_result or [])
            )

            if any(_is_similar(variant_content, row.get("content", "")) for row in existing_rows):
                already_present += 1
                logger.info(
                    "Cross-pollination skipped %s->%s: similar insight exists",
                    origin_slug,
                    sibling_slug,
                )
                continue

            attempted += 1

            try:
                synthetic_tasks = winner.get("synthetic_tasks") or await synthesize_test_tasks(
                    sibling_slug,
                    product_id,
                    SYNTHETIC_TASK_COUNT,
                    db,
                    llm_client,
                )
                if not synthetic_tasks:
                    continue

                experiments = await run_experiment(
                    sibling_slug,
                    product_id,
                    [{"snippet": variant_content}],
                    synthetic_tasks,
                    db,
                    llm_client,
                )
                results = await commit_results(sibling_slug, product_id, experiments, db)

                if results["winners"] > 0:
                    won += 1
                    by_specialty.append(
                        {
                            "origin": origin_slug,
                            "target": sibling_slug,
                            "improvement": winner["improvement"],
                        }
                    )

                # Log cross-pollination attempt
                await db.query(
                    """
                    CREATE experiment_log SET
                        domain = $target,
                        experiment_type = 'cross_pollination',
                        control_description = $control_desc,
                        variant_description = $variant_desc,
                        significant = $significant,
                        committed = $committed,
                        details = $details,
                        created_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "target": sibling_slug,
                        "control_desc": f"Current intelligence for {sibling_slug}",
                        "variant_desc": variant_content[:500],
                        "significant": results["winners"] > 0,
                        "committed": results["winners"] > 0,
                        "details": {
                            "origin_specialty": origin_slug,
                            "target_specialty": sibling_slug,
                            "discipline": discipline,
                        },
                    },
                )

            except Exception as exc:
                logger.warning(
                    "Cross-pollination test failed %s->%s: %s",
                    origin_slug,
                    sibling_slug,
                    exc,
                )

    # Bonus: cross-discipline propagation via specialty affinities
    for winner in winners:
        try:
            affinity_targets = await _get_affinity_targets(winner["specialty_slug"], product_id, db)
            for target_slug in affinity_targets:
                attempted += 1
                try:
                    synthetic_tasks = await synthesize_test_tasks(
                        target_slug,
                        product_id,
                        SYNTHETIC_TASK_COUNT,
                        db,
                        llm_client,
                    )
                    if not synthetic_tasks:
                        continue
                    experiments = await run_experiment(
                        target_slug,
                        product_id,
                        [{"snippet": winner["variant"].get("content", "")}],
                        synthetic_tasks,
                        db,
                        llm_client,
                    )
                    results = await commit_results(target_slug, product_id, experiments, db)
                    if results["winners"] > 0:
                        won += 1
                        by_specialty.append(
                            {
                                "origin": winner["specialty_slug"],
                                "target": target_slug,
                                "improvement": winner["improvement"],
                                "via_affinity": True,
                            }
                        )
                except Exception as exc:
                    logger.warning(
                        "Affinity cross-pollination failed %s->%s: %s",
                        winner["specialty_slug"],
                        target_slug,
                        exc,
                    )
        except Exception as exc:
            logger.warning(
                "Affinity target lookup failed for %s: %s",
                winner["specialty_slug"],
                exc,
            )

    return {
        "attempted": attempted,
        "winners": won,
        "already_present": already_present,
        "by_specialty": by_specialty,
    }


# ── Full Loop ─────────────────────────────────────────────────────


@register_engine(
    name="domain_research",
    cron="0 5 * * *",
    description="Nightly domain research — research, synthesize, experiment, commit (5am)",
)
async def run_domain_research(product_id: str) -> dict:
    """Run the 4-stage experimentation loop for active specialties, grouped by discipline."""
    _validate_research_inputs(product_id)
    total_findings = 0
    total_experiments = 0
    total_winners = 0
    total_losers = 0
    specialties_processed = 0
    cross_pollination_stats = {"attempted": 0, "winners": 0}

    async with pool.connection() as db:
        grouped = await _get_eligible_specialties(product_id, db)

        if not grouped:
            return {"specialties_processed": 0, "reason": "no_eligible_specialties"}

        for discipline, specialties in grouped.items():
            discipline_winners = []

            for spec in specialties:
                slug = spec.get("slug", "")
                if not slug:
                    continue
                specialties_processed += 1

                try:
                    findings = await research_domain(slug, product_id, db, llm)
                    total_findings += len(findings)

                    if not findings:
                        logger.info("Specialty %s: no findings from research", slug)
                        continue

                    synthetic_tasks = await synthesize_test_tasks(slug, product_id, SYNTHETIC_TASK_COUNT, db, llm)
                    if not synthetic_tasks:
                        logger.info("Specialty %s: no synthetic tasks generated", slug)
                        continue

                    experiments = await run_experiment(slug, product_id, findings, synthetic_tasks, db, llm)
                    total_experiments += len(experiments)

                    results = await commit_results(slug, product_id, experiments, db)
                    total_winners += results["winners"]
                    total_losers += results["losers"]

                    # Collect winners for cross-pollination
                    for exp in experiments:
                        if exp.get("significant") and exp.get("improvement", 0) > 0:
                            discipline_winners.append(
                                {
                                    "specialty_slug": slug,
                                    "variant": exp["variant"],
                                    "improvement": exp["improvement"],
                                    "synthetic_tasks": synthetic_tasks,
                                }
                            )

                except Exception as exc:
                    logger.warning("Domain research failed for %s: %s", slug, exc)

            # Stage 5: Cross-pollinate winners within this discipline
            if discipline_winners:
                try:
                    cp_result = await cross_pollinate(
                        discipline,
                        discipline_winners,
                        product_id,
                        db,
                        llm,
                    )
                    cross_pollination_stats["attempted"] += cp_result.get("attempted", 0)
                    cross_pollination_stats["winners"] += cp_result.get("winners", 0)
                except Exception as exc:
                    logger.warning("Cross-pollination failed for discipline %s: %s", discipline, exc)

    logger.info(
        "Domain research: specialties=%d, findings=%d, experiments=%d, winners=%d, losers=%d, cross_pollinated=%d",
        specialties_processed,
        total_findings,
        total_experiments,
        total_winners,
        total_losers,
        cross_pollination_stats["winners"],
    )
    return {
        "specialties_processed": specialties_processed,
        "findings": total_findings,
        "experiments": total_experiments,
        "winners_committed": total_winners,
        "losers_logged": total_losers,
        "cross_pollination": cross_pollination_stats,
    }
