# engine/product/discovery_sprint.py
"""DiscoverySprintPackager — generates client-ready discovery sprint reports.

Orchestrates the full pipeline:
  scan_result + gaps_result + recommend_result + synthesis_result
  → DiscoveryReport (markdown + JSON)

Fallback: if synthesis_result is None, generates a preliminary report
from gaps + recommend only, marking it as preliminary.

Non-fatal on partial data: missing fields degrade output quality, not execution.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.engine.product.report_models import AutomationCandidate, DiscoveryReport, SpecStub

logger = logging.getLogger(__name__)

_EFFORT_TIER_MAP = {
    "low": "low",
    "medium": "medium",
    "high": "high",
}

# Default loaded hourly rate if not provided
_DEFAULT_HOURLY_RATE = 150.0

# Jargon → plain language replacements for executive summary
_JARGON_REPLACEMENTS = {
    "discipline": "area",
    "graph node": "component",
    "archetype": "pattern",
    "synthesis": "analysis",
}


class DiscoverySprintPackager:
    """Generates a DiscoveryReport from scan + gaps + recommend + synthesis outputs.

    Usage::

        packager = DiscoverySprintPackager()
        report = await packager.generate(
            product_id="product:acme",
            client_name="Acme Corp",
            scan_result=scan,
            gaps_result=gaps,
            recommend_result=recommend,
            synthesis_result=synthesis,  # pass None for preliminary
            loaded_hourly_rate=150.0,
        )
        markdown = report.to_markdown()
        json_str = report.to_json()
    """

    async def generate(
        self,
        product_id: str,
        client_name: str,
        scan_result: dict,
        gaps_result: list,
        recommend_result: list,
        synthesis_result: Optional[dict],
        loaded_hourly_rate: float = _DEFAULT_HOURLY_RATE,
    ) -> DiscoveryReport:
        """Generate a DiscoveryReport from discovery sprint outputs.

        Args:
            product_id: ACE product identifier for this client
            client_name: Human-readable client name (for the report header)
            scan_result: Output from ace_scan_repo
            gaps_result: Output from ace_gaps (list of gap dicts)
            recommend_result: Output from ace_recommend (list of recommendation dicts)
            synthesis_result: Output from Synthesizer (dict with leverage_points,
                              systems_map) — pass None for preliminary mode
            loaded_hourly_rate: Client's loaded hourly rate for ROI calculation

        Returns:
            DiscoveryReport ready for export as markdown or JSON
        """
        preliminary = synthesis_result is None

        automation_candidates = self._build_candidates(
            recommend_result=recommend_result,
            gaps_result=gaps_result,
            synthesis_result=synthesis_result,
            loaded_hourly_rate=loaded_hourly_rate,
        )

        executive_summary = self._build_exec_summary(
            client_name=client_name,
            candidates=automation_candidates,
            preliminary=preliminary,
        )

        systems_map_summary = self._build_systems_map_summary(
            synthesis_result=synthesis_result,
            scan_result=scan_result,
        )

        report = DiscoveryReport(
            product_id=product_id,
            client_name=client_name,
            executive_summary=executive_summary,
            automation_candidates=automation_candidates,
            systems_map_summary=systems_map_summary,
            preliminary=preliminary,
        )

        # Hard gate: exec summary must never contain technical jargon
        report.validate_exec_summary()

        return report

    # ── Private builders ──────────────────────────────────────────────────────

    def _build_candidates(
        self,
        recommend_result: list,
        gaps_result: list,
        synthesis_result: Optional[dict],
        loaded_hourly_rate: float,
    ) -> list[AutomationCandidate]:
        """Build up to 5 AutomationCandidates from recommendations."""
        candidates = []
        for rec in recommend_result[:5]:
            try:
                hours = float(rec.get("hours_per_week_saved", 2.0))
                effort = self._infer_effort(rec, gaps_result)
                stub = self._build_spec_stub(rec, gaps_result)

                candidates.append(
                    AutomationCandidate(
                        title=rec.get("title", "Automation opportunity"),
                        description=rec.get("rationale", ""),
                        hours_per_week_saved=hours,
                        loaded_hourly_rate=loaded_hourly_rate,
                        effort_tier=effort,
                        spec_stub=stub,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("Skipping malformed recommendation entry: %s", exc)

        return candidates

    def _infer_effort(self, rec: dict, gaps_result: list) -> str:
        """Infer effort tier from recommendation priority or gap severity."""
        priority = rec.get("priority", 2)
        if priority == 1:
            return "medium"
        elif priority <= 3:
            return "low"
        return "high"

    def _build_spec_stub(self, rec: dict, gaps_result: list) -> Optional[SpecStub]:
        """Build a SpecStub from a recommendation entry."""
        title = rec.get("title", "")
        if not title:
            return None

        # Build acceptance criteria from the recommendation rationale
        rationale = rec.get("rationale", "")
        criteria = [
            f"{title} is implemented and operational",
            f"Manual steps replaced: {rationale}" if rationale else "Manual process eliminated",
        ]

        # Infer scope from hours saved
        hours = float(rec.get("hours_per_week_saved", 2.0))
        if hours <= 2:
            scope = "low"
        elif hours <= 6:
            scope = "medium"
        else:
            scope = "high"

        try:
            return SpecStub(
                title=title,
                acceptance_criteria=criteria,
                estimated_scope=scope,
            )
        except ValueError:
            return None

    def _build_exec_summary(
        self,
        client_name: str,
        candidates: list[AutomationCandidate],
        preliminary: bool,
    ) -> str:
        """Build a plain-language executive summary (≤ 300 words, no jargon)."""
        if not candidates:
            return (
                f"{client_name} has several manual processes that are candidates for automation. "
                "A full analysis is needed to quantify the opportunity."
            )

        total_hours = sum(c.hours_per_week_saved for c in candidates)
        total_annual = sum(c.annual_value for c in candidates)
        top = candidates[0]

        prelim_note = " (preliminary estimate — full analysis pending)" if preliminary else ""

        summary = (
            f"{client_name} currently spends approximately {total_hours:.0f} hours per week "
            f"on manual operations that can be automated{prelim_note}. "
            f"The highest-priority opportunity is {top.title.lower()}, which alone recovers "
            f"{top.hours_per_week_saved:.0f} hours per week — worth "
            f"${top.annual_value:,.0f} annually at current staffing levels.\n\n"
            f"Across {len(candidates)} automation targets, the total recoverable value is "
            f"${total_annual:,.0f} per year. The recommended starting point is "
            f"{top.title.lower()} ({top.effort_tier} effort), which unblocks downstream "
            f"improvements and delivers the fastest return.\n\n"
            f"This report includes implementation-ready specs for each automation target. "
            f"Each spec defines what needs to be built and how to verify it's working."
        )

        return summary

    def _build_systems_map_summary(
        self,
        synthesis_result: Optional[dict],
        scan_result: dict,
    ) -> str:
        """Build a plain-language systems overview."""
        if synthesis_result:
            nodes = synthesis_result.get("systems_map", {}).get("nodes", [])
            if nodes:
                node_names = [n.get("discipline", "").replace("_", " ") for n in nodes[:5]]
                return (
                    f"Core systems identified: {', '.join(node_names)}. "
                    "Integration opportunities exist between these areas."
                )

        languages = scan_result.get("languages", [])
        total_files = scan_result.get("total_files", 0)
        lang_str = ", ".join(languages[:3]) if languages else "multiple languages"

        return (
            f"Codebase spans {total_files} files across {lang_str}. Full systems map available after complete analysis."
        )
