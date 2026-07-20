# engine/review/learning.py
"""Adaptive learning from developer reactions to review comments.

Tracks which findings developers accept (resolve/fix) vs dismiss (won't fix/ignore).
Feeds accepted patterns into ACE's capture pipeline as positive signals,
and dismissed patterns as noise indicators to suppress in future reviews.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


class ReviewLearner:
    """Tracks and learns from developer reactions to review findings."""

    async def record_reaction(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        finding_index: int,
        reaction: str,  # accepted | dismissed | modified
        comment: str = "",
    ) -> dict:
        """Record a developer's reaction to a review finding."""
        async with pool.connection() as db:
            result = await db.query(
                """
                CREATE review_reaction SET
                    owner = $owner,
                    repo = $repo,
                    pr_number = $pr_number,
                    finding_index = $finding_index,
                    reaction = $reaction,
                    comment = $comment,
                    created_at = time::now()
                """,
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "finding_index": finding_index,
                    "reaction": reaction,
                    "comment": comment,
                },
            )
            rows = parse_rows(result)
            return rows[0] if rows else {}

    async def get_acceptance_rates(
        self,
        owner: str,
        repo: str,
        limit: int = 100,
    ) -> dict[str, float]:
        """Get acceptance rates by discipline.

        Returns dict of {discipline: acceptance_rate} where 1.0 = all accepted.
        """
        async with pool.connection() as db:
            result = await db.query(
                """
                SELECT reaction, meta, created_at
                FROM review_reaction
                WHERE owner = $owner AND repo = $repo
                ORDER BY created_at DESC
                LIMIT $limit
                """,
                {"owner": owner, "repo": repo, "limit": limit},
            )
            rows = parse_rows(result)

        if not rows:
            return {}

        by_discipline: dict[str, dict[str, int]] = defaultdict(lambda: {"accepted": 0, "total": 0})
        for row in rows:
            discipline = (row.get("meta") or {}).get("discipline", "unknown")
            by_discipline[discipline]["total"] += 1
            if row.get("reaction") == "accepted":
                by_discipline[discipline]["accepted"] += 1

        return {
            disc: counts["accepted"] / counts["total"] if counts["total"] > 0 else 0.5
            for disc, counts in by_discipline.items()
        }

    async def feed_to_capture(
        self,
        owner: str,
        repo: str,
        finding: dict,
        reaction: str,
        product_id: str = "product:platform",
    ) -> None:
        """Feed reaction into ACE's capture pipeline as an observation."""
        try:
            if reaction == "accepted":
                content = (
                    f"Review finding accepted by developer: "
                    f"[{finding.get('discipline', '')}] {finding.get('message', '')}"
                )
                obs_type = "pattern"
            elif reaction == "dismissed":
                content = (
                    f"Review finding dismissed by developer (likely false positive): "
                    f"[{finding.get('discipline', '')}] {finding.get('message', '')}"
                )
                obs_type = "correction"
            else:
                return

            discipline = finding.get("discipline", "")
            async with pool.connection() as db:
                await db.query(
                    """
                    CREATE observation SET
                        product = <record>$product,
                        observation_type = $type,
                        content = $content,
                        discipline_hint = $discipline_hint,
                        domain_hint = $domain_hint,
                        confidence = $confidence,
                        source = 'review_reaction',
                        synthesized = false,
                        created_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "type": obs_type,
                        "content": content,
                        "discipline_hint": discipline,
                        "domain_hint": discipline,
                        "confidence": 0.7,
                    },
                )
        except Exception as exc:
            logger.warning("Failed to feed reaction to capture: %s", exc)
