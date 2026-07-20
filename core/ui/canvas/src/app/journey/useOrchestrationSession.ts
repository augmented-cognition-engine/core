// app/journey/useOrchestrationSession.ts
//
// Phase 1 live ACE wiring: REST `POST /canvas/sessions` → WebSocket
// `/canvas/sessions/{id}/orchestration` → reducer projects the event
// stream into a live `DeliberationJourneyState`.
//
// What's intentionally NOT here (Phase 2 follow-ups):
//   - Live token streaming into track contribution (tokens are buffered
//     per task_id; contribution updates on EngagementDone).
//   - Reconnect / resume protocol — drop = run abandoned.
//   - URL-param session id for refresh survival.
//   - Multi-stage progression — Phase 1 shows a single live stage that
//     accumulates tracks; backend doesn't emit phase markers.
//
// The hook is deliberately lifecycle-scoped — call it once per topic;
// changing the topic kicks off a new session and tears down the old WS.

import { useCallback, useEffect, useReducer, useRef } from 'react'

import type {
  DeliberationJourneyState,
  JourneyClassification,
  JourneyDecision,
  JourneyPrediction,
  JourneySentinelMark,
  JourneyStage,
  JourneyTrack,
  StagePhase,
  StageStatus,
} from '../../types/canvas'
import type {
  ClassificationCompleteEvent,
  ClassificationEvent,
  EngagementStartEvent,
  UnknownInbound,
  WsInbound,
} from './orchestrationProtocol'

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export type OrchestrationStatus =
  | 'idle'
  | 'creating_session'
  | 'connecting'
  | 'streaming'
  | 'reconnecting'
  | 'done'
  | 'error'

/** A tool invocation observed live on the WS — added on tool_call,
 *  resolved on tool_result. Surfaced in WorkingRoomRibbon so the user
 *  sees what tools the partner is actually using mid-deliberation. */
export interface LiveToolCall {
  tool: string
  inputSummary?: string
  /** Backend task_id — used to match tool_result back to the call. */
  taskId: string
  /** ts of the start event (epoch ms, set client-side). */
  startedAt: number
  /** Result summary once tool_result lands. Track lingers ~3s after
   *  result so the user sees "spoke 1s ago" before it fades. */
  resultSummary?: string
  resolvedAt?: number
}

export interface OrchestrationSessionState {
  status: OrchestrationStatus
  sessionId: string | null
  runId: string | null
  /** Last task_id observed on the WS — used as a "mid-run" sentinel to
   *  gate reconnect (the resume cursor itself is `lastSeq`, not this). */
  lastTaskId: string | null
  /** Last seq observed on the WS — used as the per-event resume cursor
   *  (M3). Events with seq <= lastSeq are de-duped (idempotent replay). */
  lastSeq: number | null
  error: string | null
  journey: DeliberationJourneyState | null
  /** Buffer for streaming tokens, keyed by task_id. Mirrors the live
   *  track contribution; survives EngagementDone for resume sanity. */
  tokenBuffers: Record<string, string>
  /** Tools currently in flight (or recently resolved) — keyed by
   *  task_id so tool_result can match back. */
  toolCalls: Record<string, LiveToolCall>
  /** Count of consecutive reconnect attempts since last successful
   *  ws_open. Resets to 0 on every successful open. Used by the
   *  optional auto-reconnect effect to compute backoff and bail
   *  after max retries. */
  reconnectAttempt: number
}

const initialState: OrchestrationSessionState = {
  status: 'idle',
  sessionId: null,
  runId: null,
  lastTaskId: null,
  lastSeq: null,
  error: null,
  journey: null,
  tokenBuffers: {},
  toolCalls: {},
  reconnectAttempt: 0,
}

/** Exported for unit tests — the reducer's starting state, freshly built
 *  so tests don't share references. */
export function freshInitialState(): OrchestrationSessionState {
  return {
    status: 'idle',
    sessionId: null,
    runId: null,
    lastTaskId: null,
    lastSeq: null,
    error: null,
    journey: null,
    tokenBuffers: {},
    toolCalls: {},
    reconnectAttempt: 0,
  }
}

// ---------------------------------------------------------------------------
// Reducer actions
// ---------------------------------------------------------------------------

