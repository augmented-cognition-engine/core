"""M2 — Knowledge decay + composite freshness scoring.

freshness_score = age_weight    × age_factor
               + change_weight  × (1 - change_factor)
               + contradiction_weight × (1 - contradiction_factor)

Where each factor is 0.0–1.0. Score > 0.8 = fresh, 0.4–0.8 = aging, < 0.4 = stale.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class FreshnessResult:
    item_id: str
    freshness_score: float
    age_factor: float
    change_factor: float
    contradiction_factor: float
    label: str  # fresh | aging | stale


class FreshnessDecay:
    """Composite freshness scorer for insights and decisions."""

    WEIGHTS = {"age": 0.4, "change": 0.4, "contradiction": 0.2}
    AGE_HALFLIFE_DAYS = 180

    def compute(self, item: dict, governed_file_changes: dict[str, int]) -> FreshnessResult:
        """Compute freshness for a single insight/decision item.

        Args:
            item: DB record dict with at least {id, created_at, governed_files, contradiction_count}
            governed_file_changes: {file_path: changed_lines} for files the item governs
        """
        item_id = str(item.get("id", ""))

        # Age factor: exponential decay, half-life 180 days
        created_raw = item.get("created_at") or item.get("freshness_last_computed")
        age_days = self._age_days(created_raw)
        age_factor = math.exp(-age_days / self.AGE_HALFLIFE_DAYS)

        # Change factor: ratio of changed lines in governed files
        governed_files: list[str] = item.get("governed_files") or []
        change_factor = self._change_factor(governed_files, governed_file_changes)

        # Contradiction factor: saturates at 5 contradictions. `or 0` because the
        # SELECT returns the field as None (not absent) for rows that never set it,
        # and int(None) raises — which would abort the whole recompute_all table loop.
        contradiction_count = int(item.get("contradiction_count") or 0)
        contradiction_factor = min(contradiction_count / 5.0, 1.0)

        w = self.WEIGHTS
        score = (
            w["age"] * age_factor
            + w["change"] * (1.0 - change_factor)
            + w["contradiction"] * (1.0 - contradiction_factor)
        )
        score = max(0.0, min(1.0, score))

        if score > 0.8:
            label = "fresh"
        elif score >= 0.4:
            label = "aging"
        else:
            label = "stale"

        return FreshnessResult(
            item_id=item_id,
            freshness_score=round(score, 4),
            age_factor=round(age_factor, 4),
            change_factor=round(change_factor, 4),
            contradiction_factor=round(contradiction_factor, 4),
            label=label,
        )

    async def recompute_all(self, db_pool, product_id: str) -> int:
        """Batch recompute freshness for all insights/decisions.

        Reads governed_files from each record, computes file changes via git, writes back.
        Returns count of records updated.
        """
        from core.engine.core.db import parse_record_id, parse_rows

        file_changes = self._get_file_changes()

        count = 0
        for table in ("insight", "decision"):
            try:
                async with db_pool.connection() as db:
                    rows = parse_rows(
                        await db.query(
                            f"SELECT id, created_at, governed_files, contradiction_count "
                            f"FROM {table} WHERE product = <record>$product LIMIT 10000",
                            {"product": product_id},
                        )
                    )
                for row in rows:
                    result = self.compute(row, file_changes)
                    try:
                        async with db_pool.connection() as db:
                            await db.query(
                                "UPDATE $rid SET freshness_score = $score, freshness_last_computed = time::now()",
                                # RecordID target — v3 REFUSES a bare string here and returns the
                                # error as a result string (not a raise), so the write silently
                                # drops while count still increments. parse_record_id restores the ref.
                                {"rid": parse_record_id(str(row["id"])), "score": result.freshness_score},
                            )
                        count += 1
                    except Exception as exc:
                        logger.debug("freshness update failed for %s: %s", row.get("id"), exc)
            except Exception as exc:
                logger.warning("freshness.recompute_all %s query failed: %s", table, exc)

        logger.info("freshness.recompute_all: updated %d records for %s", count, product_id)
        return count

    def _age_days(self, created_raw) -> float:
        if created_raw is None:
            return 0.0
        try:
            if isinstance(created_raw, datetime):
                dt = created_raw
            else:
                dt = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (now - dt).total_seconds() / 86400)
        except Exception:
            return 0.0

    def _change_factor(self, governed_files: list[str], file_changes: dict[str, int]) -> float:
        """Fraction of governed-file lines that have changed."""
        if not governed_files:
            return 0.0
        total_changes = sum(file_changes.get(f, 0) for f in governed_files)
        total_lines = max(1, sum(file_changes.get(f, 100) for f in governed_files))
        return min(float(total_changes) / float(total_lines), 1.0)

    def _get_file_changes(self) -> dict[str, int]:
        """Get changed line counts from git since last week. Best-effort, empty on failure."""
        import subprocess

        try:
            out = subprocess.check_output(
                ["git", "diff", "--stat", "HEAD~7", "HEAD", "--"],
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).decode()
        except Exception:
            return {}

        changes: dict[str, int] = {}
        for line in out.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 2:
                path = parts[0].strip()
                nums = [s for s in parts[1].split() if s.isdigit()]
                if nums:
                    changes[path] = int(nums[0])
        return changes


def freshness_label(score: float) -> str:
    if score > 0.8:
        return "fresh"
    if score >= 0.4:
        return "aging"
    return "stale"
