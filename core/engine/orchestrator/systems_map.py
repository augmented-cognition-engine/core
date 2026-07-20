# engine/orchestrator/systems_map.py
"""Data models for the Synthesizer layer.

SystemsMap     — topology of discipline nodes and implication edges
CrossImplicationChain — a root finding cascading through disciplines
LeveragePoint  — ranked intervention with highest cascade effect
SynthesisResult — complete output of a synthesis pass
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List


@dataclass
class SystemsMapNode:
    """A discipline node in the systems map."""

    discipline: str
    score: float
    key_findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "discipline": self.discipline,
            "score": self.score,
            "key_findings": self.key_findings,
        }


@dataclass
class SystemsMapEdge:
    """A directed implication edge between two discipline nodes."""

    from_discipline: str
    to_discipline: str
    implication: str
    weight: float

    def to_dict(self) -> dict:
        return {
            "from_discipline": self.from_discipline,
            "to_discipline": self.to_discipline,
            "implication": self.implication,
            "weight": self.weight,
        }


@dataclass
class SystemsMap:
    """Topology of the system: discipline nodes + implication edges."""

    nodes: List[SystemsMapNode]
    edges: List[SystemsMapEdge]
    task_description: str

    def to_dict(self) -> dict:
        return {
            "task_description": self.task_description,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class ImplicationLink:
    """A single step in a cross-discipline implication chain."""

    discipline: str
    finding: str
    severity: str  # "critical" | "high" | "medium" | "low"

    def to_dict(self) -> dict:
        return {
            "discipline": self.discipline,
            "finding": self.finding,
            "severity": self.severity,
        }


@dataclass
class CrossImplicationChain:
    """A root finding that cascades through multiple disciplines.

    Example: data_modeling (no encryption)
      → security (PII exposed)
        → compliance (GDPR gap)
          → deployment (no encryption-at-rest config)
    """

    root_discipline: str
    root_finding: str
    chain: List[ImplicationLink] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return len(self.chain)

    def to_dict(self) -> dict:
        return {
            "root_discipline": self.root_discipline,
            "root_finding": self.root_finding,
            "depth": self.depth,
            "chain": [link.to_dict() for link in self.chain],
        }


@dataclass
class LeveragePoint:
    """A ranked intervention with the highest cascade effect across disciplines."""

    rank: int
    discipline: str
    intervention: str
    impact_score: float
    affected_dimensions: List[str]
    cascade_description: str

    def __post_init__(self) -> None:
        if self.rank not in (1, 2, 3):
            raise ValueError(f"LeveragePoint rank must be 1, 2, or 3 — got {self.rank!r}")
        if not (0.0 <= self.impact_score <= 1.0):
            raise ValueError(f"LeveragePoint impact_score must be in [0.0, 1.0] — got {self.impact_score!r}")

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "discipline": self.discipline,
            "intervention": self.intervention,
            "impact_score": self.impact_score,
            "affected_dimensions": self.affected_dimensions,
            "cascade_description": self.cascade_description,
        }


@dataclass
class ProjectionStep:
    """A single step in a forward projection — what the system looks like at step N."""

    step: int
    state: str
    key_change: str

    def to_dict(self) -> dict:
        return {"step": self.step, "state": self.state, "key_change": self.key_change}


@dataclass
class ForwardProjection:
    """Projection of system state N steps forward if a leverage point is applied.

    Example: apply "add auth middleware" (rank 1) →
      step 1: JWT gate active
      step 2: audit trail flowing
      step 3: SOC2 certification eligible
    """

    leverage_point_rank: int
    steps: List[ProjectionStep]
    projected_outcome: str

    def to_dict(self) -> dict:
        return {
            "leverage_point_rank": self.leverage_point_rank,
            "steps": [s.to_dict() for s in self.steps],
            "projected_outcome": self.projected_outcome,
        }


_VALID_LOOP_TYPES = {"reinforcing", "balancing"}


@dataclass
class FeedbackLoop:
    """A detected feedback loop in the systems map.

    Reinforcing loops amplify change (virtuous or vicious cycles).
    Balancing loops resist change (stabilising or oscillating).
    """

    loop_type: str  # "reinforcing" | "balancing"
    disciplines: List[str]
    description: str
    net_effect: str  # e.g. "amplifying", "stabilizing", "oscillating"

    def __post_init__(self) -> None:
        if self.loop_type not in _VALID_LOOP_TYPES:
            raise ValueError(
                f"FeedbackLoop loop_type must be one of {sorted(_VALID_LOOP_TYPES)!r} — got {self.loop_type!r}"
            )

    def to_dict(self) -> dict:
        return {
            "loop_type": self.loop_type,
            "disciplines": self.disciplines,
            "description": self.description,
            "net_effect": self.net_effect,
        }


@dataclass
class CascadeFailurePath:
    """The failure chain that results if a critical intervention is NOT addressed.

    blast_radius is computed from cascade_sequence length — not stored separately.
    """

    failure_origin: str
    discipline: str
    cascade_sequence: List[str]

    @property
    def blast_radius(self) -> int:
        return len(self.cascade_sequence)

    def to_dict(self) -> dict:
        return {
            "failure_origin": self.failure_origin,
            "discipline": self.discipline,
            "cascade_sequence": self.cascade_sequence,
            "blast_radius": self.blast_radius,
        }


_VALID_REVERSIBILITY = {"reversible", "partially_reversible", "irreversible"}


@dataclass
class TradeOff:
    """Explicit gains and costs of applying a leverage point intervention."""

    leverage_point_rank: int
    intervention: str
    gains: List[str]
    costs: List[str]
    reversibility: str  # "reversible" | "partially_reversible" | "irreversible"

    def __post_init__(self) -> None:
        if self.reversibility not in _VALID_REVERSIBILITY:
            raise ValueError(
                f"TradeOff reversibility must be one of {sorted(_VALID_REVERSIBILITY)!r} — got {self.reversibility!r}"
            )

    def to_dict(self) -> dict:
        return {
            "leverage_point_rank": self.leverage_point_rank,
            "intervention": self.intervention,
            "gains": self.gains,
            "costs": self.costs,
            "reversibility": self.reversibility,
        }


@dataclass
class SynthesisResult:
    """Complete output of a synthesis pass over a task result."""

    cross_implication_chains: List[CrossImplicationChain]
    leverage_points: List[LeveragePoint]
    systems_map: SystemsMap
    synthesis_duration_ms: float
    # P3 — Systems Design Depth (default to empty for backward compatibility)
    forward_projections: List[ForwardProjection] = field(default_factory=list)
    feedback_loops: List[FeedbackLoop] = field(default_factory=list)
    cascade_failure_paths: List[CascadeFailurePath] = field(default_factory=list)
    trade_offs: List[TradeOff] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cross_implication_chains": [c.to_dict() for c in self.cross_implication_chains],
            "leverage_points": [lp.to_dict() for lp in self.leverage_points],
            "systems_map": self.systems_map.to_dict(),
            "synthesis_duration_ms": self.synthesis_duration_ms,
            "forward_projections": [fp.to_dict() for fp in self.forward_projections],
            "feedback_loops": [fl.to_dict() for fl in self.feedback_loops],
            "cascade_failure_paths": [cp.to_dict() for cp in self.cascade_failure_paths],
            "trade_offs": [t.to_dict() for t in self.trade_offs],
        }
