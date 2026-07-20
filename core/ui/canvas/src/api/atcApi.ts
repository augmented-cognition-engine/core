// frontend/src/api/atcApi.ts
/// <reference types="vite/client" />
import { getToken, clearToken } from './auth'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

export interface AtcFlight {
  id: string
  title?: string
  source?: string
  source_id?: string
  capabilities?: string[]
  files_predicted?: string[]
  status?: string
  priority?: number
  blocked_by?: string
  blocker_title?: string
  blocker_source?: string
  cleared_at?: string
  landed_at?: string
  created_at?: string
  updated_at?: string
}

export interface CapabilitySector {
  slug: string
  name: string
  status: string
  flights: { flight_id: string; title: string; source: string; status: string }[]
  flight_count: number
}

export interface RadarData {
  active: AtcFlight[]
  holding: AtcFlight[]
  landing: AtcFlight[]
  recent_landed: AtcFlight[]
  counts: { active: number; holding: number; landing: number }
}

export interface CapabilitiesData {
  sectors: CapabilitySector[]
  total: number
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

export const atcApi = {
  getRadar: () => authGet<RadarData>('/atc/radar'),
  getCapabilities: () => authGet<CapabilitiesData>('/atc/capabilities'),
}
