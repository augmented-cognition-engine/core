# engine/review/watcher.py
"""Review watcher — triggers automated reviews on local branch changes.

Integrates with ACE's existing infrastructure to automatically review
code when branches diverge from main. Designed for local CI workflows.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from core.engine.core.db import parse_rows, pool
from core.engine.review.engine import ReviewEngine
from core.engine.review.impact import PRImpactAnalyzer
from core.engine.review.judge import Judge
from core.engine.review.providers import LocalGitProvider

logger = logging.getLogger(__name__)


async def check_and_review(
    repo_path: str = ".",
    base_branch: str = "main",
    product_id: str = "product:platform",
    force: bool = False,
) -> dict | None:
    """Check if current branch has unreviewed changes and trigger review.

    Returns review result dict, or None if no review needed.
    Designed to be called periodically (e.g., by commit watcher or cron).
    """
    repo = Path(repo_path).resolve()

    # Get current branch
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    current_branch = result.stdout.strip()

    if current_branch == base_branch and not force:
        return None  # Don't review main against itself

    # Get head commit SHA
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    head_sha = result.stdout.strip()

    # Check if we already reviewed this SHA
    if not force:
        try:
            async with pool.connection() as db:
                existing = await db.query(
                    """
                    SELECT id FROM pr_review
                    WHERE owner = 'local' AND repo = $repo
                    AND meta.head_sha = $sha
                    LIMIT 1
                    """,
                    {"repo": repo.name, "sha": head_sha},
                )
                rows = parse_rows(existing)
                if rows:
                    logger.debug("Already reviewed %s at %s", current_branch, head_sha[:8])
                    return None
        except Exception:
            pass  # DB check is best-effort

    # Run review
    logger.info("Reviewing %s (%s) against %s", current_branch, head_sha[:8], base_branch)

    provider = LocalGitProvider(repo_path=str(repo), base_branch=base_branch)
    pr, files = await provider.get_diff()

    if not files:
        logger.info("No changes to review on %s", current_branch)
        return None

    engine = ReviewEngine(product_id=product_id)
    passes = await engine.run_passes(pr, files)

    judge = Judge()
    synthesis = await judge.synthesize(passes)

    analyzer = PRImpactAnalyzer()
    impact = await analyzer.full_impact([f.path for f in files], product_id)

    # Persist review
    try:
        async with pool.connection() as db:
            await db.query(
                """
                CREATE pr_review SET
                    owner = 'local',
                    repo = $repo,
                    pr_number = 0,
                    title = $title,
                    summary = $summary,
                    findings_count = $findings_count,
                    findings = $findings,
                    discipline_scores = $discipline_scores,
                    pass_quality_gate = $pass_quality_gate,
                    gate_failures = $gate_failures,
                    findings_by_severity = $findings_by_severity,
                    impact = $impact,
                    meta = { head_sha: $sha, branch: $branch },
                    reviewed_at = time::now()
                """,
                {
                    "repo": repo.name,
                    "title": f"{current_branch} \u2192 {base_branch}",
                    "summary": synthesis.summary,
                    "findings_count": len(synthesis.findings),
                    "findings": [f.model_dump() for f in synthesis.findings],
                    "discipline_scores": synthesis.discipline_scores,
                    "pass_quality_gate": synthesis.pass_quality_gate,
                    "gate_failures": synthesis.gate_failures,
                    "findings_by_severity": synthesis.findings_by_severity,
                    "impact": impact,
                    "sha": head_sha,
                    "branch": current_branch,
                },
            )
    except Exception as exc:
        logger.warning("Failed to persist local review: %s", exc)

    # Log results
    if synthesis.findings:
        logger.warning(
            "Review of %s: %d findings (%s)",
            current_branch,
            len(synthesis.findings),
            "GATE FAILED" if not synthesis.pass_quality_gate else "gate passed",
        )
    else:
        logger.info("Review of %s: clean — no issues found", current_branch)

    return {
        "branch": current_branch,
        "head_sha": head_sha,
        "findings_count": len(synthesis.findings),
        "pass_quality_gate": synthesis.pass_quality_gate,
        "summary": synthesis.summary,
        "discipline_scores": synthesis.discipline_scores,
    }
