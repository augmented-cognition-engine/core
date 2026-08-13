/// <reference types="vite/client" />

import { clearToken, getToken } from './auth'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const AUTHORITY_GRANT_REF =
  import.meta.env.VITE_INTELLIGENCE_AUTHORITY_GRANT_REF ??
  'authority_grant:atrium-observe-read'

export const INTELLIGENCE_RESOURCE_KINDS = [
  'connection',
  'source',
  'source_health',
  'entity',
  'observation',
  'signal',
  'shift',
  'case',
  'brief',
  'monitor',
  'subscription',
  'agent',
  'decision',
  'action',
  'outcome',
  'feedback',
  'evidence_lineage',
  'uncertainty',
  'conflict',
  'semantic_revision',
  'context_manifest',
  'memory_use',
] as const

export type IntelligenceResourceKind = (typeof INTELLIGENCE_RESOURCE_KINDS)[number]
export type IntelligenceResourceAvailability = 'available' | 'degraded' | 'tombstoned'

export interface IntelligenceResourceReference {
  contract: string
  product_id: string
  resource_kind: IntelligenceResourceKind
  resource_id: string
  resource_digest: string
  resource_contract: string
  revision: number
  as_of: string
  available_at: string
}

export interface IntelligenceResourceRecord {
  contract: string
  reference: IntelligenceResourceReference
  availability: IntelligenceResourceAvailability
  title: string
  summary: string | null
  subject_refs: string[]
  provenance: IntelligenceResourceReference[]
  supersedes: IntelligenceResourceReference | null
  payload: unknown
  degraded_reason_refs: string[]
}

export interface IntelligenceResourceCursor {
  contract: string
  query_id: string
  after_available_at: string
  after_resource_kind: IntelligenceResourceKind
  after_resource_id: string
  after_revision: number
  cursor_id: string
  cursor_digest: string
}

export interface IntelligenceResourcePage {
  contract: string
  query_id: string
  query_digest: string
  product_id: string
  actor_ref: string
  as_of: string
  available_at: string
  evaluated_at: string
  state: 'complete' | 'degraded'
  items: IntelligenceResourceRecord[]
  next_cursor: IntelligenceResourceCursor | null
  degraded_reason_refs: string[]
  page_id: string
  page_digest: string
}

export class IntelligenceResourceApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'IntelligenceResourceApiError'
    this.status = status
  }
}

async function postPage(
  token: string,
  kinds: readonly IntelligenceResourceKind[],
  asOf: string,
  availableAt: string,
  cursor: IntelligenceResourceCursor | null,
): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/resources/query`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      authority_grant_ref: AUTHORITY_GRANT_REF,
      resource_kinds: kinds,
      subject_refs: [],
      as_of: asOf,
      available_at: availableAt,
      page_size: 200,
      cursor,
    }),
  })
}

async function responseError(response: Response): Promise<IntelligenceResourceApiError> {
  let detail = `Intelligence resources are unavailable (${response.status}).`
  try {
    const body = (await response.json()) as { detail?: string }
    if (typeof body.detail === 'string') detail = body.detail
  } catch {
    // Preserve the bounded status-only message when the response is not JSON.
  }
  return new IntelligenceResourceApiError(response.status, detail)
}

export async function queryIntelligenceResources(
  kinds: readonly IntelligenceResourceKind[] = INTELLIGENCE_RESOURCE_KINDS,
): Promise<IntelligenceResourcePage> {
  const availableAt = new Date().toISOString()
  const asOf = '2000-01-01T00:00:00.000Z'
  let cursor: IntelligenceResourceCursor | null = null
  let token = await getToken()
  let firstPage: IntelligenceResourcePage | null = null
  const items: IntelligenceResourceRecord[] = []
  const degradedReasons = new Set<string>()

  for (let pageNumber = 0; pageNumber < 10; pageNumber += 1) {
    let response = await postPage(token, kinds, asOf, availableAt, cursor)
    if (response.status === 401) {
      clearToken()
      token = await getToken()
      response = await postPage(token, kinds, asOf, availableAt, cursor)
    }
    if (!response.ok) throw await responseError(response)

    const page = (await response.json()) as IntelligenceResourcePage
    if (firstPage === null) firstPage = page
    items.push(...page.items)
    page.degraded_reason_refs.forEach((reason) => degradedReasons.add(reason))
    cursor = page.next_cursor
    if (cursor === null) {
      return {
        ...firstPage,
        items,
        state: degradedReasons.size > 0 ? 'degraded' : firstPage.state,
        degraded_reason_refs: [...degradedReasons].sort(),
        next_cursor: null,
      }
    }
  }

  if (firstPage === null) {
    throw new IntelligenceResourceApiError(503, 'No Intelligence resource page was returned.')
  }
  return {
    ...firstPage,
    items,
    state: 'degraded',
    degraded_reason_refs: [
      ...degradedReasons,
      'degraded_reason:atrium-pagination-limit',
    ].sort(),
    next_cursor: cursor,
  }
}
