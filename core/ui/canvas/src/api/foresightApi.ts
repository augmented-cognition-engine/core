// frontend/src/api/foresightApi.ts
/// <reference types="vite/client" />
const BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

function headers(): Record<string, string> {
  const h: Record<string, string> = {}
  if (API_KEY) h['X-API-Key'] = API_KEY
  return h
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: headers() })
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { ...headers(), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json()
}

export interface RolloutBranch {
  path: string[]
  terminal_score: number
  top_risk: string
  state_override: Record<string, number>
  authored_by_archetype: string
}

export interface RolloutScenario {
  id?: string
  candidate: string
  product?: string
  branches: RolloutBranch[]
  best_path: string[]
  created_at: string
}

export interface CalibrationOutcome {
  id: string
  prediction_id: string
  decision_id: string
  decision_title: string
  archetype: string
  discipline: string
  calibration_score: number
  predicted_deltas: Record<string, number>
  actual_deltas: Record<string, number>
  closed_at: string
}

export const foresightApi = {
  getRollouts: (productId: string) =>
    get<{ scenarios: RolloutScenario[] }>(`/foresight/${encodeURIComponent(productId)}/rollouts`),

  generateRollout: (productId: string, candidate: string) =>
    post<RolloutScenario>(`/foresight/${encodeURIComponent(productId)}/rollouts/generate`, {
      candidate_decision: candidate,
    }),

  getCalibration: (productId: string, limit = 20) =>
    get<{ outcomes: CalibrationOutcome[] }>(
      `/foresight/${encodeURIComponent(productId)}/calibration?limit=${limit}`,
    ),
}
