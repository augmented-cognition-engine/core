"""Contributions aggregator — read 3 source tables, build the 5-metric
dashboard payload (counts + sparklines + headline + journey deep-links).

Trailing 30-day window. Pure async function — no FastAPI coupling so the
same logic can be reused by an MCP tool, CLI, or cron job.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

from core.engine.core.db import parse_rows

_METRIC_KEYS = (
    "prs_reviewed",
    "gaps_caught",
    "you_shipped",
    "we_let_go",
    "effectiveness",
    "tasks_completed",
    "cost_saved_usd",
)


def _unwrap(result: Any) -> list[dict]:
    """Normalize a SurrealDB query response into a flat list of row dicts.

    SurrealDB clients vary by transport: the native v3 SDK returns rows
    directly (`[row1, row2, ...]`), but the HTTP/JSON wire format wraps
    them in `[{"result": [...], "status": "OK"}]`. Strip the envelope if
    present, then defer to parse_rows for RecordID coercion + edge cases.
    """
    if (
        isinstance(result, list)
        and len(result) == 1
        and isinstance(result[0], dict)
        and "status" in result[0]
        and "result" in result[0]
    ):
        return parse_rows(result[0]["result"])
    return parse_rows(result)


# Deep-links are mapped server-side so the journey URL shape can evolve
# without portal-side drift. All five card pairs are live in v1 — the
# outcome.* and effectiveness.score topics were registered in Task 1.
_DEEP_LINKS = {
    "prs_reviewed": "/journey?topics=review.completed&since=month",
    "gaps_caught": "/journey?topics=gap.detected,gap.closed&since=month",
    "you_shipped": "/journey?topics=outcome.committed&since=month",
    "we_let_go": "/journey?topics=outcome.ignored&since=month",
    "effectiveness": "/journey?topics=effectiveness.score.recomputed&since=month",
    "tasks_completed": "/settings/token-intelligence",
    "cost_saved_usd": "/settings/token-intelligence",
}

_HEADLINE_TEMPLATE = (
    "In the last 30 days we ran {tasks} {tasks_word} — noticed {gaps} {gaps_word}, "
    "you shipped {shipped} of them, and we saved ~${saved:.2f} through cache hits."
)


async def compute_contributions(pool: Any, product_id: str) -> dict[str, Any]:
    """Return the dashboard payload. Sub-query failures isolated per-metric.

    Schema-coupling notes (SurrealDB v3 traps avoided):
    - All ORDER BY columns appear in SELECT (the v3 parser rejects otherwise).
    - <record>$pid casts the bound product_id back to a record reference.
    """
    metrics: dict[str, dict[str, Any]] = {k: {"count": None, "sparkline": []} for k in _METRIC_KEYS}

    if pool is None:
        # CI / unit-test path — return zeros + empty sparklines
        for k in _METRIC_KEYS:
            metrics[k] = {"count": 0, "sparkline": [0] * 30}
        metrics["effectiveness"] = {"delta_pct": 0.0, "sparkline": [0.0] * 30}
        metrics["cost_saved_usd"] = {"amount_usd": 0.0, "sparkline": [0] * 30}
        return _build_response(metrics)

    async with pool.connection() as db:
        # PRs reviewed — pr_review table (schema v047)
        try:
            rows = _unwrap(
                await db.query(
                    "SELECT id, created_at FROM pr_review "
                    "WHERE product = <record>$pid AND created_at > time::now() - 30d "
                    "ORDER BY created_at ASC",
                    {"pid": product_id},
                )
            )
            metrics["prs_reviewed"] = {
                "count": len(rows),
                "sparkline": _bucketize(rows, "created_at"),
            }
        except Exception as exc:
            print(f"warn: pr_review aggregation failed: {exc!r}", file=sys.stderr)
            metrics["prs_reviewed"] = {"count": None, "sparkline": []}

        # Gaps we caught — every observation raised in window
        try:
            rows = _unwrap(
                await db.query(
                    "SELECT id, emitted_at FROM outcome_observation "
                    "WHERE product = <record>$pid "
                    "AND emission_kind IN ['recommendation', 'uncertainty', 'drift', 'pattern_matched'] "
                    "AND emitted_at > time::now() - 30d "
                    "ORDER BY emitted_at ASC",
                    {"pid": product_id},
                )
            )
            metrics["gaps_caught"] = {
                "count": len(rows),
                "sparkline": _bucketize(rows, "emitted_at"),
            }
        except Exception as exc:
            print(f"warn: gaps aggregation failed: {exc!r}", file=sys.stderr)
            metrics["gaps_caught"] = {"count": None, "sparkline": []}

        # You shipped — outcome_label committed/acted_on
        try:
            rows = _unwrap(
                await db.query(
                    "SELECT id, outcome_at FROM outcome_observation "
                    "WHERE product = <record>$pid "
                    "AND outcome_label IN ['committed', 'acted_on'] "
                    "AND outcome_at > time::now() - 30d "
                    "ORDER BY outcome_at ASC",
                    {"pid": product_id},
                )
            )
            metrics["you_shipped"] = {
                "count": len(rows),
                "sparkline": _bucketize(rows, "outcome_at"),
            }
        except Exception as exc:
            print(f"warn: you_shipped aggregation failed: {exc!r}", file=sys.stderr)
            metrics["you_shipped"] = {"count": None, "sparkline": []}

        # We both let go — outcome_label ignored/rejected
        try:
            rows = _unwrap(
                await db.query(
                    "SELECT id, outcome_at FROM outcome_observation "
                    "WHERE product = <record>$pid "
                    "AND outcome_label IN ['ignored', 'rejected'] "
                    "AND outcome_at > time::now() - 30d "
                    "ORDER BY outcome_at ASC",
                    {"pid": product_id},
                )
            )
            metrics["we_let_go"] = {
                "count": len(rows),
                "sparkline": _bucketize(rows, "outcome_at"),
            }
        except Exception as exc:
            print(f"warn: we_let_go aggregation failed: {exc!r}", file=sys.stderr)
            metrics["we_let_go"] = {"count": None, "sparkline": []}

        # Effectiveness Δ — 7-day-window comparison: avg(last 7d) vs avg(30-37d ago)
        try:
            rows_recent = _unwrap(
                await db.query(
                    "SELECT score, created_at FROM effectiveness_score "
                    "WHERE product = <record>$pid AND created_at > time::now() - 7d "
                    "ORDER BY created_at ASC",
                    {"pid": product_id},
                )
            )
            rows_prior = _unwrap(
                await db.query(
                    # SurrealDB v3 rejects `BETWEEN ... AND ...`; expand to two
                    # explicit comparisons. ORDER BY column appears in SELECT (v3
                    # quirk that bit voice-audit 4 times).
                    "SELECT score, created_at FROM effectiveness_score "
                    "WHERE product = <record>$pid "
                    "AND created_at >= time::now() - 37d "
                    "AND created_at <= time::now() - 30d "
                    "ORDER BY created_at ASC",
                    {"pid": product_id},
                )
            )
            recent_avg = _avg([r["score"] for r in rows_recent if "score" in r])
            prior_avg = _avg([r["score"] for r in rows_prior if "score" in r])
            delta_pct = (recent_avg - prior_avg) * 100  # express in percentage points
            # Sparkline: full 30-day series of average scores per day
            rows_full = _unwrap(
                await db.query(
                    "SELECT score, created_at FROM effectiveness_score "
                    "WHERE product = <record>$pid AND created_at > time::now() - 30d "
                    "ORDER BY created_at ASC",
                    {"pid": product_id},
                )
            )
            metrics["effectiveness"] = {
                "delta_pct": round(delta_pct, 1),
                "sparkline": _bucketize_avg_score(rows_full),
            }
        except Exception as exc:
            print(f"warn: effectiveness aggregation failed: {exc!r}", file=sys.stderr)
            metrics["effectiveness"] = {"delta_pct": None, "sparkline": []}

        # Tasks completed + cost saved — from token_ledger_entry.
        # Field names mirror TokenLedger.record()'s actual write shape
        # (intelligence/token_ledger.py): rows carry `product` (a record link,
        # hence <record>$pid), `resolved_at`, and cache reads nested at
        # tokens_by_stage.cache_read — the prior product_id / created_at /
        # cache_read_tokens read matched ZERO rows by construction.
        # Executor rows only: the ledger also carries per-call provider rows
        # (source="cli_provider"/"openai_compat") describing the SAME underlying
        # spend the executor accumulator already summarizes — counting them would
        # report raw LLM calls as "tasks we ran" and double-count cache savings.
        # The NONE/IS NULL hedge keeps legacy rows written before the source
        # field existed (consolidator.py idiom).
        try:
            rows = _unwrap(
                await db.query(
                    "SELECT id, resolved_at, cost_usd, "
                    "tokens_by_stage.cache_read AS cache_read_tokens "
                    "FROM token_ledger_entry "
                    "WHERE product = <record>$pid "
                    "AND (source = NONE OR source IS NULL OR source = 'executor') "
                    "AND resolved_at > time::now() - 30d "
                    "ORDER BY resolved_at ASC",
                    {"pid": product_id},
                )
            )
            metrics["tasks_completed"] = {
                "count": len(rows),
                "sparkline": _bucketize(rows, "resolved_at"),
            }
            _INPUT_RATE = 3.0 / 1_000_000  # $3/1M Sonnet input tokens
            saved = sum((r.get("cache_read_tokens") or 0) * _INPUT_RATE * 0.9 for r in rows)
            metrics["cost_saved_usd"] = {
                "amount_usd": round(saved, 4),
                "sparkline": _bucketize(rows, "resolved_at"),
            }
        except Exception as exc:
            print(f"warn: token_ledger aggregation failed: {exc!r}", file=sys.stderr)
            metrics["tasks_completed"] = {"count": None, "sparkline": []}
            metrics["cost_saved_usd"] = {"amount_usd": None, "sparkline": []}

    return _build_response(metrics)


def _build_response(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    gaps = metrics["gaps_caught"].get("count") or 0
    shipped = metrics["you_shipped"].get("count") or 0
    tasks = metrics["tasks_completed"].get("count") or 0
    saved = metrics["cost_saved_usd"].get("amount_usd") or 0.0
    headline = _HEADLINE_TEMPLATE.format(
        tasks=tasks,
        tasks_word="tasks" if tasks != 1 else "task",
        gaps=gaps,
        gaps_word="things" if gaps != 1 else "thing",
        shipped=shipped,
        saved=saved,
    )
    return {
        "metrics": metrics,
        "headline": headline,
        "deep_links": dict(_DEEP_LINKS),
        "window_days": 30,
    }


def _bucketize(rows: list[dict], date_field: str) -> list[int]:
    """Bucket row timestamps into 30 daily buckets (oldest first)."""
    now = datetime.now(timezone.utc)
    buckets = [0] * 30
    for r in rows:
        ts = r.get(date_field)
        if not ts:
            continue
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
        days_ago = (now - ts).days
        if 0 <= days_ago < 30:
            buckets[29 - days_ago] += 1
    return buckets


def _bucketize_avg_score(rows: list[dict]) -> list[float]:
    """Average score per day across 30 daily buckets."""
    now = datetime.now(timezone.utc)
    sums = [0.0] * 30
    counts = [0] * 30
    for r in rows:
        ts = r.get("created_at")
        score = r.get("score")
        if ts is None or score is None:
            continue
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
        days_ago = (now - ts).days
        if 0 <= days_ago < 30:
            sums[29 - days_ago] += float(score)
            counts[29 - days_ago] += 1
    return [round(sums[i] / counts[i], 3) if counts[i] > 0 else 0.0 for i in range(30)]


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