type Action =
  | { type: 'session_creating' }
  | { type: 'session_created'; sessionId: string }
  | { type: 'ws_open' }
  | { type: 'ws_close' }
  | { type: 'ws_error'; error: string }
  | { type: 'remote'; event: WsInbound | UnknownInbound; topic: string }
  | { type: 'reset'; topic: string }
  | { type: 'reconnect_scheduled' }
  | { type: 'reconnect_exhausted'; error: string }

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

function initialJourney(topic: string): DeliberationJourneyState {
  return {
    topic,
    classification: {
      discipline: 'pending…',
      taskType: 'pending',
      mode: 'pending',
      archetype: 'pending',
      complexity: 'pending',
      depth: 1,
      fusionMode: false,
      metaSkills: [],
    } satisfies JourneyClassification,
    stages: [
      {
        id: 'live',
        phase: 'choose',
        glyph: '◇',
        title: 'In motion',
        subtitle: 'the partner is reasoning',
        status: 'current',
        tracks: [],
      } satisfies JourneyStage,
    ],
  }
}

function reducer(state: OrchestrationSessionState, action: Action): OrchestrationSessionState {
  switch (action.type) {
    case 'reset':
      return {
        ...initialState,
        toolCalls: {},
        status: 'creating_session',
        journey: initialJourney(action.topic),
      }

    case 'session_creating':
      return { ...state, status: 'creating_session', error: null }

    case 'session_created':
      return { ...state, status: 'connecting', sessionId: action.sessionId }

    case 'ws_open':
      // Successful open clears any pending reconnect attempt counter
      // so a future drop starts the backoff from scratch.
      return { ...state, status: 'streaming', reconnectAttempt: 0, error: null }

    case 'ws_close':
      if (state.status === 'done' || state.status === 'error') return state
      // Unexpected close while still streaming. The default behavior
      // is to surface as error so the caller (or the auto-reconnect
      // effect) can decide what to do; auto-reconnect transitions to
      // 'reconnecting' via the dedicated 'reconnect_scheduled' action.
      return {
        ...state,
        status: state.lastTaskId !== null ? 'error' : 'done',
        error: state.lastTaskId !== null ? 'connection lost mid-run' : state.error,
      }

    case 'reconnect_scheduled':
      return {
        ...state,
        status: 'reconnecting',
        reconnectAttempt: state.reconnectAttempt + 1,
        error: null,
      }

    case 'reconnect_exhausted':
      return { ...state, status: 'error', error: action.error }

    case 'ws_error':
      return { ...state, status: 'error', error: action.error }

    case 'remote': {
      // applyRemoteEvent handles the M3 seq de-dupe and lastSeq advancement.
      const next = applyRemoteEvent(state, action.event, action.topic)
      // Track the most recent task_id so the resume protocol has a
      // cursor to hand back to the backend on reconnect.
      const taskId = action.event.task_id
      if (taskId !== undefined && taskId !== next.lastTaskId) {
        return { ...next, lastTaskId: taskId }
      }
      return next
    }

    default:
      return state
  }
}

// ---------------------------------------------------------------------------
// Event → journey reducer
// ---------------------------------------------------------------------------

/** Exported for unit tests — pure event → state projection used by the
 *  hook's reducer. Safe to call directly with a synthesized event.
 *
 *  M3: de-dupes replayed events using the `seq` field (idempotent resume).
 *  Events without a `seq` field are applied normally (backward compat). */
export function applyRemoteEvent(
  state: OrchestrationSessionState,
  evt: WsInbound | UnknownInbound,
  topic: string,
): OrchestrationSessionState {
  // Idempotent replay: drop events we've already applied (M3 seq cursor).
  // Events without a seq field skip this guard for backward compatibility.
  const seq = (evt as { seq?: number }).seq
  if (typeof seq === 'number' && state.lastSeq !== null && seq <= state.lastSeq) {
    return state
  }

  // Apply the event and then advance lastSeq if the event carried one.
  const next = _applyRemoteEventInner(state, evt, topic)
  return typeof seq === 'number' ? { ...next, lastSeq: seq } : next
}

