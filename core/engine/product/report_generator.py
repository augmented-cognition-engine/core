# engine/product/report_generator.py
"""ReportGenerator — renders DiscoveryReport as markdown or JSON.

Markdown output renders cleanly in Notion, Google Docs, and email.
Two-layer structure: executive summary (non-technical) + technical detail.
"""

from __future__ import annotations

import json

from core.engine.product.report_models import DiscoveryReport


class ReportGenerator:
    """Render a DiscoveryReport to markdown or JSON.

    Usage::

        generator = ReportGenerator(report)
        md = generator.to_markdown()
        raw = generator.to_json()
    """

    def __init__(self, report: DiscoveryReport) -> None:
        self._report = report

    def to_json(self) -> str:
        return json.dumps(self._report.to_dict(), ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        r = self._report
        sections = [self._header(r)]

        if r.preliminary:
            sections.append(
                "> **Note:** This is a preliminary report — full synthesis analysis pending. "
                "Automation estimates are based on gaps and recommendations only."
            )
            sections.append("")

        sections.append(self._exec_summary(r))
        sections.append(self._automation_candidates(r))
        sections.append(self._systems_overview(r))
        sections.append(self._next_steps(r))

        return "\n".join(sections)

    # ── Section renderers ─────────────────────────────────────────────────────

    def _header(self, r: DiscoveryReport) -> str:
        return f"# Discovery Sprint Report — {r.client_name}\n"

    def _exec_summary(self, r: DiscoveryReport) -> str:
        lines = ["## Executive Summary", ""]
        lines.append(r.executive_summary)
        lines.append("")
        return "\n".join(lines)

    def _automation_candidates(self, r: DiscoveryReport) -> str:
        if not r.automation_candidates:
            return "## Automation Opportunities\n\n_No automation candidates identified._\n"

        lines = ["## Automation Opportunities", ""]
        lines.append("| # | Automation | Hours/Week Saved | Annual Value | Effort |")
        lines.append("|---|-----------|-----------------|-------------|--------|")

        for i, c in enumerate(r.automation_candidates[:5], 1):
            annual = f"${c.annual_value:,.0f}"
            lines.append(
                f"| {i} | {c.title} | {c.hours_per_week_saved:.1f}h | {annual} | {c.effort_tier.capitalize()} |"
            )
        lines.append("")

        # Detail blocks for each candidate
        for i, c in enumerate(r.automation_candidates[:5], 1):
            lines.append(f"### {i}. {c.title}")
            lines.append("")
            lines.append(c.description)
            lines.append("")
            annual = f"${c.annual_value:,.0f}"
            lines.append(
                f"**ROI:** {c.hours_per_week_saved:.1f} hours/week × "
                f"${c.loaded_hourly_rate:.0f}/hr × 52 weeks = **{annual}/year**"
            )
            lines.append(f"**Effort:** {c.effort_tier.capitalize()}")
            if c.spec_stub:
                lines.append("")
                lines.append("**Acceptance Criteria:**")
                for criterion in c.spec_stub.acceptance_criteria:
                    lines.append(f"- {criterion}")
            lines.append("")

        return "\n".join(lines)

    def _systems_overview(self, r: DiscoveryReport) -> str:
        lines = ["## Systems Overview", ""]
        lines.append(r.systems_map_summary)
        lines.append("")
        return "\n".join(lines)

    def _next_steps(self, r: DiscoveryReport) -> str:
        lines = ["## Recommended Next Steps", ""]
        if r.automation_candidates:
            top = r.automation_candidates[0]
            lines.append(f"1. **Start with:** {top.title} ({top.effort_tier} effort, highest ROI)")
        lines.append("2. **Scope review:** Review each automation candidate with your team")
        lines.append("3. **Engagement kickoff:** Begin full implementation engagement")
        lines.append("")
        return "\n".join(lines)
