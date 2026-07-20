// frontend/src/types/canvas.ts
// Mirrors engine/canvas/models.py and engine/canvas/event_protocol.py verbatim.

export type ParticipantState = 'idle' | 'watching' | 'drafting' | 'blocked_on_input'
export type ParticipantKind = 'human' | 'ai'
export type ShapeKind =
  | 'participant_card'
  | 'framework_artifact'
  | 'decision_sticky'
  | 'lineage_edge'
  | 'sticky'
  | 'arrow'
  | 'note'

// Event type constants — must match engine/canvas/event_protocol.py exactly
export const EVENT_SESSION_OPENED = 'session.opened'
export const EVENT_SESSION_CLOSED = 'session.closed'
export const EVENT_ARTIFACT_PLACED = 'artifact.placed'
export const EVENT_ARTIFACT_UPDATED = 'artifact.updated'
export const EVENT_ARTIFACT_REMOVED = 'artifact.removed'
export const EVENT_FRAMEWORK_REQUESTED = 'framework.requested'
export const EVENT_FRAMEWORK_STREAMING = 'framework.streaming'
export const EVENT_FRAMEWORK_COMPLETED = 'framework.completed'
export const EVENT_DECISION_MADE = 'decision.made'
export const EVENT_PARTICIPANT_STATE_CHANGED = 'participant.state_changed'
export const EVENT_AGENT_PERSPECTIVE_START = 'agent.perspective.start'
export const EVENT_AGENT_PERSPECTIVE_STEP = 'agent.perspective.step'
export const EVENT_AGENT_PERSPECTIVE_END = 'agent.perspective.end'
export const EVENT_SYNTHESIS_START = 'synthesis.start'
export const EVENT_SYNTHESIS_STEP = 'synthesis.step'
export const EVENT_SYNTHESIS_END = 'synthesis.end'
export const EVENT_PIPELINE_CLASSIFY = 'pipeline.classify'
export const EVENT_PIPELINE_COMPOSE = 'pipeline.compose'
export const EVENT_PIPELINE_ORCHESTRATE = 'pipeline.orchestrate'
export const EVENT_AGENT_PHASE_END = 'agent.phase.end'
export const EVENT_BUILD_TEAM_RESOLVED = 'build.team_resolved'
export const EVENT_AGENT_PHASE_START = 'agent.phase.start'

// Union of all event type strings — use in switch statements for exhaustiveness checking
export type CanvasEventType =
  | typeof EVENT_SESSION_OPENED
  | typeof EVENT_SESSION_CLOSED
  | typeof EVENT_ARTIFACT_PLACED
  | typeof EVENT_ARTIFACT_UPDATED
  | typeof EVENT_ARTIFACT_REMOVED
  | typeof EVENT_FRAMEWORK_REQUESTED
  | typeof EVENT_FRAMEWORK_STREAMING
  | typeof EVENT_FRAMEWORK_COMPLETED
  | typeof EVENT_DECISION_MADE
  | typeof EVENT_PARTICIPANT_STATE_CHANGED
  | typeof EVENT_AGENT_PERSPECTIVE_START
  | typeof EVENT_AGENT_PERSPECTIVE_STEP
  | typeof EVENT_AGENT_PERSPECTIVE_END
  | typeof EVENT_SYNTHESIS_START
  | typeof EVENT_SYNTHESIS_STEP
  | typeof EVENT_SYNTHESIS_END

// ===========================================================================
// Living Canvas substrate events — mirror engine/events/canvas.py exactly.
// These flow over the canvas WebSocket alongside session-level CanvasEvents
// but describe substrate-level mutations (capabilities, decisions, sentinel,
// compositions, etc.) rather than artifact/session events.
// ===========================================================================