/** Core event → state projection. Called by applyRemoteEvent after de-dupe guard. */
function _applyRemoteEventInner(
  state: OrchestrationSessionState,
  evt: WsInbound | UnknownInbound,
  topic: string,
): OrchestrationSessionState {
  const journey = state.journey ?? initialJourney(topic)
  const t = evt.type

  if (t === 'hello' || t === 'ping') return state

  if (t === 'run_start') {
    return { ...state, runId: evt.run_id ?? state.runId, journey }
  }

  if (t === 'classification') {
    return {
      ...state,
      journey: {
        ...journey,
        classification: classificationFromEvent(evt as ClassificationEvent, journey.classification),
      },
    }
  }

  if (t === 'classification_complete') {
    return {
      ...state,
      journey: {
        ...journey,
        classification: classificationFromCompleteEvent(
          evt as ClassificationCompleteEvent,
          journey.classification,
        ),
      },
    }
  }

  if (t === 'block_start') {
    const blockName = (evt as { block_name?: string }).block_name ?? ''
    if (!blockName) return state
    return { ...state, journey: applyBlockStart(journey, blockName) }
  }

  if (t === 'block_done') {
    // timing-only; no stage mutation. outer reducer still advances lastTaskId.
    return state
  }

  if (t === 'engagement_start') {
    return {
      ...state,
      journey: pushTrack(journey, trackFromEngagement(evt as EngagementStartEvent)),
    }
  }

  if (t === 'token') {
    if (evt.task_id === undefined) return state
    const content = (evt as { content?: string }).content ?? ''
    return appendToken(state, evt.task_id, content)
  }

  if (t === 'agent_token') {
    if (evt.task_id === undefined) return state
    const text = (evt as { text?: string }).text ?? ''
    return appendToken(state, evt.task_id, text)
  }

  if (t === 'engagement_done') {
    if (evt.task_id === undefined) return state
    return finalizeTrack(state, evt.task_id)
  }

  if (t === 'decision_captured') {
    const decisionId = (evt as { decision_id?: string }).decision_id ?? `dec_${Date.now()}`
    return {
      ...state,
      journey: pushDecision(journey, {
        id: decisionId,
        title: `decision · ${decisionId}`,
      }),
    }
  }

  if (t === 'prediction_attached') {
    const horizon = (evt as { horizon_days?: number }).horizon_days ?? 30
    const falsifyIf =
      (evt as { falsification_condition?: string }).falsification_condition ?? 'condition unspecified'
    return {
      ...state,
      journey: attachPrediction(journey, {
        horizonDays: horizon,
        forecast: 'prediction recorded',
        falsifyIf,
      }),
    }
  }

  if (t === 'sentinel_event') {
    const engine = (evt as { engine?: string }).engine ?? 'sentinel'
    const summary = (evt as { summary?: string }).summary ?? 'finding flagged'
    const severity = (evt as { severity?: string }).severity ?? 'medium'
    const normSev: JourneySentinelMark['severity'] =
      severity === 'low' || severity === 'high' ? severity : 'medium'
    return {
      ...state,
      journey: pushSentinel(journey, {
        source: engine,
        headline: summary,
        severity: normSev,
      }),
    }
  }

  if (t === 'tool_call') {
    if (evt.task_id === undefined) return state
    const tool = (evt as { tool?: string }).tool ?? 'unknown'
    const inputSummary = (evt as { input_summary?: string }).input_summary
    return {
      ...state,
      toolCalls: {
        ...state.toolCalls,
        [evt.task_id]: {
          tool,
          inputSummary,
          taskId: evt.task_id,
          startedAt: Date.now(),
        },
      },
    }
  }

  if (t === 'tool_result') {
    if (evt.task_id === undefined) return state
    const existing = state.toolCalls[evt.task_id]
    if (existing === undefined) {
      // tool_result without prior tool_call — record a synthetic resolved entry.
      const tool = (evt as { tool?: string }).tool ?? 'unknown'
      const summary = (evt as { summary?: string }).summary
      return {
        ...state,
        toolCalls: {
          ...state.toolCalls,
          [evt.task_id]: {
            tool,
            taskId: evt.task_id,
            startedAt: Date.now(),
            resultSummary: summary,
            resolvedAt: Date.now(),
          },
        },
      }
    }
    const summary = (evt as { summary?: string }).summary
    return {
      ...state,
      toolCalls: {
        ...state.toolCalls,
        [evt.task_id]: {
          ...existing,
          resultSummary: summary,
          resolvedAt: Date.now(),
        },
      },
    }
  }

  if (t === 'run_done') {
    return {
      ...state,
      status: 'done',
      journey: freezeStages(journey),
    }
  }

  if (t === 'run_error') {
    const error = (evt as { error?: string }).error ?? 'run failed'
    return { ...state, status: 'error', error, journey: freezeStages(journey) }
  }

  // Unknown event — Phase 1 ignores. Phase 2 may extend.
  return state
}

