// frontend/src/api/canvasApi.ts
/// <reference types="vite/client" />
import type {
  CanvasSession,
  CanvasTimeline,
  CompileResponse,
  ContributionBody,
  ContributionResult,
  CreateSessionBody,
  JourneyForkTrace,
  PlaceArtifactBody,
  RequestFrameworkBody,
  RecordDecisionBody,
  Prediction,
  PredictionOutcome,
  RespondBody,
  RespondResult,
} from '../types/canvas'

export interface ProactiveLineData {
  line: string
  source: string
  topic: string | null
  source_artifact_id: string
}

export interface BriefingLatest {
  content: string | Record<string, unknown> | null
  period: string
  metrics: Record<string, unknown>
  created_at: string | null
}

export interface PulseDomain {
  domain_path: string | null
  insight_count: number
}

export interface PulseData {
  insights: number
  specialties: number
  connections: number
  domains: PulseDomain[]
}

export interface Decision {
  id: string
  title: string
  decision_type: string
  rationale: string
  created_at: string
}

export interface Recommendation {
  id: string
  type: string
  title: string
  description: string
  action: string
  action_prompt: string
  severity: 'high' | 'medium' | 'low'
  source: string
  related_files: string[]
}

import { getToken, clearToken } from './auth'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

function apiHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...extra }
  if (API_KEY) h['X-API-Key'] = API_KEY
  return h
}

// Authenticated GET — exchanges API key for JWT if needed, retries once on 401.
export async function authGet<T>(path: string): Promise<T> {
  const token = await getToken()
  const res = await fetch(`${BASE}${path}`, {
    headers: { ...apiHeaders(), Authorization: `Bearer ${token}` },
  })
  if (res.status === 401) {
    clearToken()
    const fresh = await getToken()
    const retry = await fetch(`${BASE}${path}`, {
      headers: { ...apiHeaders(), Authorization: `Bearer ${fresh}` },
    })
    if (!retry.ok) throw new Error(`GET ${path} → ${retry.status}`)
    return retry.json()
  }
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json()
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: apiHeaders() })
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json()
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`)
  return res.json()
}

export const canvasApi = {
  createSession: (body: CreateSessionBody) =>
    post<CanvasSession>('/canvas/sessions', body),

  getSession: (sessionId: string) =>
    get<CanvasSession>(`/canvas/sessions/${sessionId}`),

  placeArtifact: (sessionId: string, body: PlaceArtifactBody) =>
    post<unknown>(`/canvas/sessions/${sessionId}/artifacts`, body),

  requestFramework: (sessionId: string, body: RequestFrameworkBody) =>
    post<unknown>(`/canvas/sessions/${sessionId}/framework`, body),

  requestContribution: (sessionId: string, body: ContributionBody) =>
    post<ContributionResult>(`/canvas/sessions/${sessionId}/contribution`, body),

  respond: (sessionId: string, body: RespondBody) =>
    post<RespondResult>(`/canvas/sessions/${sessionId}/respond`, body),

  recordDecision: (sessionId: string, body: RecordDecisionBody) =>
    post<{ decision_id: string }>(`/canvas/sessions/${sessionId}/decision`, body),

  getPredictionForDecision: (decisionId: string) =>
    get<{ prediction: Prediction; outcome: PredictionOutcome | null }>(
      `/canvas/decisions/${encodeURIComponent(decisionId)}/prediction`,
    ),

  getTimeline: (sessionId: string) =>
    get<CanvasTimeline>(`/canvas/sessions/${sessionId}/timeline`),

  /** Compute the 'paths not taken' fork for a logged run at a checkpoint (on-demand — expensive). */
  forkReasoning: (
    sessionId: string,
    body: { run_id: string; checkpoint_seq: number; with_capability_lens?: boolean },
  ) => post<JourneyForkTrace>(`/canvas/sessions/${sessionId}/fork`, body),

  patchDecision: (decisionId: string, body: { what_it_led_to: string }) =>
    patch<Record<string, unknown>>(`/canvas/decisions/${decisionId}`, body),

  compileSession: (sessionId: string) =>
    post<CompileResponse>(`/canvas/sessions/${sessionId}/compile`, {}),

  getProactiveLine: (productId: string) =>
    authGet<ProactiveLineData | null>(`/proactive/${encodeURIComponent(productId)}/current`),

  getBriefingLatest: (productId: string) =>
    authGet<BriefingLatest>(`/briefings/latest?product=${encodeURIComponent(productId)}`),

  listSessions: (projectId?: string, limit = 10) =>
    get<CanvasSession[]>(
      `/canvas/sessions${projectId ? `?project_id=${encodeURIComponent(projectId)}&limit=${limit}` : `?limit=${limit}`}`
    ),

  getPulseData: (productId: string) =>
    authGet<PulseData>(`/portal/pulse?product=${encodeURIComponent(productId)}`),

  getRecommendations: (productId: string, limit = 5) =>
    authGet<{ recommendations: Recommendation[] }>(
      `/recommendations?product=${encodeURIComponent(productId)}&limit=${limit}`
    ),

  getDecisions: (productId: string, limit = 20) =>
    authGet<{ decisions: Decision[] }>(
      `/decisions?product=${encodeURIComponent(productId)}&limit=${limit}`
    ),

  getRecentProactiveLines: (productId: string, n = 8) =>
    authGet<RecentProactiveLine[]>(`/proactive/${encodeURIComponent(productId)}/recent?n=${n}`),

  getAttention: (productId: string) =>
    authGet<{ items: AttentionItem[] }>(`/portal/attention?product=${encodeURIComponent(productId)}`),

  patchSession: (sessionId: string, body: { title: string }) =>
    patch<CanvasSession>(`/canvas/sessions/${encodeURIComponent(sessionId)}`, body),

  classifySession: (sessionId: string) =>
    post<{
      discipline: string
      archetypes: { archetype: string; color_hint: string; idle_zone_hint: string }[]
      specialties: string[]
    }>(`/canvas/sessions/${encodeURIComponent(sessionId)}/classify`, {}),
}

export interface RecentProactiveLine {
  line: string
  source: string
  topic: string | null
  severity: number
  priority?: 'HIGH' | 'MEDIUM' | 'LOW' | null
  generated_at?: string
}

export interface AttentionItem {
  type: string
  id: string
  title: string
  detail?: string
  link?: string
}
