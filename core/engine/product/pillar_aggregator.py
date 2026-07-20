"""Pillar score aggregator with cache + invalidation.

Reads existing capability_quality dim scores, aggregates to 7 pillars,
caches in pillar_score_cache. Cache invalidates on capability score change,
ambition change, phase change, type/scale change, floor override.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from core.engine.core.db import parse_rows
from core.engine.product.pillars import Pillar, aggregate_to_pillars

_CACHE_TTL_SECONDS = 60


class PillarAggregator:
    def __init__(self, pool):
        self._pool = pool

    async def get_pillar_scores(self, product_id: str, use_cache: bool = True) -> dict[Pillar, float]:
        """Return all 7 pillar scores for a product. Uses cache when warm."""
        if use_cache:
            cached = await self._read_cache_all(product_id)
            if cached is not None:
                return cached
        dim_scores = await self._read_dim_scores(product_id)
        pillar_scores = self._aggregate_from_dim_scores(dim_scores)
        for p, s in pillar_scores.items():
            await self._write_cache(product_id, p, s)
        return pillar_scores

    def _aggregate_from_dim_scores(self, dim_scores: dict[str, float]) -> dict[Pillar, float]:
        return aggregate_to_pillars(dim_scores)

    async def _read_dim_scores(self, product_id: str) -> dict[str, float]:
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT dimension, math::mean(score) AS avg_score
                   FROM capability_quality
                   WHERE product = <record>$pid
                   GROUP BY dimension""",
                {"pid": product_id},
            )
        rows = parse_rows(result)
        return {r.get("dimension", ""): float(r.get("avg_score", 0.0)) for r in rows if r.get("dimension")}

    async def _read_cache(self, product_id: str, pillar: Pillar) -> Optional[float]:
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT score, computed_at FROM pillar_score_cache
                   WHERE product = <record>$pid
                     AND pillar = <string>$pillar
                     AND invalidated_at = NONE
                   ORDER BY computed_at DESC LIMIT 1""",
                {"pid": product_id, "pillar": pillar.value},
            )
        rows = parse_rows(result)
        if not rows:
            return None
        row = rows[0]
        computed_at = row.get("computed_at")
        if isinstance(computed_at, str):
            computed_at = datetime.fromisoformat(computed_at.replace("Z", "+00:00"))
        if computed_at and datetime.now(computed_at.tzinfo) - computed_at > timedelta(seconds=_CACHE_TTL_SECONDS):
            return None
        return float(row.get("score", 0.0))

    async def _read_cache_all(self, product_id: str) -> Optional[dict[Pillar, float]]:
        result_map: dict[Pillar, float] = {}
        for p in Pillar:
            score = await self._read_cache(product_id, p)
            if score is None:
                return None
            result_map[p] = score
        return result_map

    async def _write_cache(self, product_id: str, pillar: Pillar, score: float) -> None:
        async with self._pool.connection() as db:
            await db.query(
                """CREATE pillar_score_cache CONTENT {
                    product: <record>$pid,
                    pillar: <string>$pillar,
                    score: <float>$score,
                    computed_at: time::now(),
                    invalidated_at: NONE
                }""",
                {"pid": product_id, "pillar": pillar.value, "score": score},
            )

    async def invalidate(self, product_id: str) -> None:
        """Mark all cached scores for product as invalidated."""
        async with self._pool.connection() as db:
            await db.query(
                """UPDATE pillar_score_cache
                   SET invalidated_at = time::now()
                   WHERE product = <record>$pid AND invalidated_at = NONE""",
                {"pid": product_id},
            )