// --- helpers -----------------------------------------------------------------

function classificationFromEvent(
  evt: ClassificationEvent,
  prev: JourneyClassification,
): JourneyClassification {
  const depth = (evt.depth ?? prev.depth) as JourneyClassification['depth']
  const archetypes = evt.archetypes ?? []
  return {
    ...prev,
    discipline: evt.discipline ?? prev.discipline,
    archetype: archetypes[0] ?? prev.archetype,
    depth,
    fusionMode: depth <= 2,
    metaSkills: archetypes.length > 0 ? archetypes : prev.metaSkills,
  }
}

function classificationFromCompleteEvent(
  evt: ClassificationCompleteEvent,
  prev: JourneyClassification,
): JourneyClassification {
  return {
    ...prev,
    discipline: evt.domain_path ?? prev.discipline,
    archetype: evt.archetype ?? prev.archetype,
    mode: evt.mode ?? prev.mode,
    complexity: evt.complexity ?? prev.complexity,
  }
}

function trackFromEngagement(evt: EngagementStartEvent): JourneyTrack & { _taskId?: string } {
  const archetypes = evt.archetypes ?? []
  const metaSkill = archetypes[0] ?? evt.pattern ?? 'unknown_intelligence'
  return {
    metaSkill,
    label: metaSkill.replace(/_/g, ' ').toUpperCase(),
    contribution: '',
    inFlight: true,
    instrument: evt.pattern,
    // Carry the task_id so token events can target the right track later.
    // Stored on the track object — not in the JourneyTrack type, but the
    // reducer treats it as opaque metadata.
    _taskId: evt.task_id,
  }
}

// --- block-event helpers -----------------------------------------------------

const BLOCK_TO_STAGE: Record<string, { phase: StagePhase; glyph: string; title: string }> = {
  classify: { phase: 'frame', glyph: '◯', title: 'Framing' },
  compose: { phase: 'prioritize', glyph: '◇', title: 'Assembling the committee' },
  engage: { phase: 'choose', glyph: '◇', title: 'Deliberating' },
}

function stageFromBlock(blockName: string): JourneyStage {
  const def = BLOCK_TO_STAGE[blockName] ?? { phase: 'choose' as StagePhase, glyph: '◇', title: blockName }
  return { id: `block-${blockName}`, phase: def.phase, glyph: def.glyph, title: def.title, status: 'current', tracks: [] }
}

function applyBlockStart(journey: DeliberationJourneyState, blockName: string): DeliberationJourneyState {
  const real = journey.stages.filter((s) => s.id !== 'live')
  const existing = real.find((s) => s.id === `block-${blockName}`)
  const prior = real
    .filter((s) => s.id !== `block-${blockName}`)
    .map((s) => ({ ...s, status: 'past' as StageStatus }))
  const stage = existing ? { ...existing, status: 'current' as StageStatus } : stageFromBlock(blockName)
  return { ...journey, stages: [...prior, stage] }
}

function freezeStages(journey: DeliberationJourneyState): DeliberationJourneyState {
  return {
    ...journey,
    stages: journey.stages.map((s) => ({
      ...s,
      status: 'past' as StageStatus,
      tracks: s.tracks.map((t) => ({ ...t, inFlight: false })),
    })),
  }
}

// --- track helpers -----------------------------------------------------------

function pushTrack(
  journey: DeliberationJourneyState,
  track: JourneyTrack & { _taskId?: string },
): DeliberationJourneyState {
  const idx = journey.stages.findIndex((s) => s.status === 'current')
  const target = idx >= 0 ? idx : journey.stages.length - 1
  if (target < 0) return journey
  const stages = journey.stages.map((s, i) =>
    i === target ? { ...s, tracks: [...s.tracks, track] } : s,
  )
  return { ...journey, stages }
}

