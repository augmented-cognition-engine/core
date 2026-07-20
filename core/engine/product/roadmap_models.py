"""The Living Roadmap data shapes — a computed projection, never hand-edited."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

LANES = ("now", "review", "next", "blocked", "parked", "done")


class RoadmapStaleness(str, Enum):
    FRESH = "fresh"
    DECAYED = "decayed"  # recommendation_decay pushed it down
    SUPERSEDED = "superseded"  # a decision/spec reverts/supersedes it (Graph Tensions)


@dataclass
class RoadmapItem:
    title: str
    pillar: str
    discipline: str | None
    capability_slug: str = ""  # the capability the gap belongs to (spec lookup key)
    gap: float = 0.0
    rank: float = 0.0
    rationale: str = ""
    blocking_patterns: list[str] = field(default_factory=list)
    spec_status: str | None = None  # None | draft | building | shipped | superseded
    staleness: RoadmapStaleness = RoadmapStaleness.FRESH
    lane: str = "next"
    cbt: int = 0  # consecutive_briefings_at_top (for decay)
    kind: str = "gap"  # "gap" | "spec" | "phase"
    source_ref: str | None = None  # provenance: which doc this item came from


@dataclass
class Roadmap:
    product_id: str
    lanes: dict[str, list[RoadmapItem]] = field(default_factory=dict)
    ambition_summary: str = ""