export const LCE_CAPABILITY_ADDED = 'capability.added'
export const LCE_CAPABILITY_UPDATED = 'capability.updated'
export const LCE_CAPABILITY_LIFECYCLE_CHANGED = 'capability.lifecycle_changed'
export const LCE_DECISION_CAPTURED = 'decision.captured'
export const LCE_EDGE_ADDED = 'edge.added'
export const LCE_SCORE_CHANGED = 'score.changed'
export const LCE_SENTINEL_FIRED = 'sentinel.fired'
export const LCE_BRIEFING_UPDATED = 'briefing.updated'
export const LCE_PROACTIVE_LINE_UPDATED = 'proactive.line.updated'
export const LCE_HANDOFF_STARTED = 'handoff.started'
export const LCE_HANDOFF_PROGRESS = 'handoff.progress'
export const LCE_HANDOFF_COMPLETED = 'handoff.completed'
export const LCE_DRIFT_CROSSED = 'drift.crossed'
export const LCE_RECOMMENDATION_SHIFTED = 'recommendation.shifted'
export const LCE_UNCERTAINTY_OPENED = 'uncertainty.opened'
export const LCE_UNCERTAINTY_ANSWERED = 'uncertainty.answered'
export const LCE_INTELLIGENCE_CLASSIFIED = 'intelligence.classified'
export const LCE_PATTERN_MATCHED = 'pattern.matched'
export const LCE_CODE_EDITED = 'code.edited'
export const LCE_THREAD_COMMITTED = 'thread.committed'
export const LCE_THREAD_RESOLVED = 'thread.resolved'
// L3 composition layer — emitted on every successful CognitiveComposer.compose()
// so the orchestra (which of the 22 meta-intelligences self-nominated) becomes
// legible on the canvas.
export const LCE_COMPOSITION_SELECTED = 'composition.selected'

export type LivingCanvasEventType =
  | typeof LCE_CAPABILITY_ADDED
  | typeof LCE_CAPABILITY_UPDATED
  | typeof LCE_CAPABILITY_LIFECYCLE_CHANGED
  | typeof LCE_DECISION_CAPTURED
  | typeof LCE_EDGE_ADDED
  | typeof LCE_SCORE_CHANGED
  | typeof LCE_SENTINEL_FIRED
  | typeof LCE_BRIEFING_UPDATED
  | typeof LCE_PROACTIVE_LINE_UPDATED
  | typeof LCE_HANDOFF_STARTED
  | typeof LCE_HANDOFF_PROGRESS
  | typeof LCE_HANDOFF_COMPLETED
  | typeof LCE_DRIFT_CROSSED
  | typeof LCE_RECOMMENDATION_SHIFTED
  | typeof LCE_UNCERTAINTY_OPENED
  | typeof LCE_UNCERTAINTY_ANSWERED
  | typeof LCE_INTELLIGENCE_CLASSIFIED
  | typeof LCE_PATTERN_MATCHED
  | typeof LCE_CODE_EDITED
  | typeof LCE_THREAD_COMMITTED
  | typeof LCE_THREAD_RESOLVED
  | typeof LCE_COMPOSITION_SELECTED

export interface LivingCanvasProvenance {
  source: 'user' | 'ace_classifier' | 'sentinel' | 'scanner' | 'agent_dispatch'
  actor_id?: string | null
  rationale?: string | null
}

export interface LivingCanvasEvent<TPayload = Record<string, unknown>> {
  event_type: LivingCanvasEventType
  product_id: string
  timestamp: string
  payload: TPayload
  provenance: LivingCanvasProvenance
}

// Payload for composition.selected — surfaced as the orchestra view.
// Mirrors emit_composition_selected() in engine/events/canvas.py.
export interface CompositionSelectedPayload {
  meta_skills: string[]
  depth: 1 | 2 | 3 | 4
  fusion_mode: boolean
  classification?: {
    task_type?: string
    discipline?: string
    mode?: string
    archetype?: string
    complexity?: string
  }
}