function appendToken(
  state: OrchestrationSessionState,
  taskId: string,
  text: string,
): OrchestrationSessionState {
  if (text.length === 0) return state
  const buffer = (state.tokenBuffers[taskId] ?? '') + text
  const journey = state.journey
  // Live stream the token into the matching track's contribution so the
  // partner is visibly speaking, not silently accumulating. The buffer
  // is still kept so EngagementDone has the final canonical text.
  const nextJourney =
    journey === null
      ? journey
      : updateLiveStage(journey, (stage) => ({
          ...stage,
          tracks: stage.tracks.map((t) => {
            const taggedTaskId = (t as JourneyTrack & { _taskId?: string })._taskId
            if (taggedTaskId !== taskId) return t
            return { ...t, contribution: buffer, inFlight: true }
          }),
        }))
  return {
    ...state,
    tokenBuffers: { ...state.tokenBuffers, [taskId]: buffer },
    journey: nextJourney,
  }
}

function finalizeTrack(
  state: OrchestrationSessionState,
  taskId: string,
): OrchestrationSessionState {
  const journey = state.journey
  if (journey === null) return state
  const buffer = state.tokenBuffers[taskId] ?? ''
  const next = updateLiveStage(journey, (stage) => ({
    ...stage,
    tracks: stage.tracks.map((t) => {
      const taggedTaskId = (t as JourneyTrack & { _taskId?: string })._taskId
      if (taggedTaskId !== taskId) return t
      return {
        ...t,
        inFlight: false,
        contribution: buffer.length > 0 ? buffer.trim() : t.contribution,
      }
    }),
  }))
  // Drop the buffer once consumed.
  const { [taskId]: _drop, ...restBuffers } = state.tokenBuffers
  void _drop
  return { ...state, journey: next, tokenBuffers: restBuffers }
}

function pushDecision(
  journey: DeliberationJourneyState,
  decision: JourneyDecision,
): DeliberationJourneyState {
  return updateLiveStage(journey, (stage) => ({
    ...stage,
    decisions: [...(stage.decisions ?? []), decision],
  }))
}

function attachPrediction(
  journey: DeliberationJourneyState,
  prediction: JourneyPrediction,
): DeliberationJourneyState {
  return updateLiveStage(journey, (stage) => ({
    ...stage,
    prediction,
  }))
}

function pushSentinel(
  journey: DeliberationJourneyState,
  mark: JourneySentinelMark,
): DeliberationJourneyState {
  return updateLiveStage(journey, (stage) => ({
    ...stage,
    sentinel: [...(stage.sentinel ?? []), mark],
  }))
}

