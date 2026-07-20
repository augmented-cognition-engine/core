"""Committee orchestration pattern — extends team with influence DAG + two-pass.

Pass 1: parallel reads (delegated to team pattern).
Pass 2: adversarial veto by gating seats (delegated to adversarial pattern).

Both passes are delegated to the existing team and adversarial patterns; this
pattern enforces the sequencing on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.engine.orchestration.patterns.base import PatternConfig, PatternResult, PatternStrategy


@dataclass
class CommitteeConfig(PatternConfig):
    seats: list[Any] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)

    def __init__(self, seats=None, sentences=None, **kwargs):
        """Allow simpler construction for unit tests."""
        super().__init__(
            run_id=kwargs.get("run_id", "test-run"),
            product_id=kwargs.get("product_id", "test-product"),
            **{k: v for k, v in kwargs.items() if k not in ("run_id", "product_id")},
        )
        self.seats = seats or []
        self.sentences = sentences or []


def _run_team(seats, sentences) -> dict:
    """Indirection so tests can monkeypatch. Production wires to team pattern
    (filled in by Task 17 integration)."""
    return {"reads": []}


def _run_adversarial(gating_seats, sentences, pass1_reads) -> dict:
    """Indirection so tests can monkeypatch. Production wires to adversarial
    pattern (filled in by Task 17 integration)."""
    return {"vetoes": []}


class CommitteePattern(PatternStrategy):
    def __init__(self):
        """Simplified constructor for unit testing. Production version will accept
        bus and factory parameters."""
        pass

    @property
    def name(self) -> str:
        return "committee"

    def execute(self, config: CommitteeConfig) -> PatternResult:
        pass1 = _run_team(config.seats, config.sentences)
        gating = [s for s in (config.seats or []) if getattr(s, "is_gating", False)]
        pass2 = _run_adversarial(gating, config.sentences, pass1["reads"])
        return PatternResult(
            run_id=getattr(config, "run_id", "test"),
            pattern_name="committee",
            status="completed",
            output={"pass1": pass1, "pass2": pass2},
        )
