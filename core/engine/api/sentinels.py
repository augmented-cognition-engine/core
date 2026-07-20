# engine/api/sentinels.py
"""Sentinel health surface — exposes the L8 autonomic layer to the user.

ACE has 35 sentinel engines running on cron schedules. Without this surface,
the user can't see what's monitoring their system, when each last ran, or
what each found. This endpoint joins the static registry (engine name, cron,
description) with the engine_run telemetry table (last status, last
findings, last duration) so the frontend can render a "what's watching"
dashboard.

Closes audit gap #1: 35 invisible sentinels surfaced.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from core.engine.core.db import parse_rows, pool
from core.engine.sentinel.registry import list_engines

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sentinels"])


def _ensure_engines_loaded() -> None:
    """Import every engine module so its @register_engine decorator fires.

    Engines register at import time. The scheduler imports them on its own
    schedule, but a fresh process serving only API traffic won't have them
    in the registry until something triggers the imports. Idempotent — Python
    caches modules.
    """
    import importlib
    import pkgutil

    import core.engine.sentinel.engines as engines_pkg

    for _finder, modname, _ispkg in pkgutil.iter_modules(engines_pkg.__path__):
        if modname.startswith("_"):
            continue
        try:
            importlib.import_module(f"core.engine.sentinel.engines.{modname}")
        except Exception as exc:
            logger.warning("Failed to import sentinel engine %s: %s", modname, exc)


@router.get("/sentinels/status")
async def get_sentinels_status(product_id: str = "product:platform") -> dict[str, Any]:
    """Health snapshot of every registered sentinel engine.

    Joins the static registry (decorator-driven, no DB) with the most-recent
    engine_run row per engine for the given product. Engines that have never
    run for this product return last_run=None.

    Response shape:
      {
        "sentinels": [
          {
            "name": "decay_manager",
            "cron": "0 2 * * *",
            "description": "Daily confidence decay",
            "last_run": {
              "status": "completed" | "running" | "failed",
              "started_at": "<iso datetime>",
              "completed_at": "<iso datetime>" | None,
              "duration_ms": 1234 | None,
              "results_summary": "<one-line digest>" | None,
              "cost": 0.0
            } | None,
            "schedule_label": "daily 02:00" | "every 4h" | etc.   # human-friendly cron
          },
          ...
        ],
        "counts": {
          "total": 35,
          "ran_in_last_24h": 28,
          "failed_in_last_24h": 0,
          "never_run_for_this_product": 7
        }
      }
    """
    _ensure_engines_loaded()
    registered = list_engines()

    # Pull last 500 engine_run rows for this product; dedupe in Python by
    # first-seen (since ORDER BY started_at DESC). Single query keeps the
    # endpoint fast even with 35+ engines.
    last_runs: dict[str, dict[str, Any]] = {}
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT engine, status, started_at, completed_at,
                              duration_ms, results, cost
                       FROM engine_run
                       WHERE product = <record>$product
                       ORDER BY started_at DESC
                       LIMIT 500""",
                    {"product": product_id},
                )
            )
        for row in rows:
            engine = str(row.get("engine") or "")
            if engine and engine not in last_runs:
                last_runs[engine] = row
    except Exception:
        logger.warning("get_sentinels_status: engine_run query failed (non-fatal)", exc_info=True)
        # Empty last_runs — endpoint still returns the registry shape, just
        # with last_run=None on every entry.

    sentinels: list[dict[str, Any]] = []
    ran_in_last_24h = 0
    failed_in_last_24h = 0

    from datetime import datetime, timedelta, timezone

    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    for entry in registered:
        name = entry["name"]
        last = last_runs.get(name)
        last_run_block: dict[str, Any] | None = None
        if last:
            started_at = last.get("started_at")
            # Counts for the summary
            if isinstance(started_at, datetime) and started_at >= cutoff_24h:
                ran_in_last_24h += 1
                if last.get("status") == "failed":
                    failed_in_last_24h += 1
            last_run_block = {
                "status": last.get("status"),
                "started_at": started_at.isoformat() if isinstance(started_at, datetime) else started_at,
                "completed_at": (
                    last.get("completed_at").isoformat()
                    if isinstance(last.get("completed_at"), datetime)
                    else last.get("completed_at")
                ),
                "duration_ms": last.get("duration_ms"),
                "results_summary": _summarize_results(last.get("results")),
                "cost": float(last.get("cost") or 0.0),
            }

        sentinels.append(
            {
                "name": name,
                "cron": entry["cron"],
                "description": entry["description"],
                "schedule_label": _humanize_cron(entry["cron"]),
                "last_run": last_run_block,
            }
        )

    # Sort: ran-recently first, never-run last. String compare on ISO datetime
    # works lexicographically; reverse=True puts the newest first.
    has_run = [s for s in sentinels if s["last_run"]]
    never_run = [s for s in sentinels if not s["last_run"]]
    has_run.sort(key=lambda s: s["last_run"]["started_at"] or "", reverse=True)
    sentinels = has_run + never_run

    return {
        "sentinels": sentinels,
        "counts": {
            "total": len(registered),
            "ran_in_last_24h": ran_in_last_24h,
            "failed_in_last_24h": failed_in_last_24h,
            "never_run_for_this_product": len(never_run),
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarize_results(results: Any) -> str | None:
    """One-line digest of the engine's results dict for the dashboard.

    Engines return arbitrary shapes; pick the most-informative scalar/key.
    """
    if not isinstance(results, dict):
        return None
    if not results:
        return "no findings"
    # Prefer common keys engines return
    for key in ("inferred", "processed", "findings", "decisions", "matches", "n", "count"):
        if key in results and isinstance(results[key], (int, float)):
            return f"{key}={results[key]}"
    # Fallback: first non-zero scalar
    for k, v in results.items():
        if isinstance(v, (int, float)) and v:
            return f"{k}={v}"
    return f"{len(results)} keys"


# Tiny cron→label heuristic. Not exhaustive — covers the patterns ACE actually uses.
_CRON_LABELS = {
    "0 0 * * *": "daily 00:00",
    "0 1 * * *": "daily 01:00",
    "0 2 * * *": "daily 02:00",
    "0 3 * * *": "daily 03:00",
    "0 4 * * *": "daily 04:00",
    "0 5 * * *": "daily 05:00",
    "0 6 * * *": "daily 06:00",
    "0 12 * * *": "daily 12:00",
    "0 */1 * * *": "hourly",
    "0 */2 * * *": "every 2h",
    "0 */4 * * *": "every 4h",
    "0 */6 * * *": "every 6h",
    "*/5 * * * *": "every 5min",
    "*/15 * * * *": "every 15min",
    "*/30 * * * *": "every 30min",
}


def _humanize_cron(cron: str) -> str:
    """Map common cron patterns to human-friendly labels; fall back to raw cron."""
    return _CRON_LABELS.get(cron, cron)