function updateLiveStage(
  journey: DeliberationJourneyState,
  updater: (s: JourneyStage) => JourneyStage,
): DeliberationJourneyState {
  return {
    ...journey,
    stages: journey.stages.map((s) => (s.status === 'current' ? updater(s) : s)),
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const PROJECT_ID = 'product:platform'

/** Build auth headers for backend REST calls. Reads `VITE_API_KEY` from
 *  the Vite env at build/dev time — when present, sent as `X-API-Key`
 *  to satisfy the backend's APIKeyMiddleware. When absent, no header is
 *  sent (matches dev-mode-without-key where the middleware is a no-op).
 *
 *  WS upgrade requests bypass the middleware (see
 *  `core/engine/api/middleware.py:_AUTH_SKIP_PREFIXES` note) so no
 *  header is needed on the WebSocket open. */
function authHeaders(): HeadersInit {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env
  const key = env?.VITE_API_KEY
  if (key !== undefined && key.length > 0) {
    return { 'X-API-Key': key }
  }
  return {}
}

export interface UseOrchestrationSessionOptions {
  /** Optional lens-source label for the session title (passed to the
   *  backend's create-session call). Defaults to the topic. */
  lensSourceLabel?: string
  /** Reuse an existing session id instead of creating a new one. Set
   *  this from `?session=<id>` so a page refresh in the middle of a
   *  run reconnects to the same session instead of orphaning it. */
  resumeSessionId?: string
  /** Run id to resume. When paired with `resumeSessionId`, the hook
   *  sends `{ type: 'resume', run_id, last_seq }` after the WS opens so
   *  the backend replays events with seq > last_seq. */
  resumeRunId?: string
  /** Last seq seen pre-disconnect (resume cursor). Sent as `last_seq`. */
  resumeLastSeq?: number
  /** Opt-in: on unexpected WS drop while still streaming, the hook
   *  schedules an exponential-backoff reconnect (1s, 2s, 4s, 8s,
   *  capped at 30s) for up to `maxReconnectAttempts` (default 5).
   *  The reconnect reuses the same session_id and triggers the
   *  backend's replay protocol (cursor: `last_seq`) when mid-run.
   *  Default false to preserve single-shot test semantics. */
  autoReconnect?: boolean
  /** Maximum number of consecutive reconnect attempts before giving
   *  up. Counter resets to 0 on every successful ws_open. */
  maxReconnectAttempts?: number
}

const RECONNECT_BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000] as const

/** Pure helper — given the attempt number (1-indexed), return the
 *  delay before the next reconnect attempt. Exported for tests. */
export function reconnectBackoffMs(attempt: number): number {
  const idx = Math.min(Math.max(0, attempt - 1), RECONNECT_BACKOFF_MS.length - 1)
  return RECONNECT_BACKOFF_MS[idx]
}

/**
 * Lifecycle-scoped live ACE session.
 *
 * - Pass a topic string → REST creates session → WS opens → events flow.
 * - Pass `null` → idle (returns null journey).
 * - Changing the topic tears down the prior WS and starts fresh.
 */
/** The wire frame for steering the room mid-deliberation — the same `{type:'message'}` frame the initial
 *  topic uses, so a steer is just another turn in the session. Returns null for empty/whitespace input
 *  (nothing to send). Pure, so the steer contract is testable without a socket. */
export function steerFrame(text: string): string | null {
  const body = text.trim()
  if (body.length === 0) return null
  return JSON.stringify({ type: 'message', content: body })
}

/** The live session, plus `steer(text)` to send the partner a mid-deliberation message. */
export type OrchestrationSession = OrchestrationSessionState & {
  /** Send a steer over the open socket. Returns false if there's no open session or the text is empty. */
  steer: (text: string) => boolean
}

export function useOrchestrationSession(
  topic: string | null,
  opts: UseOrchestrationSessionOptions = {},
): OrchestrationSession {
  const [state, dispatch] = useReducer(reducer, initialState)
  // The currently-open socket, so `steer` can send after the initial kickoff. Set when a socket opens in
  // either the main or the reconnect effect; cleared when that same socket tears down.
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (topic === null || topic.trim().length === 0) return

    let cancelled = false
    let ws: WebSocket | null = null

    dispatch({ type: 'reset', topic })

    void (async () => {
      try {
        // Resume path: caller already has a session id (e.g. from
        // `?session=<id>` in the URL). Skip POST /canvas/sessions and
        // just reconnect the WS — the backend's replay protocol fills
        // in missed events when `resumeRunId` is also supplied.
        let sessionId = opts.resumeSessionId
        if (sessionId === undefined) {
          const title = opts.lensSourceLabel
            ? `${opts.lensSourceLabel} · ${topic.slice(0, 80)}`
            : topic.slice(0, 120)
          const resp = await fetch('/canvas/sessions', {
            method: 'POST',
            headers: {
              'content-type': 'application/json',
              ...authHeaders(),
            },
            body: JSON.stringify({ project_id: PROJECT_ID, title }),
          })
          if (!resp.ok) {
            dispatch({ type: 'ws_error', error: `session create failed (${resp.status})` })
            return
          }
          const session = (await resp.json()) as { id?: string }
          if (cancelled || session.id === undefined) return
          sessionId = session.id
        }

        dispatch({ type: 'session_created', sessionId })

        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const url = `${proto}//${window.location.host}/canvas/sessions/${encodeURIComponent(sessionId)}/orchestration`
        ws = new WebSocket(url)
        wsRef.current = ws

        ws.addEventListener('open', () => {
          if (cancelled || ws === null) return
          dispatch({ type: 'ws_open' })
          // Resume vs fresh kick-off:
          //   - resumeRunId → ask backend to replay events since last_seq
          //     (it'll send replay_start, a stream of past events, then
          //     replay_done). M3: sends last_seq (per-event cursor).
          //   - Otherwise → fire the user message as a new run.
          if (opts.resumeSessionId !== undefined && opts.resumeRunId !== undefined) {
            ws.send(
              JSON.stringify({
                type: 'resume',
                run_id: opts.resumeRunId,
                last_seq: opts.resumeLastSeq ?? 0,
              }),
            )
          } else {
            ws.send(JSON.stringify({ type: 'message', content: topic }))
          }
        })
        ws.addEventListener('message', (e: MessageEvent<string>) => {
          if (cancelled) return
          try {
            const evt = JSON.parse(e.data) as WsInbound
            dispatch({ type: 'remote', event: evt, topic })
          } catch {
            // malformed frame — ignore
          }
        })
        ws.addEventListener('error', () => {
          if (cancelled) return
          dispatch({ type: 'ws_error', error: 'websocket error' })
        })
        ws.addEventListener('close', () => {
          if (cancelled) return
          dispatch({ type: 'ws_close' })
        })
      } catch (err) {
        if (cancelled) return
        dispatch({ type: 'ws_error', error: err instanceof Error ? err.message : String(err) })
      }
    })()

    return () => {
      cancelled = true
      if (wsRef.current === ws) wsRef.current = null
      ws?.close()
    }
  }, [topic, opts.lensSourceLabel, opts.resumeSessionId, opts.resumeRunId, opts.resumeLastSeq])

  // ---------------------------------------------------------------------------
  // Auto-reconnect (opt-in): schedule exponential-backoff retries when the
  // WS drops mid-run. Two effects compose to avoid a setState loop:
  //   1. Scheduler — watches status='error' + retryable conditions, sets a
  //      timer to dispatch 'reconnect_scheduled' after backoff.
  //   2. Connector — watches status='reconnecting' + sessionId/runId/lastTaskId,
  //      opens a fresh WS with the resume frame. ws_open transitions back to
  //      streaming and zeroes the attempt counter; another close re-enters
  //      the scheduler with attempt + 1.
  // ---------------------------------------------------------------------------

  const autoReconnect = opts.autoReconnect ?? false
  const maxAttempts = opts.maxReconnectAttempts ?? 5

  // Scheduler effect
  useEffect(() => {
    if (!autoReconnect) return
    if (state.status !== 'error') return
    if (state.lastTaskId === null) return // not mid-run
    if (state.sessionId === null) return
    if (state.runId === null) return
    if (state.reconnectAttempt >= maxAttempts) {
      dispatch({
        type: 'reconnect_exhausted',
        error: `reconnect exhausted after ${maxAttempts} attempts — refresh to resume`,
      })
      return
    }
    const delayMs = reconnectBackoffMs(state.reconnectAttempt + 1)
    const timer = setTimeout(() => dispatch({ type: 'reconnect_scheduled' }), delayMs)
    return () => clearTimeout(timer)
  }, [
    autoReconnect,
    maxAttempts,
    state.status,
    state.lastTaskId,
    state.sessionId,
    state.runId,
    state.reconnectAttempt,
  ])

  // Connector effect
  useEffect(() => {
    if (state.status !== 'reconnecting') return
    if (state.sessionId === null) return
    if (state.runId === null) return
    if (state.lastTaskId === null) return

    let cancelled = false
    let ws: WebSocket | null = null

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}/canvas/sessions/${encodeURIComponent(state.sessionId)}/orchestration`
    ws = new WebSocket(url)
    wsRef.current = ws

    ws.addEventListener('open', () => {
      if (cancelled || ws === null) return
      dispatch({ type: 'ws_open' })
      ws.send(
        JSON.stringify({
          type: 'resume',
          run_id: state.runId,
          last_seq: state.lastSeq ?? 0,
        }),
      )
    })
    ws.addEventListener('message', (e: MessageEvent<string>) => {
      if (cancelled) return
      try {
        const evt = JSON.parse(e.data) as WsInbound
        dispatch({ type: 'remote', event: evt, topic: topic ?? '' })
      } catch {
        /* malformed — ignore */
      }
    })
    ws.addEventListener('error', () => {
      if (cancelled) return
      dispatch({ type: 'ws_error', error: 'reconnect failed' })
    })
    ws.addEventListener('close', () => {
      if (cancelled) return
      dispatch({ type: 'ws_close' })
    })

    return () => {
      cancelled = true
      if (wsRef.current === ws) wsRef.current = null
      ws?.close()
    }
    // Only re-run when status enters 'reconnecting' (driven by the
    // scheduler). The other deps are read but not part of the trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status, state.reconnectAttempt, state.lastSeq])

  // Steer the room mid-deliberation: send the partner another turn over the open socket. Stable identity
  // (useCallback) so consumers can pass it straight to a composer without re-render churn. No-op (returns
  // false) when there's no open session — e.g. demo mode, or before the socket connects.
  const steer = useCallback((text: string): boolean => {
    const frame = steerFrame(text)
    const ws = wsRef.current
    if (frame === null || ws === null || ws.readyState !== WebSocket.OPEN) return false
    ws.send(frame)
    return true
  }, [])

  return { ...state, steer }
}
