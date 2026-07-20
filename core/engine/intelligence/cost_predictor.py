"""CostPredictor — pre-task cost estimate from token ledger history.

Queries token_ledger_entry for historical costs in this discipline and
returns p50/p90 estimates so the composition context can warn about
expensive operations before they run, not after.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


class CostPredictor:
    async def estimate(self, discipline: str, product_id: str, window_days: int = 30) -> dict:
        """Return {discipline, p50_usd, p90_usd, sample_count} or empty dict on error."""
        # Field names mirror TokenLedger.record()'s actual write shape: rows
        # carry `product` (record link, hence <record>$pid) and `resolved_at`
        # — the prior product_id/created_at read matched zero rows. The
        # duration::from::days() idiom matches token_ledger.py (a raw string
        # bind is not a duration). No source filter needed: per-call provider
        # rows write discipline="", so the discipline match excludes them
        # structurally for any real discipline.
        try:
            async with pool.connection() as db:
                rows = parse_rows(
                    await db.query(
                        """SELECT cost_usd, resolved_at FROM token_ledger_entry
                           WHERE product = <record>$pid
                             AND discipline = $discipline
                             AND resolved_at > time::now() - duration::from::days($window_days)
                           ORDER BY resolved_at DESC
                           LIMIT 200""",
                        {
                            "pid": product_id,
                            "discipline": discipline,
                            "window_days": window_days,
                        },
                    )
                )
            costs = sorted(float(r["cost_usd"]) for r in rows if r.get("cost_usd") is not None)
            n = len(costs)
            if n == 0:
                return {"discipline": discipline, "p50_usd": 0.0, "p90_usd": 0.0, "sample_count": 0}
            p50 = costs[int(n * 0.50)]
            p90 = costs[min(int(n * 0.90), n - 1)]
            return {
                "discipline": discipline,
                "p50_usd": round(p50, 6),
                "p90_usd": round(p90, 6),
                "sample_count": n,
            }
        except Exception as exc:
            logger.debug("CostPredictor failed (non-fatal): %s", exc)
            return {}