// ===========================================================================
// Deliberation Journey — the canvas's primary surface.
//
// The journey renders the substrate's full L1→L9 stack visibly:
//   L1 (Meta-Intelligence)  → Topic header + prior context
//   L2 (Classification)     → Classification banner (discipline/mode/depth/conf)
//   L3 (Composition)        → Stage count + active meta-skills
//   L4 (Engagement)         → Parallel tracks within each stage
//   L5 (Frameworks)         → Per-track instrument name (resolved framework)
//   L6 (Synthesis)          → Stage-bottom synthesis: implication + tension + leverage
//   L7 (Decision + Graph)   → Decision cards pinned at converge stages
//   L8 (Sentinel)           → Edge marks when sentinel engines fire
//   L9 (Foresight)          → Prediction tile attached to decisions
//
// Every layer of the substrate is visible somewhere on the journey surface.
// Static fixture data populates these types for first render; live WebSocket
// subscription will swap to substrate-driven data later.
// ===========================================================================

/** Canonical cognitive function names from MetaSkillRecipe phases. */
export type StagePhase =
  | 'prep'
  | 'frame'
  | 'prioritize'
  | 'choose'
  | 'validate'
  | 'allocate'
  | 'critique'

export type StageStatus = 'past' | 'current' | 'future'

/** One meta-intelligence's contribution at a stage (L4 lens × L5 instrument). */
export interface JourneyTrack {
  /** meta_skill slug, e.g. 'creative_intelligence'. Drives identity color. */
  metaSkill: string
  /** Short display name — 'creative', 'coding', etc. */
  label: string
  /** Color token reference (e.g., '--ace-accent-creator'). Falls back gracefully. */
  accent?: string
  /** The contribution body — what this intelligence said at this stage. */
  contribution: string
  /** L5: which instrument framework resolved at this slot. */
  instrument?: string
  /** 0–1 confidence. Optional — shown subtly if present. */
  confidence?: number
  /** Whether the track is still forming (for current stage animation). */
  inFlight?: boolean
}

/** L6 synthesis at the bottom of a stage — the cross-track implication chain. */
export interface JourneySynthesis {
  /** Lead synthesis sentence — what the tracks together imply. */
  implication: string
  /** Tension surfaced between tracks — the partnership's most useful output. */
  tension?: string
  /** Top leverage point per L6 — the intervention with highest cascade. */
  leveragePoint?: string
}

/** L9 prediction attached at a converge stage — falsifiable forward forecast. */
export interface JourneyPrediction {
  horizonDays: number
  forecast: string
  falsifyIf: string
  /** When true, the prediction window has closed and was scored. */
  reconciled?: boolean
  /** 0–1 calibration score if reconciled. */
  calibrationScore?: number
}

/** L8 sentinel finding surfaced at the stage's edge. */
export interface JourneySentinelMark {
  severity: 'low' | 'medium' | 'high'
  source: string
  headline: string
}

/** L7 captured decision pinned at a converge stage. */
export interface JourneyDecision {
  id: string
  title: string
  rationale?: string
  /** 0–1 mean confidence across contributing tracks. */
  confidence?: number
  /** Track labels that fed this decision (lineage). */
  cited?: string[]
}

/** Optional inline visualizations a stage can render alongside its tracks. */
export interface JourneyCapabilityNode {
  id: string
  label: string
  state: 'load-bearing' | 'out-of-scope'
}

export interface JourneyCapabilityEdge {
  from: string
  to: string
  dashed?: boolean
}

export interface JourneyCapabilityGraph {
  nodes: JourneyCapabilityNode[]
  edges: JourneyCapabilityEdge[]
}

/** Live working-room signal at the bottom of a current stage. */
export interface JourneyWorkingSignal {
  metaSkill: string
  label: string
  state: 'typing' | 'just-spoke' | 'waiting'
  whenLabel?: string
}

