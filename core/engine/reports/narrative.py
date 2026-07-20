# engine/reports/narrative.py
"""NarrativeGenerator — LLM-writes plain-language sections for consulting reports."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are a consulting report writer. Return ONLY a valid JSON object — no markdown, no prose, no explanation.

Input data:
- Product: {product_name}
- Client: {client_name}
- Health (discipline: avg_score):
{health_summary}
- Top risks:
{risks_summary}
- Initiatives:
{initiatives_summary}

Return this exact JSON structure:
{{
  "executive_summary": "2-3 paragraphs of plain-English executive summary",
  "headline_findings": ["finding 1", "finding 2", "finding 3"],
  "risk_summaries": {{"capability_slug": "plain-language explanation"}},
  "recommendation_intro": "1 paragraph framing recommended actions"
}}

Rules:
- executive_summary: state what the product does, its current health, and the most urgent issue. No jargon.
- headline_findings: 3-4 crisp "so what" statements an executive can act on.
- risk_summaries: map each capability_slug from top risks to a 1-2 sentence business-impact explanation.
- recommendation_intro: frame the priority order and expected outcome.
- Output ONLY the JSON object. No text before or after."""


class NarrativeOutput(BaseModel):
    executive_summary: str
    headline_findings: list[str] = Field(default_factory=list)
    risk_summaries: dict[str, str] = Field(default_factory=dict)
    recommendation_intro: str = ""


_FALLBACK = NarrativeOutput(
    executive_summary=(
        "This report summarizes the technical health assessment findings for the product "
        "under review. Detailed scores and identified gaps are presented in the sections below."
    ),
    headline_findings=["See health scorecard for discipline scores", "Top risks are listed below"],
    risk_summaries={},
    recommendation_intro="The following actions are recommended based on the assessment findings.",
)


class NarrativeGenerator:
    async def generate(self, assembled: dict) -> dict:
        """Generate narrative sections. Returns fallback dict on any failure."""
        try:
            llm = get_llm()
            health_lines = [
                f"  - {d['discipline']}: {d['avg_score']:.0%} ({d['gap_count']} gaps)"
                for d in assembled.get("health_by_discipline", [])[:8]
            ]
            risk_lines = [
                f"  - [{r['severity'].upper()}] {r['discipline']} / {r['capability_slug']}: "
                f"{', '.join(r['gaps'][:2]) or 'score=' + str(r['score'])}"
                for r in assembled.get("top_risks", [])
            ]
            initiative_lines = [f"  - [{i['status']}] {i['title']}" for i in assembled.get("initiatives", [])[:5]]
            prompt = _PROMPT_TEMPLATE.format(
                product_name=assembled.get("product_name", ""),
                client_name=assembled.get("client_name", ""),
                health_summary="\n".join(health_lines) or "  (no data)",
                risks_summary="\n".join(risk_lines) or "  (no significant risks found)",
                initiatives_summary="\n".join(initiative_lines) or "  (none active)",
            )
            result: NarrativeOutput = await llm.complete_structured(prompt, schema=NarrativeOutput)
            return result.model_dump()
        except Exception as exc:
            logger.warning("NarrativeGenerator failed (non-fatal): %s", exc)
            return _FALLBACK.model_dump()
