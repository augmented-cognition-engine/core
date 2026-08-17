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

export interface DomainPackMetadata {
  readonly pack_id: string
  readonly version: string
  readonly display_name: string
  readonly description: string | null
}

export interface DomainPackModuleRef {
  readonly module_id: string
  readonly contract: string
  readonly resource_id: string
  readonly depends_on: readonly string[]
}

export interface DomainPackOverlaySlot {
  readonly slot_id: string
  readonly value_kind: string
  readonly required: boolean
}

export interface DomainPackManifest {
  readonly contract: string
  readonly metadata: DomainPackMetadata
  readonly resources: readonly { readonly resource_id: string; readonly path: string; readonly digest: string }[]
  readonly modules: readonly DomainPackModuleRef[]
  readonly capability_requirements: readonly { readonly requirement_id: string; readonly capability: string; readonly contract: string }[]
  readonly authority_requests: readonly { readonly request_id: string; readonly authority: string }[]
  readonly overlay_slots: readonly DomainPackOverlaySlot[]
}

export interface InstalledDomainPackPreview {
  readonly distribution: string
  readonly distribution_version: string
  readonly manifest_resource_path: string
  readonly manifest_digest: string
  readonly manifest: DomainPackManifest
  readonly lifecycle: readonly DomainPackLifecycleCapability[]
}

export type DomainPackLifecycleAvailability = 'available' | 'contract_only' | 'not_exposed'

export interface DomainPackLifecycleCapability {
  readonly capability_id: 'installed_material' | 'reviewed_customization' | 'upgrade_discovery' | 'activation_history' | 'rollback'
  readonly label: string
  readonly availability: DomainPackLifecycleAvailability
  readonly contract_refs: readonly string[]
  readonly endpoint: string | null
  readonly boundary: string
}

export interface InstalledDomainPackCatalog {
  readonly contract: 'ace.http.installed-domain-pack-catalog/v1alpha1'
  readonly packs: readonly InstalledDomainPackPreview[]
}

export type IntelligenceConsumerAvailability = 'available' | 'contract_only' | 'navigation_only' | 'not_exposed'

export interface IntelligenceConsumerInterface {
  readonly interface_id: string
  readonly label: string
  readonly kind: 'api' | 'mcp' | 'sdk' | 'subscription' | 'stream' | 'webhook' | 'schema' | 'handoff'
  readonly availability: IntelligenceConsumerAvailability
  readonly version: string | null
  readonly endpoint: string | null
  readonly contract_refs: readonly string[]
  readonly operations: readonly string[]
  readonly permission_boundary: string
  readonly provenance_boundary: string
  readonly delivery_boundary: string
}

export interface IntelligenceConsumerCatalog {
  readonly contract: 'ace.http.intelligence-consumer-catalog/v1alpha1'
  readonly interfaces: readonly IntelligenceConsumerInterface[]
  readonly unresolved_dependencies: readonly string[]
}

export interface DomainPackActivationOverlayValue {
  readonly slot_id: string
  readonly value_json: string
}

export interface DomainPackActivationCompiledOverlay {
  readonly contract: string
  readonly overlay_id: string
  readonly version: string
  readonly pack_id: string
  readonly pack_version: string
  readonly pack_digest: string
  readonly values: readonly DomainPackActivationOverlayValue[]
  readonly compiled_overlay_id: string | null
  readonly overlay_digest: string | null
}

export interface DomainPackActivationCompiledPackRef {
  readonly pack_id: string
  readonly pack_version: string
  readonly compiled_pack_id: string
  readonly pack_digest: string
}

export type DomainPackActivationPlanAction =
  | 'initial_activation'
  | 'upgrade'
  | 'suspend'
  | 'reactivate'
  | 'rollback'
  | 'retire'

export type DomainPackActivationRuntimeState = 'active' | 'suspended' | 'retired'

export interface DomainPackActivationRevision {
  readonly revision: number
  readonly revision_id: string
  readonly revision_digest: string
  readonly action: DomainPackActivationPlanAction
  readonly state: DomainPackActivationRuntimeState
  readonly pack: DomainPackActivationCompiledPackRef
  readonly overlay: DomainPackActivationCompiledOverlay
  readonly plan_id: string
  readonly plan_digest: string
  readonly approval_receipt_ref: string
  readonly approval_receipt_digest: string
  readonly actor_ref: string
  readonly occurred_at: string
  readonly commit_receipt_id: string
  readonly commit_receipt_digest: string
  readonly committed_at: string
}

export interface DomainPackActivationHistory {
  readonly contract: 'ace.http.domain-pack-activation-history/v1alpha1'
  readonly authority_stage: 'historical_reference'
  readonly live_authority: false
  readonly product_id: string
  readonly activation_key: string
  readonly activation_id: string
  readonly current: DomainPackActivationRevision
  readonly history: readonly DomainPackActivationRevision[]
}

export class IntelligenceCatalogApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'IntelligenceCatalogApiError'
    this.status = status
  }
}

async function getCatalog(token: string): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/catalog/profiles`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

async function getCatalogPath(token: string, path: 'packs' | 'consumers'): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/catalog/${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

async function queryCatalogPath<T>(path: 'packs' | 'consumers', label: string): Promise<T> {
  let token = await getToken()
  let response = await getCatalogPath(token, path)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await getCatalogPath(token, path)
  }
  if (!response.ok) throw new Error(`${label} is unavailable (${response.status}).`)
  return (await response.json()) as T
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

export function queryInstalledDomainPackCatalog(): Promise<InstalledDomainPackCatalog> {
  return queryCatalogPath<InstalledDomainPackCatalog>('packs', 'Installed Domain Pack catalog')
}

export function queryIntelligenceConsumerCatalog(): Promise<IntelligenceConsumerCatalog> {
  return queryCatalogPath<IntelligenceConsumerCatalog>('consumers', 'Intelligence consumer catalog')
}

async function getPackActivationHistory(token: string, activationKey: string): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/catalog/packs/activations/${encodeURIComponent(activationKey)}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

/**
 * Reads one exact Pack activation by its exact activation key. The caller must supply the
 * real activation key; this never infers it from an installed Pack ID.
 */
export async function queryDomainPackActivationHistory(activationKey: string): Promise<DomainPackActivationHistory> {
  let token = await getToken()
  let response = await getPackActivationHistory(token, activationKey)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await getPackActivationHistory(token, activationKey)
  }
  if (!response.ok) {
    let detail = `Pack activation history is unavailable (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceCatalogApiError(response.status, detail)
  }
  return (await response.json()) as DomainPackActivationHistory
}
