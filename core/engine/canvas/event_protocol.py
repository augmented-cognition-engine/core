# engine/canvas/event_protocol.py
"""Surface-agnostic event protocol (vision-doc §4.2).

Every surface (canvas, Claude Code hook, IDE, meeting transcript, mobile)
emits events conforming to this protocol. The engine consumer is surface-blind.

DO NOT add canvas-specific required fields to payload models. Canvas-only
fields (e.g. tldraw_shape_id) must be Optional so other surfaces can emit
the same event type without inventing data they don't have.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

# Event type constants. String literals (not enum) so non-Python surfaces
# can emit them without a translation table.
EVENT_SESSION_OPENED = "session.opened"
EVENT_SESSION_CLOSED = "session.closed"
EVENT_ARTIFACT_PLACED = "artifact.placed"
EVENT_ARTIFACT_UPDATED = "artifact.updated"
EVENT_ARTIFACT_REMOVED = "artifact.removed"
EVENT_FRAMEWORK_REQUESTED = "framework.requested"
EVENT_FRAMEWORK_STREAMING = "framework.streaming"
EVENT_FRAMEWORK_COMPLETED = "framework.completed"
EVENT_DECISION_MADE = "decision.made"
EVENT_PARTICIPANT_STATE_CHANGED = "participant.state_changed"
EVENT_AGENT_PERSPECTIVE_START = "agent.perspective.start"
EVENT_AGENT_PERSPECTIVE_STEP = "agent.perspective.step"
EVENT_AGENT_PERSPECTIVE_TOKEN = "agent.perspective.token"
EVENT_AGENT_PERSPECTIVE_END = "agent.perspective.end"
EVENT_AGENT_PHASE_START = "agent.phase.start"
EVENT_AGENT_PHASE_STEP = "agent.phase.step"
EVENT_AGENT_PHASE_END = "agent.phase.end"
EVENT_SYNTHESIS_START = "synthesis.start"
EVENT_SYNTHESIS_STEP = "synthesis.step"
EVENT_SYNTHESIS_END = "synthesis.end"
EVENT_PIPELINE_CLASSIFY = "pipeline.classify"
EVENT_PIPELINE_COMPOSE = "pipeline.compose"
EVENT_PIPELINE_ORCHESTRATE = "pipeline.orchestrate"
EVENT_AGENT_ACTIVITY_PLACED = "agent.activity.placed"
EVENT_DECISION_PREDICTION_ATTACHED = "decision.prediction.attached"
EVENT_PREDICTION_OUTCOME_CLOSED = "prediction.outcome.closed"
EVENT_BUILD_TEAM_RESOLVED = "build.team_resolved"

# decision:lv6stu70piemfwypde2e — Layer 5 context-assembly visibility.
# Emitted when load_decision_context surfaces N>0 prior decisions during a
# canvas-sourced engagement, so the surface can render a small "informed by N
# prior decisions" indicator near the turn header. Plan §11 future-work #3.
EVENT_LAYER5_CONTEXT_LOADED = "layer5.context_loaded"

ALL_EVENT_TYPES = frozenset(
    {
        EVENT_SESSION_OPENED,
        EVENT_SESSION_CLOSED,
        EVENT_ARTIFACT_PLACED,
        EVENT_ARTIFACT_UPDATED,
        EVENT_ARTIFACT_REMOVED,
        EVENT_FRAMEWORK_REQUESTED,
        EVENT_FRAMEWORK_STREAMING,
        EVENT_FRAMEWORK_COMPLETED,
        EVENT_DECISION_MADE,
        EVENT_PARTICIPANT_STATE_CHANGED,
        EVENT_AGENT_PERSPECTIVE_START,
        EVENT_AGENT_PERSPECTIVE_STEP,
        EVENT_AGENT_PERSPECTIVE_TOKEN,
        EVENT_AGENT_PERSPECTIVE_END,
        EVENT_AGENT_PHASE_START,
        EVENT_AGENT_PHASE_STEP,
        EVENT_AGENT_PHASE_END,
        EVENT_SYNTHESIS_START,
        EVENT_SYNTHESIS_STEP,
        EVENT_SYNTHESIS_END,
        EVENT_PIPELINE_CLASSIFY,
        EVENT_PIPELINE_COMPOSE,
        EVENT_PIPELINE_ORCHESTRATE,
        EVENT_AGENT_ACTIVITY_PLACED,
        EVENT_DECISION_PREDICTION_ATTACHED,
        EVENT_PREDICTION_OUTCOME_CLOSED,
        EVENT_LAYER5_CONTEXT_LOADED,
        EVENT_BUILD_TEAM_RESOLVED,
    }
)


class SessionOpenedPayload(BaseModel):
    title: str
    project_id: str
    opener_kind: str  # "human" | "ai"


class ArtifactPlacedPayload(BaseModel):
    shape_kind: str
    payload: dict[str, Any]
    author: str  # "human" | "ai"
    # Canvas-specific — Optional so non-canvas surfaces can omit
    tldraw_shape_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None


class FrameworkRequestedPayload(BaseModel):
    framework_kind: str  # "trade_off_matrix" | "rice" | "abstraction_ladder"
    prompt: str
    cited_artifact_ids: list[str] = []
    tldraw_shape_id: str = ""  # assigned by API before dispatch


class DecisionMadePayload(BaseModel):
    title: str
    rationale: str
    cited_artifact_ids: list[str] = []
    framework_kind: Optional[str] = None


class ParticipantStateChangedPayload(BaseModel):
    participant_id: str
    new_state: str  # ParticipantState value


class FrameworkCompletedPayload(BaseModel):
    tldraw_shape_id: Optional[str] = None  # canvas-only; other surfaces omit
    shape_kind: str
    framework_kind: str
    payload: dict[str, Any]
    reasoning_trace: Optional[dict[str, Any]] = None


class ReasoningStepPayload(BaseModel):
    framework_kind: str
    framework_name: str  # human-readable: "Trade-off Matrix"
    step_label: str  # "Checking" | "Scoring" | "Weighing" | "Conclusion"
    step_text: str
    step_index: int


class AgentPerspectiveStartPayload(BaseModel):
    archetype: str  # "analyst" | "creator" | "sentinel" | etc.
    mode: str  # "deliberative" | "exploratory" | etc.
    perspective_index: int  # 0-based position in the engagement sequence
    total_perspectives: int  # how many perspectives total


class AgentPerspectiveStepPayload(BaseModel):
    archetype: str
    content: str
    perspective_index: int


class AgentPerspectiveTokenPayload(BaseModel):
    archetype: str
    delta: str
    perspective_index: int


class AgentPerspectiveEndPayload(BaseModel):
    archetype: str
    handoff: str  # brief passed to next perspective
    confidence: float
    perspective_index: int


class AgentPhaseStartPayload(BaseModel):
    phase_idx: int
    total_phases: int
    cognitive_function: str


class AgentPhaseStepPayload(BaseModel):
    phase_idx: int
    cognitive_function: str
    content: str


class AgentPhaseEndPayload(BaseModel):
    phase_idx: int
    cognitive_function: str
    confidence: float
    gaps: list[str]


class SynthesisStepPayload(BaseModel):
    content: str


class AgentActivityPlacedPayload(BaseModel):
    """An agent placed/annotated/flagged something on the canvas."""

    agent_id: str
    archetype: str
    shape_id: Optional[str] = None
    action: str  # 'placed' | 'annotated' | 'flagged'
    rationale: str  # ≤200 chars; client truncates further if needed


class DecisionPredictionAttachedPayload(BaseModel):
    """A prediction has been attached to a decision."""

    decision_id: str
    prediction_id: str
    agent_id: str
    predicted_delta: float
    falsifier: str
    horizon_days: int


class PredictionOutcomeClosedPayload(BaseModel):
    """A prediction has been closed; archetype_calibration has been updated."""

    prediction_id: str
    agent_id: str
    archetype: str
    predicted: float
    actual: float
    predicted_deltas: dict[str, float] = {}
    actual_deltas: dict[str, float] = {}
    calibration_score: float
    weight_delta: float
    discipline: str


class Layer5ContextLoadedPayload(BaseModel):
    """The L5 loader surfaced N>0 prior decisions for the upcoming engagement.

    Surfaces render a small "informed by N prior decisions" indicator near
    the turn header so the user can see the system isn't reasoning cold —
    closes the visibility loop on decision:lv6stu70piemfwypde2e (Plan §11
    future-work item #3).
    """

    decision_count: int  # how many TieredDecisions reached the prompt
    capability_count: int  # how many were capability-tier (highest-weighted)
    discipline_count: int  # how many were discipline-tier
    recency_count: int  # how many were recency-tier
    degraded_tiers: list[str] = []  # tier names that timed out / failed
    contradictions_count: int = 0  # pairs flagged by _detect_contradictions
    elapsed_ms: float = 0.0  # loader wall-clock — debug telemetry
    calibration_archetypes: int = 0  # archetypes with calibration rows in loop_context


class PipelineClassifyPayload(BaseModel):
    discipline: str
    archetype: str
    mode: str
    specialties: list[str] = []


class PipelineComposePayload(BaseModel):
    meta_skills: list[str]  # e.g. ["coding_intelligence", "planning_intelligence"]
    depth: int  # 1-4 execution depth
    fusion_mode: bool  # True = cross-perspective synthesis enabled
    phase_count: int  # total cognitive phases resolved
    top_functions: list[str]  # first 3 cognitive_function values


class PipelineOrchestratePayload(BaseModel):
    perspectives: list[str]
    total: int


def is_surface_agnostic(event_dict: dict[str, Any]) -> bool:
    """Validate an event dict carries the surface-agnostic invariants.

    Returns True iff:
    - event_type is one of ALL_EVENT_TYPES
    - surface field is present (any non-empty string)
    - payload is a dict
    """
    if event_dict.get("event_type") not in ALL_EVENT_TYPES:
        return False
    surface = event_dict.get("surface")
    if not isinstance(surface, str) or not surface:
        return False
    if not isinstance(event_dict.get("payload"), dict):
        return False
    return True
