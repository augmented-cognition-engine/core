# engine/cognition/crm_calibrator.py
"""CrmCalibrator — outcome-conditioned confidence calibration report.

Reads failure_memory records, groups by discipline, computes:
- avg_failing_confidence: average confidence of outputs that led to gaps_found verdict
- sample_count: total records for this discipline

If avg_failing_confidence > 0.7, the model is systematically overconfident for this
discipline — the ConfidenceGate threshold should be raised for it.

The calibration report is stored in calibration_report table for inspection.
This is a read-only diagnostic by default; threshold adjustment is advisory.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CrmCalibrator:
    """Computes calibration report from failure_memory records."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def compute_report(self, product_id: str) -> dict[str, dict]:
        """Read failure_memory, group by discipline, compute calibration stats.

        Returns dict of {discipline: {sample_count, avg_failing_confidence, overconfident}}.
        """
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    "SELECT discipline, verdict, confidence FROM failure_memory WHERE product = <record>$product",
                    {"product": product_id},
                )
            rows = result[0] if result and isinstance(result[0], list) else (result or [])
        except Exception as exc:
            logger.warning("CrmCalibrator: failed to load failure_memory: %s", exc)
            return {}

        if not rows:
            return {}

        # Group by discipline
        by_discipline: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            disc = row.get("discipline") or "unknown"
            by_discipline[disc].append(row)

        report: dict[str, dict] = {}
        for discipline, records in by_discipline.items():
            failing = [r for r in records if r.get("verdict") == "gaps_found"]
            avg_fail_conf = sum(r.get("confidence", 0.5) for r in failing) / len(failing) if failing else 0.0
            report[discipline] = {
                "sample_count": len(records),
                "failing_count": len(failing),
                "avg_failing_confidence": avg_fail_conf,
                "overconfident": avg_fail_conf > 0.7,  # advisory flag
            }

        return report

    async def run(self, product_id: str) -> dict[str, dict]:
        """Compute report and persist to calibration_report table. Returns report."""
        report = await self.compute_report(product_id)
        if not report:
            return report

        try:
            async with self._pool.connection() as db:
                await db.query(
                    "CREATE calibration_report CONTENT $data",
                    {
                        "data": {
                            "product": product_id,
                            "report": report,
                            "computed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
        except Exception as exc:
            logger.warning("CrmCalibrator: failed to write report: %s", exc)

        return report
