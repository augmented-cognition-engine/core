# engine/review/engine.py
"""Multi-pass parallel discipline review engine."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from core.engine.core.config import settings
from core.engine.core.llm import llm
from core.engine.github.models import FileDiff, PRInfo
from core.engine.review.models import ReviewFinding, ReviewPass

logger = logging.getLogger(__name__)

# Patterns that map path fragments to disciplines
_PATH_DISCIPLINE_MAP: list[tuple[str, list[str]]] = [
    ("auth", ["security", "architecture"]),
    ("test", ["testing"]),
    ("api", ["api_design", "security"]),
    ("config", ["configuration", "security"]),
    ("deploy", ["deployment", "devops"]),
    ("migrat", ["data_modeling", "versioning"]),
    ("model", ["data_modeling", "architecture"]),
    ("log", ["observability"]),
    ("error", ["error_handling"]),
    ("perf", ["performance"]),
]

_BASE_DISCIPLINES = ["architecture", "security"]
_MAX_DISCIPLINES = 5


class ReviewEngine:
    """Run N discipline-specific review passes in parallel through the orchestrator."""

    def __init__(self, product_id: str = "product:platform") -> None:
        self.product_id = product_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_disciplines(self, files: list[FileDiff]) -> list[str]:
        """Select relevant disciplines based on changed file paths.

        Always includes 'architecture' and 'security'. Adds 'testing' if any
        non-test file changed. Caps the result at _MAX_DISCIPLINES.
        """
        disciplines: list[str] = list(_BASE_DISCIPLINES)

        paths_lower = [f.path.lower() for f in files]

        for fragment, mapped in _PATH_DISCIPLINE_MAP:
            if any(fragment in p for p in paths_lower):
                for d in mapped:
                    if d not in disciplines:
                        disciplines.append(d)

        # Add "testing" if any non-test file changed
        has_non_test = any("test" not in p for p in paths_lower)
        if has_non_test and "testing" not in disciplines:
            disciplines.append("testing")

        return disciplines[:_MAX_DISCIPLINES]

    def format_diff_context(self, files: list[FileDiff]) -> str:
        """Format file diffs into readable text for LLM context."""
        parts: list[str] = []
        for f in files:
            header = f"### {f.path}  [{f.status}]  +{f.additions} -{f.deletions}"
            parts.append(header)
            for hunk in f.hunks:
                hunk_header = f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
                if hunk.header:
                    hunk_header += f"  {hunk.header}"
                parts.append(hunk_header)
                parts.extend(hunk.lines)
            parts.append("")  # blank line between files
        return "\n".join(parts)

    async def run_passes(
        self,
        pr: PRInfo,
        files: list[FileDiff],
        disciplines: list[str] | None = None,
        file_contents: dict[str, str] | None = None,
    ) -> list[ReviewPass]:
        """Run parallel discipline-specific passes with asyncio.gather.

        Returns empty list if no files. Exceptions in individual passes are
        caught and logged rather than propagating.

        file_contents: optional mapping of file path → full file content.
        When provided, the security pass uses full content for taint analysis
        instead of diff-only pseudo-content.
        """
        if not files:
            return []

        if disciplines is None:
            disciplines = self.select_disciplines(files)

        diff_context = self.format_diff_context(files)

        tasks = [
            self._run_single_pass(pr, diff_context, d, files=files, file_contents=file_contents) for d in disciplines
        ]
        results: list[ReviewPass | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)

        passes: list[ReviewPass] = []
        for discipline, result in zip(disciplines, results):
            if isinstance(result, BaseException):
                logger.warning("Review pass failed for discipline=%s: %s", discipline, result)
            else:
                passes.append(result)
        return passes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_single_pass(
        self,
        pr: PRInfo,
        diff_context: str,
        discipline: str,
        files: list[FileDiff] | None = None,
        file_contents: dict[str, str] | None = None,
    ) -> ReviewPass:
        """Run one discipline review pass through the LLM."""
        intelligence_text = ""
        try:
            from core.engine.orchestrator.loader import load_intelligence

            intel: dict[str, Any] = await load_intelligence(discipline=discipline, product_id=self.product_id)
            if intel:
                insights = intel.get("insights", [])
                if insights:
                    intelligence_text = "Relevant best practices:\n" + "\n".join(
                        f"- {i.get('content', '')}" for i in insights[:5] if i
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not load intelligence for discipline=%s: %s", discipline, exc)

        taint_context = ""
        if discipline == "security" and files:
            try:
                from core.engine.review.taint import TaintAnalyzer

                analyzer = TaintAnalyzer()
                # Build analysis files: prefer full file_contents when available,
                # fall back to joining added lines from each diff hunk.
                analysis_files: list[dict] = []
                for f in files:
                    if file_contents and f.path in file_contents:
                        content = file_contents[f.path]
                    else:
                        # Best-effort: reconstruct pseudo file content from diff added lines
                        added_lines = [
                            line[1:]  # strip the leading "+"
                            for hunk in f.hunks
                            for line in hunk.lines
                            if line.startswith("+")
                        ]
                        content = "\n".join(added_lines)
                    analysis_files.append({"path": f.path, "content": content, "language": f.language})

                report = analyzer.analyze_diff_files(analysis_files)
                if report.flows:
                    taint_lines = [
                        "\n## Taint / Data Flow Analysis (automated)",
                        f"Detected {len(report.flows)} potential data flow(s) "
                        f"({report.sources_found} source(s), {report.sinks_found} sink(s)):",
                    ]
                    for flow in report.flows[:10]:
                        taint_lines.append(f"- [{flow.severity.upper()}] {flow.flow_type}: {flow.description}")
                    taint_context = "\n".join(taint_lines)
                elif report.sources_found or report.sinks_found:
                    taint_context = (
                        f"\n## Taint / Data Flow Analysis (automated)\n"
                        f"Found {report.sources_found} taint source(s) and "
                        f"{report.sinks_found} sink(s) — no direct flows detected in changed lines."
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Taint analysis failed for security pass: %s", exc)

        prompt = _build_prompt(pr, diff_context, discipline, intelligence_text, taint_context)

        response = await llm.complete(
            prompt=prompt,
            model=settings.llm_budget_model,
            max_tokens=2048,
        )

        findings = _parse_findings(response, discipline)
        summary = _extract_summary(response)

        return ReviewPass(
            discipline=discipline,
            findings=findings,
            pass_summary=summary,
            model_used=settings.llm_budget_model,
        )


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _build_prompt(
    pr: PRInfo,
    diff_context: str,
    discipline: str,
    intelligence_text: str,
    taint_context: str = "",
) -> str:
    """Build the review prompt for a single discipline pass."""
    intel_section = f"\n\n{intelligence_text}" if intelligence_text else ""
    taint_section = f"\n{taint_context}" if taint_context else ""

    return (
        f"You are a senior engineer reviewing a pull request from the perspective of **{discipline}** only.\n"
        f"Do NOT comment on concerns outside this discipline.\n"
        f"\n"
        f"## Pull Request\n"
        f"Title: {pr.title}\n"
        f"Author: {pr.author}\n"
        f"Branch: {pr.head_branch} → {pr.base_branch}\n"
        f"Description: {pr.body or '(none)'}\n"
        f"{intel_section}"
        f"{taint_section}\n"
        f"\n"
        f"## Diff\n"
        f"```diff\n"
        f"{diff_context}\n"
        f"```\n"
        f"\n"
        f"Review the diff and return ONLY valid JSON in this exact format:\n"
        f'{{"findings": [{{"file": "path", "line": 0, "message": "issue description", '
        f'"severity": "high|medium|low|critical", "discipline": "{discipline}", '
        f'"category": "bug|security|performance|style|architecture|testing", '
        f'"confidence": 0.8, "suggested_fix": "optional fix"}}], '
        f'"summary": "1-2 sentence summary of {discipline} concerns"}}\n'
        f"\n"
        f"If there are no findings, return an empty findings array. No markdown fences."
    )


def _parse_findings(response: str, discipline: str) -> list[ReviewFinding]:
    """Extract findings from the LLM JSON response."""
    text = response.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
        inner = [line for line in lines if not line.startswith("```")]
        text = "\n".join(inner).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract a JSON object from somewhere in the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                logger.warning("Could not parse JSON findings for discipline=%s", discipline)
                return []
        else:
            return []

    raw_findings = data.get("findings", [])
    findings: list[ReviewFinding] = []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        try:
            findings.append(ReviewFinding(**item))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping malformed finding: %s — %s", item, exc)
    return findings


def _extract_summary(response: str) -> str:
    """Extract the summary field from the LLM JSON response."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = [line for line in lines if not line.startswith("```")]
        text = "\n".join(inner).strip()

    try:
        data = json.loads(text)
        return data.get("summary", "")
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end])
                return data.get("summary", "")
            except json.JSONDecodeError:
                pass
    return ""
