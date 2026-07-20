# engine/review/models.py
"""Models for multi-pass code review."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewFinding(BaseModel):
    """A single finding from a review pass."""

    file: str
    line: int = 0
    message: str
    severity: str = "medium"  # critical | high | medium | low
    discipline: str = ""
    category: str = ""  # bug | security | performance | style | architecture | testing
    confidence: float = 0.8
    suggested_fix: str = ""


class ReviewPass(BaseModel):
    """Result of a single discipline-focused review pass."""

    discipline: str
    specialties: list[str] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)
    pass_summary: str = ""
    model_used: str = ""
    token_count: int = 0


class JudgeVerdict(BaseModel):
    """Judge agent's verdict on a finding — keep, merge, or discard."""

    finding_index: int
    action: str = "keep"  # keep | merge | discard
    reason: str = ""
    merged_with: int | None = None
    adjusted_severity: str | None = None


class ReviewSynthesis(BaseModel):
    """Final synthesized review after judge evaluation."""

    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str = ""
    discipline_scores: dict[str, float] = Field(default_factory=dict)
    passes_run: int = 0
    findings_before_judge: int = 0
    findings_after_judge: int = 0
    pass_quality_gate: bool = True
    gate_failures: list[str] = Field(default_factory=list)
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
