# engine/sentinel/engines/correlation_engine.py
"""D6 — Cross-discipline correlation engine.

Detects leading indicators between discipline score trajectories.
Runs weekly (Sunday 4 AM) after the gap_analyzer has run.

Prerequisite: requires 60+ days of capability_quality_snapshot data (from D2).
Correlations with |r| < 0.6 or fewer than 8 data points are discarded.

Output: correlation_signal table — used by briefing engine to emit warnings
when a leading-indicator dimension is currently declining.
"""

from __future__ import annotations

import logging
import math

from core.engine.core.db import parse_rows, pool
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

_MIN_SNAPSHOTS = 8  # minimum weekly data points before computing correlations
_MIN_CORRELATION = 0.6  # |r| threshold for a signal to be stored
_MAX_LAG_WEEKS = 8


@register_engine(
    name="correlation_engine",
    cron="0 4 * * sun",
    description="Detect cross-discipline score correlations. Requires 60+ days of snapshot history.",
)
async def run_correlation_engine(product_id: str) -> dict:
    """Analyze score trajectories across disciplines to find leading indicators.

    For each dimension pair (A, B):
    1. Load last 90 days of weekly-averaged snapshots
    2. Compute lagged correlation: does A dropping predict B dropping N weeks later?
    3. Store correlation_signal if |r| > 0.6 with lag 1-8 weeks

    Returns: {signals_found, pairs_checked, skipped_sparse}
    """
    results = {"signals_found": 0, "pairs_checked": 0, "skipped_sparse": 0}

    # Load weekly averages for all dimensions
    weekly_by_dim = await _load_weekly_averages(product_id, days=90)

    if not weekly_by_dim:
        logger.info("correlation_engine: no snapshot data for %s", product_id)
        return results

    dims = list(weekly_by_dim.keys())

    async with pool.connection() as db:
        for i, dim_a in enumerate(dims):
            for dim_b in dims:
                if dim_a == dim_b:
                    continue

                results["pairs_checked"] += 1
                series_a = weekly_by_dim[dim_a]
                series_b = weekly_by_dim[dim_b]

                if len(series_a) < _MIN_SNAPSHOTS or len(series_b) < _MIN_SNAPSHOTS:
                    results["skipped_sparse"] += 1
                    continue

                best_lag, best_r = _find_best_lag(series_a, series_b)
                if best_lag is None or abs(best_r) < _MIN_CORRELATION:
                    continue

                direction = "decline" if best_r > 0 else "inverse"
                interpretation = (
                    f"{dim_a} {direction} predicts {dim_b} {direction} "
                    f"{best_lag} week(s) later (r={best_r:.2f}, "
                    f"{len(series_a)} data points)"
                )

                await db.query(
                    """CREATE correlation_signal SET
                        product                = <record>$product,
                        dimension_a            = $dim_a,
                        dimension_b            = $dim_b,
                        lag_weeks              = $lag,
                        correlation_coefficient = $r,
                        interpretation         = $interpretation,
                        snapshot_count         = $n,
                        computed_at            = time::now()
                    """,
                    {
                        "product": product_id,
                        "dim_a": dim_a,
                        "dim_b": dim_b,
                        "lag": best_lag,
                        "r": best_r,
                        "interpretation": interpretation,
                        "n": len(series_a),
                    },
                )
                results["signals_found"] += 1

    logger.info(
        "correlation_engine: %s — %d signals from %d pairs (%d sparse)",
        product_id,
        results["signals_found"],
        results["pairs_checked"],
        results["skipped_sparse"],
    )
    return results


async def _load_weekly_averages(product_id: str, days: int = 90) -> dict[str, list[float]]:
    """Load capability_quality_snapshot and aggregate to weekly averages per dimension.

    Returns: {dimension: [week0_avg, week1_avg, ...]} sorted oldest→newest
    """
    import datetime

    cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)).isoformat()

    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT dimension, score, assessed_at
                       FROM capability_quality_snapshot
                       WHERE product = <record>$product
                       AND assessed_at > <datetime>$cutoff
                       ORDER BY assessed_at ASC""",
                    {"product": product_id, "cutoff": cutoff},
                )
            )
    except Exception as exc:
        logger.warning("correlation_engine: failed to load snapshots: %s", exc)
        return {}

    # Group by dimension → week bucket → list of scores
    weekly: dict[str, dict[int, list[float]]] = {}
    now = datetime.datetime.now(datetime.UTC)

    for r in rows:
        dim = r.get("dimension", "")
        score = float(r.get("score", 0.0))
        at_str = str(r.get("assessed_at", ""))[:10]
        try:
            at = datetime.datetime.fromisoformat(at_str)
        except ValueError:
            continue
        week_ago = (now - at).days // 7
        weekly.setdefault(dim, {}).setdefault(week_ago, []).append(score)

    result: dict[str, list[float]] = {}
    for dim, week_buckets in weekly.items():
        sorted_weeks = sorted(week_buckets.keys(), reverse=True)  # oldest week = highest number
        result[dim] = [round(sum(week_buckets[w]) / len(week_buckets[w]), 4) for w in sorted_weeks]

    return result


def _pearson_r(xs: list[float], ys: list[float]) -> float:
    """Compute Pearson correlation coefficient between two equal-length series."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return num / (denom_x * denom_y)


def _find_best_lag(
    series_a: list[float],
    series_b: list[float],
) -> tuple[int | None, float]:
    """Find the lag (weeks) where series_a best predicts series_b.

    Tries lags 1..MAX_LAG_WEEKS. Returns (best_lag, best_r) or (None, 0.0)
    if no lag achieves |r| >= _MIN_CORRELATION.
    """
    best_lag = None
    best_r = 0.0

    for lag in range(1, min(_MAX_LAG_WEEKS + 1, len(series_a))):
        a_shifted = series_a[:-lag]
        b_aligned = series_b[lag:]
        min_len = min(len(a_shifted), len(b_aligned))
        if min_len < 3:
            continue
        r = _pearson_r(a_shifted[:min_len], b_aligned[:min_len])
        if abs(r) > abs(best_r):
            best_r = r
            best_lag = lag

    if best_lag is None or abs(best_r) < _MIN_CORRELATION:
        return None, 0.0

    return best_lag, round(best_r, 4)


async def get_correlation_signals(
    product_id: str,
    declining_dimension: str,
    db=None,
) -> list[dict]:
    """Return active correlation signals where dimension_a matches a declining dimension.

    Used by briefing engine to emit predictive warnings.

    When called from inside an engine that already holds a connection (e.g. the
    briefing engine via `build_product_health_section`), the caller should pass
    `db` to avoid acquiring a nested connection — the briefing engine iterates
    over every declining dimension, so a fresh `pool.connection()` per call
    can exhaust the pool and leak connections (>120s checkouts).

    Returns: list of {dimension_b, lag_weeks, correlation_coefficient, interpretation}
    """
    query = """SELECT dimension_b, lag_weeks, correlation_coefficient, interpretation, computed_at
               FROM correlation_signal
               WHERE product = <record>$product
               AND dimension_a = <string>$dim
               ORDER BY computed_at DESC LIMIT 5"""
    params = {"product": product_id, "dim": declining_dimension}
    try:
        if db is not None:
            return parse_rows(await db.query(query, params))
        async with pool.connection() as conn:
            return parse_rows(await conn.query(query, params))
    except Exception:
        return []
