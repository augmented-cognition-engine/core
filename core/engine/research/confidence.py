"""Confidence model — maps source quality class + corroboration to a score.

Score formula:
  REFERENCE + corroboration≥2 → HIGH   (0.9, 30 days)
  REFERENCE alone             → MEDIUM_HIGH (0.75, 30 days)
  EXEMPLAR + corroboration≥3  → MEDIUM_HIGH (0.75, 14 days)
  EXEMPLAR alone/low          → MEDIUM (0.6, 14 days)
  SIGNAL + corroboration≥2    → MEDIUM (0.5, 7 days)
  SIGNAL alone                → LOW, flagged (0.3, 3 days)
  NOISE                       → 0.0, flagged (don't write to graph)
"""

from __future__ import annotations

from dataclasses import dataclass

from core.engine.research.source_registry import SourceClass


@dataclass
class ConfidenceScore:
    value: float  # 0.0 – 1.0
    tier: str  # "high" | "medium_high" | "medium" | "low" | "noise"
    decay_days: int  # days until confidence should be re-evaluated
    flagged: bool  # True → needs human review before acting on

    def __str__(self) -> str:
        flag = " [flagged]" if self.flagged else ""
        return f"{self.tier} ({self.value:.2f}){flag}"


def compute_confidence(
    source_class: SourceClass,
    corroboration_count: int = 1,
) -> ConfidenceScore:
    """Compute confidence from source quality class and corroboration count."""
    if source_class == SourceClass.NOISE:
        return ConfidenceScore(value=0.0, tier="noise", decay_days=0, flagged=True)

    if source_class == SourceClass.REFERENCE:
        if corroboration_count >= 2:
            return ConfidenceScore(value=0.9, tier="high", decay_days=30, flagged=False)
        return ConfidenceScore(value=0.75, tier="medium_high", decay_days=30, flagged=False)

    if source_class == SourceClass.EXEMPLAR:
        if corroboration_count >= 3:
            return ConfidenceScore(value=0.75, tier="medium_high", decay_days=14, flagged=False)
        return ConfidenceScore(value=0.6, tier="medium", decay_days=14, flagged=False)

    # SIGNAL
    if corroboration_count >= 2:
        return ConfidenceScore(value=0.5, tier="medium", decay_days=7, flagged=False)
    return ConfidenceScore(value=0.3, tier="low", decay_days=3, flagged=True)
