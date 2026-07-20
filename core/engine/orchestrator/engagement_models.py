# engine/orchestrator/engagement_models.py
"""Pydantic models for multi-spin engagement orchestration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SpinOutput(BaseModel):
    """Structured output from a single perspective spin."""

    content: str
    handoff: str
    confidence: float
    open_questions: list[str] = []
    perspective: str
    specialties_used: list[str] = []


class EngagementResult(BaseModel):
    """Merged result from a multi-spin engagement."""

    spins: list[SpinOutput]
    merged_output: str
    perspectives_used: list[str]
    adversarial_resolution: str | None = None
    adversarial_diversity: float | None = None  # 0.0=identical, 1.0=completely different
    synthesis_skipped: bool = False  # True if adversarial spins agreed (adaptive termination)
    injected_perspectives: list[dict] = []
    engagement_rationale: str = ""
    # Verification gate results
    verified: bool = False
    verification_gaps: list[str] = []
    verification_verdict: Literal["clean", "gaps_found", "failed", "skipped"] = "skipped"
