# engine/reports/assembler.py
"""DataAssembler — gathers intelligence from DB for report generation."""

from __future__ import annotations

import logging
from datetime import datetime

from core.engine.core.db import parse_rows

logger = logging.getLogger(__name__)

_SEVERITY_MAP = [
    (0.3, "critical"),
    (0.55, "high"),
    (0.7, "medium"),
]


def _severity(score: float) -> str:
    for threshold, label in _SEVERITY_MAP:
        if score < threshold:
            return label
    return "low"


class DataAssembler:
    def __init__(self, pool) -> None:
        self._pool = pool

    async def assemble(
        self,
        product_id: str,
        report_type: str,
        client_name: str = "",
        consultant_name: str = "",
    ) -> dict:
        quality_rows = await self._load_quality(product_id)
        capabilities = await self._load_capabilities(product_id)
        decisions = await self._load_decisions(product_id)
        initiatives = await self._load_initiatives(product_id)

        health_by_discipline = self._aggregate_health(quality_rows)
        top_risks = self._extract_risks(quality_rows)

        return {
            "product_name": product_id.split(":")[-1].replace("_", " ").title(),
            "report_type": report_type,
            "client_name": client_name,
            "consultant_name": consultant_name,
            "generated_at": datetime.now().strftime("%B %d, %Y"),
            "health_by_discipline": health_by_discipline,
            "top_risks": top_risks,
            "capabilities": capabilities,
            "recent_decisions": decisions,
            "initiatives": initiatives,
            "score_deltas": [],  # populated by snapshot path only
        }

    async def _load_quality(self, product_id: str) -> list[dict]:
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    """SELECT capability, dimension AS discipline, score, gaps
                       FROM capability_quality
                       WHERE product = <record>$product""",
                    {"product": product_id},
                )
                return parse_rows(result)
        except Exception as exc:
            logger.warning("Failed to load quality rows: %s", exc)
            return []

    async def _load_capabilities(self, product_id: str) -> list[dict]:
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    """SELECT slug, description, category, depends_on FROM capability
                       WHERE product = <record>$product
                       LIMIT 30""",
                    {"product": product_id},
                )
                return parse_rows(result)
        except Exception as exc:
            logger.warning("Failed to load capabilities: %s", exc)
            return []

    async def _load_decisions(self, product_id: str) -> list[dict]:
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    """SELECT title, rationale, decision_type, created_at
                       FROM decision
                       WHERE product = <record>$product
                       ORDER BY created_at DESC
                       LIMIT 5""",
                    {"product": product_id},
                )
                return parse_rows(result)
        except Exception as exc:
            logger.warning("Failed to load decisions: %s", exc)
            return []

    async def _load_initiatives(self, product_id: str) -> list[dict]:
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    """SELECT title, status, description, created_at
                       FROM initiative
                       WHERE product = <record>$product
                         AND status IN ['active', 'completed']
                       ORDER BY created_at DESC
                       LIMIT 10""",
                    {"product": product_id},
                )
                return parse_rows(result)
        except Exception as exc:
            logger.warning("Failed to load initiatives: %s", exc)
            return []

    def _aggregate_health(self, rows: list[dict]) -> list[dict]:
        by_discipline: dict[str, list[float]] = {}
        for r in rows:
            d = r.get("discipline", "")
            if not d:
                continue
            by_discipline.setdefault(d, []).append(float(r.get("score", 0)))
        result = []
        for discipline, scores in by_discipline.items():
            avg = sum(scores) / len(scores)
            result.append(
                {
                    "discipline": discipline,
                    "avg_score": round(avg, 3),
                    "gap_count": sum(1 for s in scores if s < 0.6),
                }
            )
        result.sort(key=lambda x: x["avg_score"])
        return result

    def _extract_risks(self, rows: list[dict]) -> list[dict]:
        risks = []
        for r in rows:
            score = float(r.get("score", 1.0))
            sev = _severity(score)
            if sev == "low":
                continue
            gaps = r.get("gaps") or []  # DB may return null → use []
            risks.append(
                {
                    "discipline": r.get("discipline", ""),
                    "capability_slug": str(r.get("capability", "")).split(":")[-1],
                    "score": round(score, 3),
                    "gaps": gaps[:3],  # top 3 gaps per item
                    "severity": sev,
                }
            )
        risks.sort(key=lambda x: x["score"])
        return risks[:7]
