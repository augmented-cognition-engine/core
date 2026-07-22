# engine/foresight/models.py
"""Data models for the Foresight Engine — prediction, outcome, calibration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class CapabilityDelta:
    capability_id: str
    score_delta: float  # signed; e.g. +0.3 means predicted improvement
    confidence: float  # 0.0–1.0


@dataclass
class Prediction:
    horizon_days: int
    expected_changes: list[CapabilityDelta]
    primary_risk: str
    leading_indicators: list[str]
    falsification_condition: str


@dataclass
class PredictionOutcome:
    prediction_id: str
    archetype: str
    discipline: str
    calibration_score: float | None  # absent when the resolution is not eligible for scoring
    predicted_deltas: dict[str, float]  # capability_id -> predicted delta
    actual_deltas: dict[str, float]  # capability_id -> actual delta at close time
    resolution_state: str = "mixed"
    score_eligible: bool = True
    non_score_reason: str | None = None


@dataclass
class ArchetypeCalibration:
    archetype: str
    discipline: str
    calibration_score: float  # EMA (alpha=0.3) of prediction_outcome.calibration_score
    sample_count: int


@dataclass
class HypotheticalScore:
    gap_score: float  # 0.0–1.0; mean capability quality after override
    top_risks: list[str]  # capability IDs with score < 0.6, ascending by score
    capability_scores: dict[str, float]  # per-capability mean score after override applied


@dataclass
class RolloutBranch:
    path: list[str]  # decisions in order: [candidate, forced_1, forced_2]
    terminal_score: float  # gap_score from value_model at this terminal state
    top_risk: str  # primary risk for this branch (one sentence)
    state_override: dict[str, float]  # capability_id → predicted score at terminal state
    authored_by_archetype: str = ""  # which archetype "owns" this branch (assigned by planner)


@dataclass
class RolloutResult:
    candidate: str  # the candidate decision that was rolled out
    product_id: str
    branches: list[RolloutBranch]  # all scored branches (up to 3)
    best_path: list[str]  # path from branch with highest terminal_score
    created_at: str  # ISO timestamp — used for cache TTL checks


@dataclass
class Signal:
    id: str
    kind: str  # "capability_decline" | "gap_persistence" | "decision_velocity_drop"
    product_id: str
    subject: str  # capability_id, gap name, or "decisions" — what this signal is about
    description: str  # one-sentence human-readable summary
    confidence: float  # 0.0–1.0 — derived from data point count + magnitude
    trend_data: dict  # raw numbers behind the signal (e.g. {scores: [0.7, 0.6, 0.5], days: 7})
    created_at: str  # ISO timestamp


@dataclass
class ScenarioBranch:
    probability: float  # 0.0–1.0; all branches in a scenario must sum to ~1.0
    description: str  # one sentence: what this branch predicts
    implication_for_product: str  # one sentence: consequence for the product
    horizon: str  # "near_term" (days–2wk) | "medium_term" (weeks–months)


@dataclass
class Scenario:
    root_signal_id: str  # signal.id that triggered this scenario
    kind: str  # matches Signal.kind
    branches: list[ScenarioBranch]


@dataclass
class ScenarioConstraint:
    product_id: str
    description: str  # e.g. "capability:auth trending down — avoid expanding auth surface"
    affected_domains: list[str]  # capability slugs or discipline names
    source_scenario_id: str
    active: bool
    expires_at: str  # ISO timestamp


@dataclass
class SpeculativeDecision:
    product_id: str
    candidate: str  # candidate decision text that was explored but not selected
    branch_path: list[str]  # full rollout path (ordered decisions)
    terminal_score: float  # value model gap_score at terminal state
    # decision:trq7pplh37iyanbtzn7m — written as SurrealDB datetime
    # (time::now() + duration("7d")) so readers can filter with datetime objects.
    expires_at: datetime  # TTL 7 days
