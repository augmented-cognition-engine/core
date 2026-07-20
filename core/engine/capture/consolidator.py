"""M4 — Nightly observation consolidation.

Clusters near-identical observations across sessions into canonical patterns.
Idempotent: runs daily, skips already-archived items.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CONSOLIDATION_THRESHOLD = 10
CLUSTER_MIN_SIZE = 5
SIMILARITY_THRESHOLD = 0.82


@dataclass
class ConsolidationResult:
    items_processed: int = 0
    clusters_found: int = 0
    patterns_created: int = 0
    items_archived: int = 0
    errors: list[str] = field(default_factory=list)


class ObservationConsolidator:
    """Nightly batch consolidation of similar observations into canonical patterns."""

    async def run(self, product_id: str, db_pool) -> ConsolidationResult:
        """Main entry point. Idempotent — skips archived items."""
        from core.engine.core.db import parse_rows

        result = ConsolidationResult()

        try:
            async with db_pool.connection() as db:
                rows = parse_rows(
                    await db.query(
                        """SELECT id, content, type, confidence, tags
                    FROM insight
                    WHERE product = <record>$product
                    AND (archived_at = NONE OR archived_at IS NULL)
                    AND observation_count > $threshold
                    LIMIT 5000""",
                        {"product": product_id, "threshold": CONSOLIDATION_THRESHOLD},
                    )
                )
        except Exception as exc:
            logger.warning("consolidator.run: query failed: %s", exc)
            return result

        result.items_processed = len(rows)
        if not rows:
            return result

        clusters = await self._cluster(rows)
        result.clusters_found = len(clusters)

        for cluster in clusters:
            if len(cluster) < CLUSTER_MIN_SIZE:
                continue
            try:
                canonical = await self._synthesize_cluster(cluster)
                if not canonical:
                    continue

                # Write canonical pattern
                async with db_pool.connection() as db:
                    new_row = parse_rows(
                        await db.query(
                            """CREATE insight SET
                            product = <record>$product,
                            type = 'pattern',
                            content = $content,
                            confidence = $confidence,
                            tags = ['consolidation'],
                            source = 'consolidation',
                            created_at = time::now()
                        """,
                            {
                                "product": product_id,
                                "content": canonical["content"],
                                "confidence": canonical.get("confidence", 0.75),
                            },
                        )
                    )
                    if not new_row:
                        continue
                    new_id = str(new_row[0]["id"])

                # Archive originals
                for item in cluster:
                    try:
                        async with db_pool.connection() as db:
                            await db.query(
                                "UPDATE $rid SET archived_at = time::now(), consolidated_into = <record>$new_id",
                                {"rid": str(item["id"]), "new_id": new_id},
                            )
                        result.items_archived += 1
                    except Exception as exc:
                        logger.debug("consolidator: archive failed for %s: %s", item.get("id"), exc)

                result.patterns_created += 1
            except Exception as exc:
                result.errors.append(str(exc))
                logger.warning("consolidator: cluster synthesis failed: %s", exc)

        logger.info(
            "consolidator.run: processed=%d clusters=%d patterns=%d archived=%d",
            result.items_processed,
            result.clusters_found,
            result.patterns_created,
            result.items_archived,
        )
        return result

    async def _cluster(self, observations: list[dict]) -> list[list[dict]]:
        """Group observations by Jaccard similarity (cheap, no embedder dependency)."""
        import re

        word_re = re.compile(r"[a-z0-9]+")

        def tokenize(text: str) -> frozenset[str]:
            return frozenset(word_re.findall((text or "").lower()))

        def jaccard(a: frozenset, b: frozenset) -> float:
            if not a and not b:
                return 1.0
            union = a | b
            return len(a & b) / len(union) if union else 0.0

        assigned: list[int] = [-1] * len(observations)
        clusters: list[list[int]] = []
        tokens = [tokenize(o.get("content", "")) for o in observations]

        for i in range(len(observations)):
            if assigned[i] != -1:
                continue
            cluster_idx = len(clusters)
            clusters.append([i])
            assigned[i] = cluster_idx
            for j in range(i + 1, len(observations)):
                if assigned[j] != -1:
                    continue
                if jaccard(tokens[i], tokens[j]) >= SIMILARITY_THRESHOLD:
                    clusters[cluster_idx].append(j)
                    assigned[j] = cluster_idx

        return [[observations[i] for i in c] for c in clusters]

    async def _synthesize_cluster(self, cluster: list[dict]) -> dict | None:
        """LLM call: synthesize N similar observations into 1 canonical pattern."""
        try:
            from core.engine.core.llm import get_llm

            examples = "\n".join(f"- {item.get('content', '')[:150]}" for item in cluster[:10])
            prompt = (
                f"Synthesize these {len(cluster)} related observations into one concise "
                f"canonical pattern statement (1-2 sentences). "
                f"Return only the pattern, no preamble.\n\n{examples}"
            )
            llm = get_llm()
            response = (await llm.complete(prompt, max_tokens=150) or "").strip()
            if not response:
                return None
            avg_confidence = sum(float(o.get("confidence", 0.5)) for o in cluster) / len(cluster)
            return {"content": response, "confidence": min(0.95, avg_confidence + 0.1)}
        except Exception as exc:
            logger.debug("consolidator._synthesize_cluster failed: %s", exc)
            return None
