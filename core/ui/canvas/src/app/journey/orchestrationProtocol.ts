// app/journey/orchestrationProtocol.ts
//
// Wire-level shapes for the orchestration WebSocket
// (`/canvas/sessions/{session_id}/orchestration`). These mirror the
// backend's `OrchestratorEvent.to_dict()` output, which renames
// `event_type` → `type` and `timestamp` → `ts`. Each event includes the
// `run_id` / `task_id` / `parent_id` envelope from the base class.
//
// Keep this file minimal — only the events we actually consume in
// `useOrchestrationSession`. Backend ships ~40 event types; we
// intentionally subscribe to a small subset for Phase 1.

export interface OrchestrationEnvelope {
  type: string
  run_id?: string
  task_id?: string
  parent_id?: string | null
  product_id?: string
  ts?: string
  seq?: number
}

// --- Lifecycle ---------------------------------------------------------------

export interface HelloEvent extends OrchestrationEnvelope {
  type: 'hello'
  session_id: string
  product_id: string
  active_runs: string[]
}

export interface PingEvent extends OrchestrationEnvelope {
  type: 'ping'
}

export interface RunStartEvent extends OrchestrationEnvelope {
  type: 'run_start'
  session_id?: string
  user_message?: string
}

export interface RunDoneEvent extends OrchestrationEnvelope {
  type: 'run_done'
  duration_ms?: number
}

export interface RunErrorEvent extends OrchestrationEnvelope {
  type: 'run_error'
  error: string
  recovery_hint?: string
}

// --- Pipeline phase markers --------------------------------------------------

export interface BlockStartEvent extends OrchestrationEnvelope {
  type: 'block_start'
  block_name: string
  layer?: number
}

export interface BlockDoneEvent extends OrchestrationEnvelope {
  type: 'block_done'
  block_name: string
  duration_ms?: number
  summary?: string
}

// --- L2 Classification -------------------------------------------------------

export interface ClassificationEvent extends OrchestrationEnvelope {
  type: 'classification'
  discipline?: string
  archetypes?: string[]
  depth?: number
}

export interface ClassificationCompleteEvent extends OrchestrationEnvelope {
  type: 'classification_complete'
  domain_path?: string
  archetype?: string
  mode?: string
  complexity?: string
}

// --- L4 Engagement (per meta-skill) ------------------------------------------

export interface EngagementStartEvent extends OrchestrationEnvelope {
  type: 'engagement_start'
  pattern?: string
  archetypes?: string[]
}

export interface EngagementDoneEvent extends OrchestrationEnvelope {
  type: 'engagement_done'
}

// --- Streaming tokens --------------------------------------------------------

export interface TokenEvent extends OrchestrationEnvelope {
  type: 'token'
  content: string
}

export interface AgentTokenEvent extends OrchestrationEnvelope {
  type: 'agent_token'
  agent_id?: string
  text: string
}

// --- L7/L8/L9 captures -------------------------------------------------------

export interface DecisionCapturedEvent extends OrchestrationEnvelope {
  type: 'decision_captured'
  decision_id: string
}

export interface PredictionAttachedEvent extends OrchestrationEnvelope {
  type: 'prediction_attached'
  prediction_id: string
  horizon_days?: number
  falsification_condition?: string
}

export interface SentinelOrchestrationEvent extends OrchestrationEnvelope {
  type: 'sentinel_event'
  engine?: string
  severity?: 'low' | 'medium' | 'high' | string
  summary?: string
}

// --- Tool calls (the partner using its tools live) ---------------------------

export interface ToolCallOrchestrationEvent extends OrchestrationEnvelope {
  type: 'tool_call'
  tool: string
  input_summary?: string
}

export interface ToolResultOrchestrationEvent extends OrchestrationEnvelope {
  type: 'tool_result'
  tool: string
  summary?: string
}

// --- Discriminated union we narrow on -----------------------------------------

export type WsInbound =
  | HelloEvent
  | PingEvent
  | RunStartEvent
  | RunDoneEvent
  | RunErrorEvent
  | BlockStartEvent
  | BlockDoneEvent
  | ClassificationEvent
  | ClassificationCompleteEvent
  | EngagementStartEvent
  | EngagementDoneEvent
  | TokenEvent
  | AgentTokenEvent
  | DecisionCapturedEvent
  | PredictionAttachedEvent
  | SentinelOrchestrationEvent
  | ToolCallOrchestrationEvent
  | ToolResultOrchestrationEvent

/** Backend may emit ~40 event types; we only narrow on the ones we
 *  consume. Unknown frames are passed through as this opaque shape and
 *  the reducer's default branch ignores them. */
export type UnknownInbound = OrchestrationEnvelope & { type: string }

export interface UserMessageOutbound {
  type: 'message'
  content: string
}
