"""Proactive Line data model — the single ranked surface ACE initiates from."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class ProactiveSource(str, Enum):
    UNRESOLVED_GATE = "unresolved_gate"
    SENTINEL_FINDING = "sentinel_finding"
    SENTINEL = "sentinel"  # alias for voice stream emitters
    RECOMMENDED_ACTION = "recommended_action"
    BRIEFING_HIGHLIGHT = "briefing_highlight"
    DECISION_CONFLICT = "decision_conflict"
    FORESIGHT_SIGNAL = "foresight_signal"


# Rank order — lower index = higher priority
_SOURCE_RANK: dict[ProactiveSource, int] = {
    ProactiveSource.UNRESOLVED_GATE: 0,
    ProactiveSource.SENTINEL_FINDING: 1,
    ProactiveSource.DECISION_CONFLICT: 2,
    ProactiveSource.FORESIGHT_SIGNAL: 3,
    ProactiveSource.RECOMMENDED_ACTION: 4,
    ProactiveSource.BRIEFING_HIGHLIGHT: 5,
}


class ProactiveLine(BaseModel):
    product_id: str
    line: str  # colleague-voice prose, 1 sentence ≤ 150 chars
    source: ProactiveSource
    source_artifact_id: str  # gate id, finding id, capability id, etc.
    drill_down_url: str  # route that displays the source artifact
    severity: float  # 0..1, used by ranker
    generated_at: datetime
    priority: Literal["HIGH", "MEDIUM", "LOW"] | None = None
    topic: str | None = None  # dedup key: topic-per-day gate in voice stream

    def rank_key(self) -> tuple[int, float]:
        """Lower = higher priority. Sort ascending."""
        tier = _SOURCE_RANK.get(self.source, 99)
        return (tier, -self.severity)  # within tier, higher severity wins
