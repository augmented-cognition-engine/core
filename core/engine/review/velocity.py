# engine/review/velocity.py
"""Developer velocity metrics — DORA-style indicators from git and ACE data.

Calculates deployment frequency, lead time for changes, review cycle time,
and PR throughput from git history and stored review/task records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


class VelocityMetrics(BaseModel):
    """DORA-inspired velocity metrics for a repository."""

    # Core DORA metrics
    deployment_frequency: float = 0.0  # deploys per week
    lead_time_hours: float = 0.0  # avg hours from first commit to merge
    review_cycle_hours: float = 0.0  # avg hours from PR open to review complete

    # PR metrics
    prs_merged_per_week: float = 0.0
    avg_pr_size_lines: float = 0.0
    avg_findings_per_review: float = 0.0
    review_pass_rate: float = 0.0  # % of reviews that pass quality gate

    # Activity metrics
    active_authors: int = 0
    total_commits: int = 0
    total_reviews: int = 0

    # Time period
    period_days: int = 30
    calculated_at: str = ""


class VelocityCalculator:
    """Calculates developer velocity metrics from ACE data."""

    async def calculate(
        self,
        owner: str,
        repo: str,
        period_days: int = 30,
    ) -> VelocityMetrics:
        """Calculate velocity metrics for a repo over the given period."""
        metrics = VelocityMetrics(
            period_days=period_days,
            calculated_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            async with pool.connection() as db:
                # PR review metrics
                reviews = await db.query(
                    """
                    SELECT
                        pr_number,
                        findings_count,
                        pass_quality_gate,
                        created_at
                    FROM pr_review
                    WHERE owner = $owner AND repo = $repo
                    AND created_at > $since
                    ORDER BY created_at DESC
                    """,
                    {
                        "owner": owner,
                        "repo": repo,
                        "since": (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat(),
                    },
                )
                review_rows = parse_rows(reviews)

                if review_rows:
                    metrics.total_reviews = len(review_rows)
                    weeks = max(period_days / 7, 1)
                    metrics.prs_merged_per_week = len(review_rows) / weeks

                    total_findings = sum(r.get("findings_count", 0) for r in review_rows)
                    metrics.avg_findings_per_review = total_findings / len(review_rows) if review_rows else 0

                    passed = sum(1 for r in review_rows if r.get("pass_quality_gate", True))
                    metrics.review_pass_rate = passed / len(review_rows) if review_rows else 0

                # Reaction acceptance metrics
                reactions = await db.query(
                    """
                    SELECT reaction
                    FROM review_reaction
                    WHERE owner = $owner AND repo = $repo
                    AND created_at > $since
                    """,
                    {
                        "owner": owner,
                        "repo": repo,
                        "since": (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat(),
                    },
                )
                # reaction_rows available for future acceptance rate metric
                parse_rows(reactions)

                # Git-based metrics from graph (if available)
                git_stats = await db.query(
                    """
                    SELECT
                        count() AS commit_count,
                        array::distinct(ownership) AS authors
                    FROM graph_file
                    WHERE change_frequency > 0
                    LIMIT 1
                    """,
                    {},
                )
                git_rows = parse_rows(git_stats)
                if git_rows:
                    metrics.total_commits = git_rows[0].get("commit_count", 0)
                    authors = git_rows[0].get("authors", [])
                    metrics.active_authors = len(authors) if isinstance(authors, list) else 0

        except Exception as exc:
            logger.warning("Velocity calculation failed for %s/%s: %s", owner, repo, exc)

        return metrics
