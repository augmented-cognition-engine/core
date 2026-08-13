import { clearToken, getToken } from './auth'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export interface InstalledIntelligenceProfile {
  readonly distribution: string
  readonly distribution_version: string
  readonly resource_path: string
  readonly profile: unknown
}

export interface InstalledIntelligenceCatalog {
  readonly contract: 'ace.http.installed-intelligence-catalog/v1alpha1'
  readonly profiles: readonly InstalledIntelligenceProfile[]
}

async function getCatalog(token: string): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/catalog/profiles`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function queryInstalledIntelligenceCatalog(): Promise<InstalledIntelligenceCatalog> {
  let token = await getToken()
  let response = await getCatalog(token)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await getCatalog(token)
  }
  if (!response.ok) throw new Error(`Installed Intelligence catalog is unavailable (${response.status}).`)
  return (await response.json()) as InstalledIntelligenceCatalog
}
