# engine/verification/models.py
"""Data models for Verification V2.

Shared across behavioral checks, honesty enforcement, and simplicity audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BehavioralEvidence:
    """A single behavioral check result for one criterion."""

    check_type: str  # "test_execution" | "code_inspection" | "integration_validation"
    status: str  # "passed" | "failed" | "skipped" | "error"
    details: dict  # check-type-specific structured data
    duration_ms: int = 0


@dataclass
class CheckResult:
    """All behavioral evidence for one acceptance criterion."""

    criterion_index: int
    criterion_text: str
    evidence: list[BehavioralEvidence] = field(default_factory=list)

    @property
    def has_hard_failures(self) -> bool:
        """Test execution failures are hard — code doesn't work."""
        return any(e.status == "failed" and e.check_type == "test_execution" for e in self.evidence)

    @property
    def has_soft_failures(self) -> bool:
        """Code inspection failures are soft — function may have been renamed."""
        return any(e.status == "failed" and e.check_type == "code_inspection" for e in self.evidence)


@dataclass
class PreCommitment:
    """Evaluator's pre-commitment before seeing evidence (anti-sycophancy)."""

    preliminary: str  # "likely_met" | "likely_not_met" | "uncertain"
    evidence_needed: str  # what the evaluator says it needs to confirm


@dataclass
class EnforcedVerdict:
    """Final verdict after honesty enforcement."""

    status: str  # "met" | "not_met" | "unclear"
    enforced: bool = False  # True if honesty enforcer overrode the LLM
    flagged: bool = False  # True if soft evidence contradicts verdict
    reason: str = ""  # why the enforcer intervened


def format_evidence(evidence: list[BehavioralEvidence]) -> str:
    """Format behavioral evidence for injection into LLM prompt."""
    if not evidence:
        return "No automated checks were run for this criterion."

    lines = []
    for e in evidence:
        icon = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP", "error": "ERR"}.get(e.status, "?")
        lines.append(f"[{icon}] {e.check_type}: {_summarize_details(e)}")

    return "\n".join(lines)


def _summarize_details(e: BehavioralEvidence) -> str:
    """Human-readable summary of check-specific details."""
    d = e.details

    if e.check_type == "test_execution":
        passed = d.get("tests_passed", 0)
        failed = d.get("tests_failed", 0)
        output = d.get("output", "")
        summary = f"{passed} passed, {failed} failed"
        if output:
            summary += f"\n  Output: {output[:500]}"
        return summary

    if e.check_type == "code_inspection":
        files = d.get("files_checked", [])
        found = [f for f in files if f.get("exists")]
        missing = [f for f in files if not f.get("exists")]
        parts = []
        if found:
            parts.append(f"{len(found)} file(s) exist")
        if missing:
            parts.append(f"{len(missing)} file(s) missing: {[f['file'] for f in missing]}")

        funcs_found = d.get("functions_found", [])
        funcs_missing = d.get("functions_missing", [])
        if funcs_found:
            parts.append(f"Functions found: {funcs_found}")
        if funcs_missing:
            parts.append(f"Functions missing: {funcs_missing}")

        return "; ".join(parts) if parts else "No files to check"

    if e.check_type == "integration_validation":
        points = d.get("points_checked", 0)
        valid = d.get("points_valid", 0)
        return f"{valid}/{points} integration points validated"

    return str(d)[:200]
