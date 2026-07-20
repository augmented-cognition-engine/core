// frontend/src/api/sentinelsApi.ts
/// <reference types="vite/client" />
import { getToken, clearToken } from './auth'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

export interface SentinelLastRun {
  status: 'completed' | 'running' | 'failed' | string
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  results_summary: string | null
  cost: number
}

export interface Sentinel {
  name: string
  cron: string
  description: string
  schedule_label: string
  last_run: SentinelLastRun | null
}

export interface SentinelStatus {
  sentinels: Sentinel[]
  counts: {
    total: number
    ran_in_last_24h: number
    failed_in_last_24h: number
    never_run_for_this_product: number
  }
}

function apiHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...extra }
  if (API_KEY) h['X-API-Key'] = API_KEY
  return h
}

async function authGet<T>(path: string): Promise<T> {
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

export const sentinelsApi = {
  getStatus: (productId: string = 'product:platform') =>
    authGet<SentinelStatus>(`/sentinels/status?product_id=${encodeURIComponent(productId)}`),
}
