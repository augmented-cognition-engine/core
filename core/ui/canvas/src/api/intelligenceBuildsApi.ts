import { clearToken, getToken } from './auth'
import type { IntelligenceResourcePage } from './intelligenceResourcesApi'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const BUILD_AUTHORITY_GRANT_REF =
  import.meta.env.VITE_INTELLIGENCE_BUILD_AUTHORITY_GRANT_REF ??
  'authority_grant:atrium-intelligence-build'

export interface IntelligenceBuildStartInput {
  readonly profile_id: string
  readonly subject: string
  readonly outcome_id: string
  readonly source_group_ids: readonly string[]
  readonly cadence_id: string
}

export interface IntelligenceBuildResult {
  readonly contract: 'ace.http.intelligence-build-result/v1alpha1'
  readonly build_id: string
  readonly request_digest: string
  readonly product_id: string
  readonly actor_ref: string
  readonly accepted_at: string
  readonly resource_page: IntelligenceResourcePage
}

export class IntelligenceBuildApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'IntelligenceBuildApiError'
    this.status = status
  }
}

function requestId(): string {
  if (typeof crypto.randomUUID === 'function') return `atrium-request:${crypto.randomUUID()}`
  return `atrium-request:${Date.now().toString(36)}`
}

async function postBuild(token: string, input: IntelligenceBuildStartInput): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/start`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      authority_grant_ref: BUILD_AUTHORITY_GRANT_REF,
      client_request_id: requestId(),
      ...input,
      requested_at: new Date().toISOString(),
    }),
  })
}

export async function startIntelligenceBuild(input: IntelligenceBuildStartInput): Promise<IntelligenceBuildResult> {
  let token = await getToken()
  let response = await postBuild(token, input)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postBuild(token, input)
  }
  if (!response.ok) {
    let detail = `ACE could not start this Intelligence build (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as IntelligenceBuildResult
}
