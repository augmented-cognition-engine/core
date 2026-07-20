"""Sub-pillar escalation — defeats pillar-smearing.

If any contained discipline has (floor - score) > ESCALATION_THRESHOLD,
the discipline surfaces as a top-level recommendation past its parent pillar.
"""

from __future__ import annotations

from dataclasses import dataclass

ESCALATION_THRESHOLD = 0.3


@dataclass
class DisciplineSignal:
    pillar: str
    discipline: str
    score: float
    floor: float

    @property
    def gap(self) -> float:
        return max(0.0, self.floor - self.score)


def escalate_critical_disciplines(
    signals: list[DisciplineSignal],
) -> list[DisciplineSignal]:
    """Return disciplines whose gap exceeds ESCALATION_THRESHOLD."""
    return [s for s in signals if s.gap > ESCALATION_THRESHOLD]
