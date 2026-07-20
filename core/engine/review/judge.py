# engine/review/judge.py
"""Judge agent — synthesizes findings from parallel review passes."""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict

from core.engine.core.config import settings
from core.engine.core.llm import llm
from core.engine.review.models import ReviewFinding, ReviewPass, ReviewSynthesis

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_PENALTY = {"critical": 0.4, "high": 0.2, "medium": 0.1, "low": 0.05}


class Judge:
    """Deduplicates, merges, and filters multi-pass review findings."""

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def group_findings(self, findings: list[ReviewFinding]) -> dict[tuple[str, int], list[ReviewFinding]]:
        """Group findings by (file, line) for deduplication."""
        groups: dict[tuple[str, int], list[ReviewFinding]] = defaultdict(list)
        for finding in findings:
            groups[(finding.file, finding.line)].append(finding)
        return groups

    def score_disciplines(self, passes: list[ReviewPass]) -> dict[str, float]:
        """Score each discipline 0.0-1.0. 1.0 = no issues. Penalise by severity."""
        scores: dict[str, float] = {}
        for rp in passes:
            penalty = sum(_PENALTY.get(f.severity, 0.0) for f in rp.findings)
            scores[rp.discipline] = max(0.0, min(1.0, 1.0 - penalty))
        return scores

    def check_quality_gate(
        self,
        findings: list[ReviewFinding],
        critical_threshold: int = 0,
        high_threshold: int = 3,
    ) -> ReviewSynthesis:
        """Return a ReviewSynthesis with gate pass/fail status populated."""
        by_severity: dict[str, int] = defaultdict(int)
        for f in findings:
            by_severity[f.severity] += 1

        gate_failures: list[str] = []
        critical_count = by_severity.get("critical", 0)
        high_count = by_severity.get("high", 0)

        if critical_count > critical_threshold:
            gate_failures.append(f"{critical_count} critical finding(s) found — threshold is {critical_threshold}")
        if high_count > high_threshold:
            gate_failures.append(f"{high_count} high-severity finding(s) found — threshold is {high_threshold}")

        return ReviewSynthesis(
            findings=findings,
            pass_quality_gate=len(gate_failures) == 0,
            gate_failures=gate_failures,
            findings_by_severity=dict(by_severity),
        )

    async def synthesize(self, passes: list[ReviewPass]) -> ReviewSynthesis:
        """Full synthesis: collect → judge → sort → score → gate → summarise."""
        all_findings: list[ReviewFinding] = [f for rp in passes for f in rp.findings]
        findings_before = len(all_findings)

        if not all_findings:
            return ReviewSynthesis(
                summary="No findings — all passes clean.",
                passes_run=len(passes),
                findings_before_judge=0,
                findings_after_judge=0,
                pass_quality_gate=True,
                discipline_scores=self.score_disciplines(passes),
            )

        # Get judge verdicts
        verdicts = await self._llm_judge(all_findings)

        # Apply verdicts
        kept: list[ReviewFinding] = []
        merged_indices: set[int] = set()

        for verdict in verdicts:
            idx = verdict.get("finding_index")
            action = verdict.get("action", "keep")
            if idx is None or idx >= len(all_findings):
                continue
            if action == "merge":
                merged_indices.add(idx)
            elif action == "discard":
                merged_indices.add(idx)  # treat discard as skip

        for i, finding in enumerate(all_findings):
            if i not in merged_indices:
                kept.append(finding)

        # Sort by severity (critical first)
        kept.sort(key=lambda f: _SEVERITY_ORDER.get(f.severity, 99))

        discipline_scores = self.score_disciplines(passes)
        gate_result = self.check_quality_gate(kept)
        summary = self._build_summary(kept, passes)

        return ReviewSynthesis(
            findings=kept,
            summary=summary,
            discipline_scores=discipline_scores,
            passes_run=len(passes),
            findings_before_judge=findings_before,
            findings_after_judge=len(kept),
            pass_quality_gate=gate_result.pass_quality_gate,
            gate_failures=gate_result.gate_failures,
            findings_by_severity=gate_result.findings_by_severity,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _llm_judge(self, findings: list[ReviewFinding]) -> list[dict]:
        """Ask the LLM to evaluate findings. Falls back to keep-all on failure."""
        if len(findings) <= 2:
            return [{"finding_index": i, "action": "keep"} for i in range(len(findings))]

        numbered = "\n".join(
            f"[{i}] ({f.severity}) {f.file}:{f.line} — {f.message} [discipline={f.discipline}, confidence={f.confidence}]"
            for i, f in enumerate(findings)
        )
        prompt = (
            "You are a senior code review judge. Evaluate the following findings and decide:\n"
            "- keep: finding is valid and actionable\n"
            "- merge: finding is a duplicate or subset of another (specify merged_with index)\n"
            "- discard: finding is noise, too low confidence, or not actionable\n\n"
            f"Findings:\n{numbered}\n\n"
            "Return a JSON array. Each element must have: finding_index (int), action (keep|merge|discard), "
            "and optionally merged_with (int) if action is merge.\n"
            "Return the JSON array only — no markdown, no explanation."
        )

        try:
            raw = await llm.complete(prompt, model=settings.llm_budget_model)
            return self._parse_verdicts(raw)
        except Exception as exc:
            logger.warning("Judge LLM call failed, keeping all findings: %s", exc)
            return [{"finding_index": i, "action": "keep"} for i in range(len(findings))]

    def _parse_verdicts(self, response: str) -> list[dict]:
        """Extract JSON array from LLM response."""
        text = response.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        # Try to extract the first JSON array using regex
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            text = match.group(0)
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            logger.warning("Failed to parse judge verdicts from: %.200s", response)
        return []

    def _build_summary(self, findings: list[ReviewFinding], passes: list[ReviewPass]) -> str:
        """Human-readable summary with finding counts by severity."""
        by_severity: dict[str, int] = defaultdict(int)
        for f in findings:
            by_severity[f.severity] += 1

        parts: list[str] = [f"Review complete — {len(passes)} pass(es), {len(findings)} finding(s)."]

        if findings:
            severity_parts = [
                f"{count} {sev}"
                for sev in ("critical", "high", "medium", "low")
                if (count := by_severity.get(sev, 0)) > 0
            ]
            parts.append("Severity breakdown: " + ", ".join(severity_parts) + ".")

        disciplines = [rp.discipline for rp in passes]
        if disciplines:
            parts.append("Disciplines reviewed: " + ", ".join(disciplines) + ".")

        return " ".join(parts)