/** One stage of the journey — a phase of cognitive work. */
export interface JourneyStage {
  /** Stable id used for keying + deep-link targets. */
  id: string
  /** Canonical cognitive function from the recipe phase. */
  phase: StagePhase
  /** Single-glyph stage mark — ⌖ prep · ◯ frame · ◇ diverge/prioritize/choose · ◆ converge/validate. */
  glyph: string
  /** Display title — e.g., 'Frame · capability map'. */
  title: string
  /** Optional subtitle clarifying what this stage does. */
  subtitle?: string
  status: StageStatus
  /** Parallel meta-intelligence tracks running this stage. */
  tracks: JourneyTrack[]
  /** L6 synthesis at the stage's bottom. */
  synthesis?: JourneySynthesis
  /** L9 prediction attached at this stage (typically converge stages). */
  prediction?: JourneyPrediction
  /** L8 sentinel marks active at this stage. */
  sentinel?: JourneySentinelMark[]
  /** L7 decision(s) captured at this stage. */
  decisions?: JourneyDecision[]
  /** Optional inline capability-graph visualization (typically Frame stage). */
  capabilityGraph?: JourneyCapabilityGraph
  /** Optional working-room signals at the bottom of a current stage. */
  workingSignals?: JourneyWorkingSignal[]
  /** Optional per-track tooltip data: matched activation_signals. Keyed by meta-skill slug. */
  matchedSignalsByMetaSkill?: Record<string, string[]>
  /** Forkable foresight — "paths not taken": alternative reasoning re-runs branched from this point. */
  forkTrace?: JourneyForkTrace
}

/** One branch in a fork comparison — the original baseline or a re-reasoned alternative. */
export interface JourneyForkBranch {
  /** 'original' for the baseline, else the lens name (e.g. 'systems', 'adversarial'). */
  label: string
  lens: string
  /** Comparative score 0..1 (the judge's ranking signal, optionally capability-blended). */
  score: number
  conclusion: string
  /** Optional value_model capability-trajectory score (the opt-in second lens). */
  capabilityDeltaScore?: number
}

/** Forkable-foresight comparison attached to a stage — branch-from-checkpoint, compare before acting. */
export interface JourneyForkTrace {
  runId: string
  checkpointSeq: number
  recommendation: 'fork' | 'keep_original'
  best: JourneyForkBranch
  original: JourneyForkBranch
  forks: JourneyForkBranch[]
}

/** Classification banner data (L2). */
export interface JourneyClassification {
  discipline: string
  taskType: string
  mode: string
  archetype: string
  complexity: string
  /** 0–1 classifier confidence. */
  confidence?: number
  /** Depth derived from mode × complexity (1–4). */
  depth: 1 | 2 | 3 | 4
  /** Whether fusion mode is active (depth ≤ 2 — single fused LLM call). */
  fusionMode: boolean
  /** Active meta-skill slugs (L3 composition). */
  metaSkills: string[]
  /** Tool inventory the partner has access to this turn. */
  tools?: JourneyTool[]
}

/** A tool available to the partner — surfaced in the Tools popover. */
export interface JourneyTool {
  /** Stable identifier — e.g. "ace_search", "grep_repo". */
  slug: string
  /** Display name — e.g. "ACE search". */
  label: string
  /** What this tool does. Surfaces in the popover description. */
  description: string
  /** Category for grouping in the popover. */
  category: 'ace' | 'code' | 'web' | 'data' | 'external'
  /** When true, this tool was used (or is being used) this turn. */
  active?: boolean
}

/** The journey state — read by DeliberationJourney to render the entire L1→L9 surface. */
export interface DeliberationJourneyState {
  /** L1: the current question / topic in flight. */
  topic: string
  /** L2: classification banner. */
  classification: JourneyClassification
  /** L3+L4: stages with parallel tracks. */
  stages: JourneyStage[]
  /** L7: prior decisions accumulated from this session, shown as pinned notes. */
  priorDecisions?: JourneyDecision[]
  /** L8: ambient sentinel pulse activity (page-wide, not stage-scoped). */
  ambientSentinel?: JourneySentinelMark[]
}

export interface CanvasSession {
  id: string           // e.g. "canvas_session:abc" — contains colons
  project_id: string
  title: string
  created_at: string
  updated_at: string
  ai_participant_id?: string
  artifacts?: CanvasArtifact[]
}

export interface CanvasArtifact {
  id: string
  session_id: string
  shape_kind: ShapeKind
  tldraw_shape_id: string
  payload: Record<string, unknown>
  x: number
  y: number
  author: ParticipantKind
  created_at: string
  updated_at: string
}

export interface CanvasEvent {
  id: string
  session_id: string
  event_type: CanvasEventType
  payload: Record<string, unknown>
  surface: string
  created_at: string
}

