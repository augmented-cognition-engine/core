"""TokenLedger — persists per-task token usage to SurrealDB.

Written on every task completion (not just reasoning loop tasks) so
historical cost data accumulates from day one. Used by ComplexityRouter
for self-calibration and by the /token-intelligence API for the portal.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


class TokenLedger:
    """Writes and queries token usage records in SurrealDB."""

    async def record(
        self,
        task_id: str,
        discipline: str,
        task_type: str,
        tier: str,
        executor_model: str,
        reviewer_model: str | None,
        passes: int,
        escalated: bool,
        cost_usd: float,
        tokens_by_stage: dict,
        cache_hit_rate: float,
        failure_categories: list[str],
        product_id: str = "product:platform",
        source: str = "executor",
        billing: str | None = None,
    ) -> None:
        """Write a ledger entry. Non-fatal — never raises.

        `source` labels the writer/granularity: "executor" (task-level, from the
        token accumulator) or "cli_provider" (per-call, from CLIProvider). `billing`
        records the cost semantics, e.g. "subscription_credit_estimate" for
        CLI/subscription calls where cost_usd is an API-rate-equivalent draw
        estimate, not a metered charge. Both are SCHEMALESS extras.
        """
        try:
            async with pool.connection() as db:
                await db.query(
                    """
                    CREATE token_ledger_entry SET
                        task_id = $task_id,
                        product = <record>$product,
                        discipline = $discipline,
                        task_type = $task_type,
                        tier = $tier,
                        executor_model = $executor_model,
                        reviewer_model = $reviewer_model,
                        passes = $passes,
                        escalated = $escalated,
                        cost_usd = $cost_usd,
                        tokens_by_stage = $tokens_by_stage,
                        cache_hit_rate = $cache_hit_rate,
                        failure_categories = $failure_categories,
                        source = $source,
                        billing = $billing,
                        resolved_at = time::now()
                    """,
                    {
                        "task_id": task_id,
                        "product": product_id,
                        "discipline": discipline,
                        "task_type": task_type,
                        "tier": tier,
                        "executor_model": executor_model,
                        "reviewer_model": reviewer_model,
                        "passes": passes,
                        "escalated": escalated,
                        "cost_usd": cost_usd,
                        "tokens_by_stage": tokens_by_stage,
                        "cache_hit_rate": cache_hit_rate,
                        "failure_categories": failure_categories,
                        "source": source,
                        "billing": billing,
                    },
                )
        except Exception:
            logger.exception("TokenLedger.record failed (non-fatal)")

    async def get_summary(self, product_id: str, days: int = 30) -> dict:
        """Return aggregate stats for the last N days.

        Scoped to task-level executor rows: the ledger also carries per-call
        provider rows (source="cli_provider"/"openai_compat") that describe
        the SAME underlying spend the executor accumulator summarizes — mixing
        them double-counts cost and inflates total_tasks with raw LLM calls.
        The NONE/IS NULL hedge keeps legacy rows written before the
        source field existed (consolidator.py idiom).
        """
        try:
            async with pool.connection() as db:
                rows = await db.query(
                    """
                    SELECT
                        math::mean(cost_usd) AS avg_cost_usd,
                        math::mean(passes) AS avg_passes,
                        math::mean(cache_hit_rate) AS avg_cache_hit_rate,
                        count() AS total_tasks,
                        count(escalated = true) AS escalated_count
                    FROM token_ledger_entry
                    WHERE product = <record>$product
                      AND (source = NONE OR source IS NULL OR source = 'executor')
                      AND resolved_at > time::now() - duration::from::days($days)
                    GROUP ALL
                    """,
                    {"product": product_id, "days": days},
                )
            parsed = parse_rows(rows)
            if not parsed:
                return self._empty_summary()
            row = parsed[0]
            total = row.get("total_tasks") or 0
            escalated = row.get("escalated_count") or 0
            return {
                "avg_cost_usd": round(row.get("avg_cost_usd") or 0.0, 6),
                "avg_passes": round(row.get("avg_passes") or 0.0, 2),
                "avg_cache_hit_rate": round(row.get("avg_cache_hit_rate") or 0.0, 3),
                "total_tasks": total,
                "escalation_rate": round(escalated / total, 3) if total > 0 else 0.0,
            }
        except Exception:
            logger.exception("TokenLedger.get_summary failed")
            return self._empty_summary()

    async def get_passes_by_discipline(self, product_id: str, days: int = 30) -> list[dict]:
        """Return pass distribution histogram per discipline.

        Executor rows only: provider-level rows carry discipline="" and
        passes=1 — mixing them adds a meaningless empty-discipline bucket and
        drags every average toward 1. Legacy pre-source rows (source = NONE)
        are executor-written and stay in.
        """
        try:
            async with pool.connection() as db:
                rows = await db.query(
                    """
                    SELECT discipline,
                           math::mean(passes) AS avg_passes,
                           count() AS total,
                           count(escalated = true) AS escalated
                    FROM token_ledger_entry
                    WHERE product = <record>$product
                      AND (source = NONE OR source IS NULL OR source = 'executor')
                      AND resolved_at > time::now() - duration::from::days($days)
                    GROUP BY discipline
                    """,
                    {"product": product_id, "days": days},
                )
            return parse_rows(rows)
        except Exception:
            logger.exception("TokenLedger.get_passes_by_discipline failed")
            return []

    async def get_failure_categories(self, product_id: str, days: int = 30) -> list[dict]:
        """Return failure category frequency counts.

        No source filter needed: provider-level rows always write
        failure_categories=[] and the array::len > 0 predicate already
        excludes them structurally — mixing cannot corrupt this metric.
        """
        try:
            async with pool.connection() as db:
                rows = await db.query(
                    """
                    SELECT failure_categories
                    FROM token_ledger_entry
                    WHERE product = <record>$product
                      AND resolved_at > time::now() - duration::from::days($days)
                      AND array::len(failure_categories) > 0
                    """,
                    {"product": product_id, "days": days},
                )
            parsed = parse_rows(rows)
            counts: dict[str, int] = {}
            for row in parsed:
                for cat in row.get("failure_categories") or []:
                    counts[cat] = counts.get(cat, 0) + 1
            return [{"category": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
        except Exception:
            logger.exception("TokenLedger.get_failure_categories failed")
            return []

    async def get_weekly_trend(self, product_id: str, weeks: int = 12) -> list[dict]:
        """Return weekly avg_passes trend for the flywheel chart.

        Executor rows only — same double-count/passes-skew reasoning as
        get_summary: per-call provider rows would flatten avg_passes to ~1
        and count raw LLM calls as tasks.
        """
        try:
            async with pool.connection() as db:
                rows = await db.query(
                    """
                    SELECT
                        time::floor(resolved_at, 1w) AS week,
                        math::mean(passes) AS avg_passes,
                        math::mean(cost_usd) AS avg_cost_usd,
                        count() AS total_tasks
                    FROM token_ledger_entry
                    WHERE product = <record>$product
                      AND (source = NONE OR source IS NULL OR source = 'executor')
                      AND resolved_at > time::now() - duration::from::weeks($weeks)
                    GROUP BY week
                    ORDER BY week ASC
                    """,
                    {"product": product_id, "weeks": weeks},
                )
            return parse_rows(rows)
        except Exception:
            logger.exception("TokenLedger.get_weekly_trend failed")
            return []

    @staticmethod
    def _empty_summary() -> dict:
        return {
            "avg_cost_usd": 0.0,
            "avg_passes": 0.0,
            "avg_cache_hit_rate": 0.0,
            "total_tasks": 0,
            "escalation_rate": 0.0,
        }
