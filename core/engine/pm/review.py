# engine/pm/review.py
"""Multi-agent parallel review for work items.

Launches 5 independent LLM review calls via asyncio.gather, each evaluating
from a different angle. Issues are filtered by confidence threshold.
Critical issues block; major issues flag.

Review dimensions:
1. Spec compliance — did it meet requirements?
2. Intelligence compliance — follows conventions, avoids anti-patterns?
3. Error handling — silent failures, missing error paths?
4. Test coverage — missing tests, critical gaps?
5. Completeness — TODOs, incomplete work, placeholders?
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 80

REVIEW_DIMENSIONS = [
    "spec_compliance",
    "intelligence_compliance",
    "error_handling",
    "test_coverage",
    "completeness",
]


def _build_review_prompt(dimension: str, work_item: dict, initiative: dict, output: str) -> str:
    """Build dimension-specific review prompt."""
    wi_title = work_item.get("title", "")
    wi_desc = work_item.get("description", "")
    domain = work_item.get("domain_path", "")
    init_title = initiative.get("title", "")
    criteria = initiative.get("success_criteria", [])

    base = f"""You are a code reviewer evaluating a work item output.
Be precise. Only flag issues you're genuinely confident about (score 80+).

Work item: {wi_title}
Description: {wi_desc}
Domain: {domain}
Initiative: {init_title}

Output to review:
{output[:3000]}

"""

    prompts = {
        "spec_compliance": base
        + f"""Review for spec compliance.
Success criteria: {", ".join(criteria) if criteria else "N/A"}

Did the output meet the requirements? Check for missing features,
incorrect behavior, or deviation from the spec.
For each issue: {{"description": "...", "severity": "minor|major|critical", "confidence": 0-100}}
Return JSON: {{"issues": [...], "summary": "..."}}""",
        "intelligence_compliance": base
        + """Review against organizational intelligence.
Does the output follow known conventions? Does it avoid known anti-patterns?
Flag violations of best practices for this domain.
For each issue: {{"description": "...", "severity": "minor|major|critical", "confidence": 0-100}}
Return JSON: {{"issues": [...], "summary": "..."}}""",
        "error_handling": base
        + """Review error handling and failure modes.
Check for: silent failures, empty catch blocks, missing error logging,
inappropriate fallback behavior, unhandled edge cases, missing validation.
For each issue: {{"description": "...", "severity": "minor|major|critical", "confidence": 0-100}}
Return JSON: {{"issues": [...], "summary": "..."}}""",
        "test_coverage": base
        + """Review test coverage quality.
Check for: missing behavioral tests, critical untested paths,
test quality (are tests testing the right things?), edge cases, mocking quality.
For each issue: {{"description": "...", "severity": "minor|major|critical", "confidence": 0-100}}
Return JSON: {{"issues": [...], "summary": "..."}}""",
        "completeness": base
        + """Review for completeness.
Check for: TODO/FIXME/HACK comments left behind, incomplete implementations,
placeholder values, missing documentation, half-finished features.
For each issue: {{"description": "...", "severity": "minor|major|critical", "confidence": 0-100}}
Return JSON: {{"issues": [...], "summary": "..."}}""",
    }

    return prompts.get(dimension, base)


class WorkItemReviewer:
    """Multi-agent parallel reviewer for work items."""

    def __init__(self, llm=None, confidence_threshold: int = DEFAULT_CONFIDENCE_THRESHOLD):
        self._llm = llm
        self.confidence_threshold = confidence_threshold

    def _get_llm(self):
        if self._llm:
            return self._llm
        from core.engine.core.llm import llm

        return llm

    async def _review_dimension(
        self,
        dimension: str,
        work_item: dict,
        initiative: dict,
        output: str,
        product_id: str,
    ) -> dict:
        """Run a single review dimension."""
        prompt = _build_review_prompt(dimension, work_item, initiative, output)
        llm = self._get_llm()

        try:
            result = await llm.complete_json(prompt)
            issues = result.get("issues", [])
            summary = result.get("summary", "")
        except Exception as e:
            logger.warning("Review dimension '%s' failed: %s", dimension, e)
            issues = []
            summary = f"Review failed: {e}"

        return {
            "dimension": dimension,
            "issues": issues,
            "summary": summary,
        }

    async def review_work_item(
        self,
        work_item: dict,
        initiative: dict,
        output: str,
        product_id: str,
    ) -> dict:
        """Run all 5 review dimensions in parallel via asyncio.gather.

        Returns:
            {
                "passed": bool,
                "needs_attention": bool,
                "stages": [...],
                "all_issues": [...],
                "critical_count": int,
                "major_count": int,
            }
        """
        # Launch all 5 reviews in parallel
        stages = await asyncio.gather(
            *[self._review_dimension(dim, work_item, initiative, output, product_id) for dim in REVIEW_DIMENSIONS]
        )

        # Merge and filter issues by confidence
        all_issues = []
        for stage in stages:
            for issue in stage["issues"]:
                confidence = issue.get("confidence", 0)
                if confidence >= self.confidence_threshold:
                    issue["dimension"] = stage["dimension"]
                    all_issues.append(issue)

        # Categorize
        critical_issues = [i for i in all_issues if i.get("severity") == "critical"]
        major_issues = [i for i in all_issues if i.get("severity") == "major"]

        passed = len(critical_issues) == 0
        needs_attention = len(major_issues) > 0

        return {
            "passed": passed,
            "needs_attention": needs_attention,
            "stages": list(stages),
            "all_issues": all_issues,
            "critical_count": len(critical_issues),
            "major_count": len(major_issues),
        }
