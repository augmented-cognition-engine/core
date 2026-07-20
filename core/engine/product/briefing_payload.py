"""BriefingPayload — structured contract between this spec and the Voice Rendering spec.

This spec produces the data; the voice spec produces the prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.engine.product.ambition import DemoTarget
from core.engine.product.strategic_prioritizer import RankedRecommendation
from core.engine.product.uncertainty import UncertaintyQuery


@dataclass
class StateChange:
    kind: str
    description: str
    at: datetime
    target_ref: Optional[str] = None


@dataclass
class Action:
    actor: str
    action: str
    target: str
    at: datetime


@dataclass
class TargetDriftAssessment:
    n_total: int
    n_blocked: int
    blocking_pillars: list[str]


@dataclass
class BriefingPayload:
    product_id: str
    timestamp: datetime
    current_phase: str
    days_in_phase: int
    next_phase: Optional[str]
    phase_floors: dict[str, float]
    demo_target: Optional[DemoTarget]
    target_drift_assessment: Optional["TargetDriftAssessment"]
    pillar_scores: dict[str, float]
    discipline_breakdown: dict[str, dict[str, float]]
    sensor_coverage: dict[str, bool]
    top_recommendations: list[RankedRecommendation]
    blocked_patterns: list[str]
    open_uncertainty_queries: list[UncertaintyQuery]
    recent_state_changes: list[StateChange] = field(default_factory=list)
    contributor_activity: dict[str, list[Action]] = field(default_factory=dict)
    # GraphRAG community summaries — the largest knowledge communities (theme + member count), so the
    # briefing shows the SHAPE of accumulated knowledge. Written by the community_summarizer engine.
    community_summaries: list[str] = field(default_factory=list)
