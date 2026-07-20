"""Insight attribution — structural and LLM-based.

Determines which injected intelligence insights actually influenced an LLM output.
Two passes:
  1. Structural: explicit [I-N] marker references + keyword fingerprinting
  2. LLM (optional, Haiku): ask the model which insight IDs shaped the response
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Minimum keyword length for fingerprinting — avoids noise from common short words
_MIN_KEYWORD_LEN = 4

# Weight values per insight_type
_WEIGHTS = {
    "correction": 5,
    "pattern": 2,
    "convention": 2,
    "preference": 2,
}
_DEFAULT_WEIGHT = 1

# Threshold: insights must compose at least this fraction of context to warrant LLM attribution
_MIN_CONTEXT_RATIO = 0.05


@dataclass
class AttributionResult:
    """Result of an attribution pass."""

    attributed_ids: list[str]
    method: str  # "structural" or "llm"
    injected_count: int
    weights: dict[str, int] = field(default_factory=dict)

    @property
    def utilization_rate(self) -> float:
        """Fraction of injected insights that were attributed."""
        if self.injected_count == 0:
            return 0.0
        return len(self.attributed_ids) / self.injected_count

    @property
    def weighted_score(self) -> int:
        """Sum of weights for all attributed insights."""
        return sum(self.weights.values())


def _extract_keywords(content: str) -> set[str]:
    """Extract significant words (≥ _MIN_KEYWORD_LEN chars) from insight content."""
    words = re.findall(r"\b\w+\b", content.lower())
    return {w for w in words if len(w) >= _MIN_KEYWORD_LEN}


def attribute_structural(
    output: str,
    marker_map: dict[str, str],
    injected_insights: list[dict],
) -> AttributionResult:
    """Structural attribution: explicit markers + keyword fingerprinting.

    Pass 1: Find [I-N] marker references explicitly in output.
    Pass 2: For markers not found, check if significant keywords from insight
            content appear in the output.

    Returns AttributionResult with method="structural".
    """
    if not output:
        return AttributionResult(
            attributed_ids=[],
            method="structural",
            injected_count=len(injected_insights),
        )

    attributed: set[str] = set()
    output_lower = output.lower()

    # Build lookup: insight_id -> insight dict
    insight_lookup: dict[str, dict] = {str(ins.get("id", "")): ins for ins in injected_insights}

    # Pass 1: Explicit [I-N] markers in output
    for marker, insight_id in marker_map.items():
        if marker in output:
            attributed.add(insight_id)

    # Pass 2: Keyword fingerprinting for all insights (not just unmatched ones)
    # This catches cases where the model paraphrased the insight without citing the marker
    for insight_id, ins in insight_lookup.items():
        if insight_id in attributed:
            continue  # already matched
        content = ins.get("content", "")
        if not content:
            continue
        keywords = _extract_keywords(content)
        # Require at least 2 keyword matches to avoid false positives
        matches = sum(1 for kw in keywords if kw in output_lower)
        if matches >= 2:
            attributed.add(insight_id)

    return AttributionResult(
        attributed_ids=list(attributed),
        method="structural",
        injected_count=len(injected_insights),
    )


async def attribute_llm(
    output: str,
    marker_map: dict[str, str],
    injected_insights: list[dict],
    llm,
) -> AttributionResult:
    """LLM-based attribution using Haiku.

    Asks the model which insight IDs (from the marker_map values) influenced the output.
    Returns a JSON array of insight IDs. Falls back to empty list on any error.
    """
    if not output or not marker_map:
        return AttributionResult(
            attributed_ids=[],
            method="llm",
            injected_count=len(injected_insights),
        )

    # Build summary of injected insights with their marker labels
    insight_summary_lines = []
    for marker, insight_id in marker_map.items():
        # Find content for this insight
        content = ""
        for ins in injected_insights:
            if str(ins.get("id", "")) == insight_id:
                content = ins.get("content", "")[:100]
                break
        insight_summary_lines.append(f"{marker} ({insight_id}): {content}")

    insight_summary = "\n".join(insight_summary_lines)

    prompt = (
        f"The following insights were injected into context before generating this output:\n\n"
        f"{insight_summary}\n\n"
        f"Output:\n{output[:1500]}\n\n"
        f"Which insight IDs (e.g. 'insight:abc') directly influenced this output? "
        f"Return a JSON array of insight ID strings only. If none, return []."
    )

    try:
        result = await llm.complete_json(prompt)
        if isinstance(result, list):
            attributed = [str(r) for r in result if isinstance(r, str)]
        elif isinstance(result, dict) and "ids" in result:
            attributed = [str(r) for r in result["ids"] if isinstance(r, str)]
        else:
            attributed = []
    except Exception as exc:
        logger.warning("LLM attribution failed (non-fatal): %s", exc)
        attributed = []

    return AttributionResult(
        attributed_ids=attributed,
        method="llm",
        injected_count=len(injected_insights),
    )


def should_run_llm_attribution(
    structural_attributed: list[str],
    injected_count: int,
    context_ratio: float,
) -> bool:
    """Decide whether to run the more expensive LLM attribution pass.

    Only runs when:
    - Structural found nothing (no explicit markers, no keyword matches)
    - Insights were actually injected (injected_count > 0)
    - Insights composed a meaningful fraction of context (context_ratio >= 0.05)
    """
    if structural_attributed:
        return False
    if injected_count == 0:
        return False
    if context_ratio < _MIN_CONTEXT_RATIO:
        return False
    return True


def weight_attributions(
    attributed_ids: list[str],
    injected_insights: list[dict],
    output: str,
) -> dict[str, int]:
    """Assign value weights to attributed insights.

    Weights reflect the impact type:
    - correction: 5 (mistake prevented — highest value)
    - pattern/convention/preference: 2 (established knowledge reused)
    - other: 1

    Returns dict of {insight_id: weight} only for attributed insights.
    """
    if not attributed_ids:
        return {}

    insight_lookup: dict[str, dict] = {str(ins.get("id", "")): ins for ins in injected_insights}
    weights: dict[str, int] = {}

    for insight_id in attributed_ids:
        ins = insight_lookup.get(insight_id, {})
        insight_type = ins.get("insight_type", "")
        weights[insight_id] = _WEIGHTS.get(insight_type, _DEFAULT_WEIGHT)

    return weights