// Payloads for events we handle in the frontend
export interface ArtifactPlacedPayload {
  shape_kind: ShapeKind
  payload: Record<string, unknown>
  author: ParticipantKind
  tldraw_shape_id?: string
  x?: number
  y?: number
}

export interface ReasoningTraceSnapshot {
  classify: PipelineClassifyPayload
  compose: PipelineComposePayload | null
  orchestrate: PipelineOrchestratePayload
  perspectives: AgentPerspective[]
  synthesis: SynthesisPhase | null
}

export interface FrameworkCompletedPayload {
  tldraw_shape_id: string
  shape_kind: string
  framework_kind: string
  payload: Record<string, unknown>
  reasoning_trace?: ReasoningTraceSnapshot | null
}

export interface FrameworkOption {
  name: string
  description: string
}

export interface FrameworkAxis {
  name: string
  weight: number
}

export interface ParticipantStateChangedPayload {
  participant_id: string
  new_state: ParticipantState
}

export interface DecisionMadePayload {
  title: string
  rationale: string
  cited_artifact_ids: string[]
  framework_kind?: string
  decision_id?: string
}

// Reasoning step — emitted as framework.streaming events
export interface ReasoningStep {
  label: string   // e.g. "Checking", "Scoring", "Weighing", "Conclusion"
  text: string
  index: number
  framework_name?: string
  timestamp?: string  // kept for backward compat
}

// API request bodies
export interface CreateSessionBody {
  project_id: string
  title: string
}

export interface PlaceArtifactBody {
  shape_kind: ShapeKind
  tldraw_shape_id: string
  payload: Record<string, unknown>
  x?: number
  y?: number
  author?: ParticipantKind
}

export interface RequestFrameworkBody {
  framework_kind: string
  prompt: string
  cited_artifact_ids?: string[]
}

export interface RecordDecisionBody {
  title: string
  rationale: string
  cited_artifact_ids?: string[]
  framework_kind?: string
}

export interface ContributionBody {
  originating_thought: string
  recent_texts: string[]
}

export interface ContributionResult {
  placed: boolean
  tldraw_shape_id: string | null
  text: string | null
  kind: string | null
  relevance: number
}

export interface ForwardMomentumItem {
  title: string
  rationale: string
  terminal_score?: number      // gap score of best branch (0–1)
  forced_decisions?: string[]  // best_path[1:]: decisions the candidate forces
  top_risk?: string            // primary risk of the best branch
}

export interface CanvasTimeline {
  events: Record<string, unknown>[]
  forward_momentum: ForwardMomentumItem[]
}

export interface ReasoningStepPayload {
  framework_kind: string
  framework_name: string
  step_label: string
  step_text: string
  step_index: number
}

// Multi-agent perspective types
export interface AgentPerspectiveStartPayload {
  archetype: string           // 'analyst' | 'creator' | 'sentinel' | 'advisor' | etc.
  mode: string                // 'deliberative' | 'exploratory' | etc.
  perspective_index: number   // 0-based
  total_perspectives: number
}

export interface AgentPerspectiveStepPayload {
  archetype: string
  content: string
  perspective_index: number
}

export interface AgentPerspectiveEndPayload {
  archetype: string
  handoff: string
  confidence: number
  perspective_index: number
}

export interface SynthesisStepPayload {
  content: string
}

// State model for ReasoningPanel
export interface AgentPerspective {
  archetype: string
  mode: string
  index: number
  content: string       // accumulates as step events arrive
  handoff: string
  confidence: number
  complete: boolean
}

export interface SynthesisPhase {
  content: string
  complete: boolean
}

export interface PipelineClassifyPayload {
  discipline: string
  archetype: string
  mode: string
  specialties: string[]
}

export interface PipelineComposePayload {
  meta_skills: string[]
  depth: number
  fusion_mode: boolean
  phase_count: number
  top_functions: string[]
}

export interface PipelineOrchestratePayload {
  perspectives: string[]
  total: number
}

export interface CodeArchitecturePayload {
  framework_kind: 'code_architecture'
  title: string
  module: string
  nodes: Array<{ id: string; label: string; type: 'core' | 'consumer' | 'dependency' }>
  edges: Array<{ from: string; to: string; label: string }>
  blast_radius: { score: number; affected_files: number; risk: 'low' | 'medium' | 'high' }
  recommendation: string
}

export interface CompileResponse {
  id?: string
  title?: string
  content?: string
  error?: string
}

export interface ExpectedChange {
  capability_id: string
  score_delta: number
  confidence: number
}

export interface Prediction {
  id: string
  decision: string
  archetype: string
  discipline: string
  horizon_days: number
  expected_changes: ExpectedChange[]
  primary_risk: string
  leading_indicators: string[]
  falsification_condition: string
  closed: boolean
  created_at: string
}

export interface PredictionOutcome {
  calibration_score: number
  predicted_deltas: Record<string, number>
  actual_deltas: Record<string, number>
  closed_at: string
}

// ─── A.7 Orchestration channel types ────────────────────────────────────────

export type OrchestrationEventType =
  | 'hello'
  | 'ping'
  | 'run_start'
  | 'run_done'
  | 'run_error'
  | 'run_cancelled'
  | 'block_start'
  | 'block_done'
  | 'claude_call_start'
  | 'claude_call_done'
  | 'token'
  | 'classification'
  | 'engagement_start'
  | 'engagement_done'
  | 'agent_loop_start'
  | 'agent_loop_done'
  | 'tool_call'
  | 'tool_result'
  | 'atc_lock'
  | 'atc_blocked'
  | 'atc_release'
  | 'decision_captured'
  | 'prediction_attached'
  | 'sentinel_event'
  | 'replay_start'
  | 'replay_done'

export interface OrchestrationEvent {
  type: OrchestrationEventType
  run_id?: string
  task_id?: string
  parent_id?: string | null
  ts?: string
  [key: string]: unknown
}

export interface OrchestrationNode {
  task_id: string
  parent_id: string | null
  type: OrchestrationEventType
  run_id: string
  ts: string
  label: string
  status: 'running' | 'done' | 'error' | 'cancelled'
  doneEvent?: OrchestrationEvent
  children: OrchestrationNode[]
}

export interface RosterArchetype {
  id: string
  name: string
  color: string
  status: 'idle' | 'thinking' | 'active' | 'watching' | 'reconnecting'
}

export interface AgentActivityPayload {
  agent_id: string
  archetype: string
  shape_id: string | null
  action: 'placed' | 'annotated' | 'flagged'
  rationale: string
}

// L9 prediction lifecycle — must match engine/canvas/event_protocol.py
// exactly (EVENT_DECISION_PREDICTION_ATTACHED / EVENT_PREDICTION_OUTCOME_CLOSED).
// The forecaster emits attach when a falsifiable forecast is pinned to a
// decision; the reconciler emits close when the horizon lapses and the
// archetype's calibration is updated.
export const LCE_DECISION_PREDICTION_ATTACHED = 'decision.prediction.attached'
export const LCE_PREDICTION_OUTCOME_CLOSED = 'prediction.outcome.closed'

export interface DecisionPredictionAttachedPayload {
  decision_id: string
  prediction_id: string
  agent_id: string
  predicted_delta: number
  falsifier: string
  horizon_days: number
}

export interface PredictionOutcomeClosedPayload {
  prediction_id: string
  agent_id: string
  archetype: string
  predicted: number
  actual: number
  predicted_deltas: Record<string, number>
  actual_deltas: Record<string, number>
  calibration_score: number
  weight_delta: number
  discipline: string
}

// Intent router — /canvas/sessions/{id}/respond
export interface RespondBody { thought: string; recent_texts: string[] }
export interface RespondResult { response_type: string; tldraw_shape_id: string | null; read: string }
export interface ReasoningSection { cognitive_function: string; output: string; confidence: number }
export interface AgentPhaseEndPayload { phase_idx: number; cognitive_function: string; confidence: number; gaps: string[] }

export interface BuildTeamResolvedPayload {
  build_run_id: string
  lenses: string[]
}
