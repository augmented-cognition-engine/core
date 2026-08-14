import { clearToken, getToken } from './auth'
import type { IntelligenceResourcePage } from './intelligenceResourcesApi'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const BUILD_AUTHORITY_GRANT_REF =
  import.meta.env.VITE_INTELLIGENCE_BUILD_AUTHORITY_GRANT_REF ??
  'authority_grant:atrium-intelligence-build'
const RESOURCE_AUTHORITY_GRANT_REF =
  import.meta.env.VITE_INTELLIGENCE_RESOURCE_AUTHORITY_GRANT_REF ??
  'authority_grant:atrium-observe-read'
const APPROVED_ONBOARDING_EFFECTS = [
  'connect_sources',
  'map_concepts',
  'activate_watch',
  'create_first_brief',
] as const

export interface IntelligenceBuildStartInput {
  readonly profile_id: string
  readonly subject: string
  readonly outcome_id: string
  readonly source_group_ids: readonly string[]
  readonly cadence_id: string
}

export interface IntelligenceBuildPlanSelectionInput {
  readonly profile_id: string
  readonly profile_digest: string
  readonly subject: string
  readonly outcome_id: string
  readonly source_group_ids: readonly string[]
  readonly cadence_id: string
}

export interface IntelligenceBuildPlanPrepareInput extends IntelligenceBuildPlanSelectionInput {
  readonly client_request_id: string
  readonly proposed_effects: typeof APPROVED_ONBOARDING_EFFECTS
  readonly requested_at: string
}

export interface IntelligenceBuildPlanReviewSource {
  readonly selection: {
    readonly contract: 'ace.application.recorded-source-selection-reference/v1alpha1'
    readonly source_group_id: string
    readonly selection_id: string
    readonly selection_digest: string
  }
  readonly label: string
  readonly evidence_role: string
  readonly source_uri: string
  readonly source_definition_ref: string
  readonly entity_type_id: string
  readonly entity_ref: string
  readonly observed_at: string
}

export interface IntelligenceBuildPlanReviewConcept {
  readonly entity_type_id: string
  readonly entity_ref: string
  readonly display_name: string
  readonly source_selections: readonly IntelligenceBuildPlanReviewSource['selection'][]
}

export interface IntelligenceBuildPlanReviewWatch {
  readonly detector_id: string
  readonly detector_family: 'numeric_delta' | 'categorical_transition'
  readonly entity_type_id: string
  readonly entity_refs: readonly string[]
  readonly attribute_id: string
  readonly change_rule: string
  readonly shift_type: string
  readonly signal_type: string
  readonly cadence_id: string
  readonly cadence_label: string
}

export interface IntelligenceBuildPlanReviewEffect {
  readonly effect: typeof APPROVED_ONBOARDING_EFFECTS[number]
  readonly label: string
  readonly what: string
  readonly why: string
  readonly how: string
  readonly when: string
  readonly unknowns: readonly string[]
}

export interface IntelligenceBuildPlanReviewProjection {
  readonly contract: 'ace.application.intelligence-build-review-projection/v1alpha1'
  readonly request_id: string
  readonly request_digest: string
  readonly profile_id: string
  readonly profile_digest: string
  readonly subject: string
  readonly outcome_id: string
  readonly outcome_label: string
  readonly sources: readonly IntelligenceBuildPlanReviewSource[]
  readonly concepts: readonly IntelligenceBuildPlanReviewConcept[]
  readonly watches: readonly IntelligenceBuildPlanReviewWatch[]
  readonly cadence_id: string
  readonly cadence_label: string
  readonly cadence_description: string
  readonly effects: readonly IntelligenceBuildPlanReviewEffect[]
  readonly projection_id: string
  readonly projection_digest: string
}

export interface IntelligenceBuildPlan {
  readonly contract: 'ace.application.intelligence-build-plan/v1alpha2' | 'ace.application.intelligence-build-plan/v1alpha3'
  readonly request: IntelligenceBuildPlanPrepareInput & {
    readonly contract: 'ace.application.intelligence-build-plan-request/v1alpha2' | 'ace.application.intelligence-build-plan-request/v1alpha3'
    readonly product_id: string
    readonly actor_ref: string
    readonly request_id: string
    readonly request_digest: string
  }
  readonly recorded_source_selection_refs: readonly IntelligenceBuildPlanReviewSource['selection'][]
  readonly review_projection: IntelligenceBuildPlanReviewProjection | null
  readonly plan_id: string
  readonly plan_digest: string
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

export function createIntelligenceBuildPlanPrepareInput(
  input: IntelligenceBuildPlanSelectionInput,
): IntelligenceBuildPlanPrepareInput {
  return {
    ...input,
    client_request_id: requestId(),
    proposed_effects: APPROVED_ONBOARDING_EFFECTS,
    requested_at: new Date().toISOString(),
  }
}

async function postPlan(token: string, input: IntelligenceBuildPlanPrepareInput): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/prepare`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
  })
}

export async function prepareIntelligenceBuild(input: IntelligenceBuildPlanPrepareInput): Promise<IntelligenceBuildPlan> {
  let token = await getToken()
  let response = await postPlan(token, input)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postPlan(token, input)
  }
  if (!response.ok) {
    let detail = `ACE could not prepare this exact Intelligence plan (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  const plan = (await response.json()) as IntelligenceBuildPlan
  if (plan.review_projection === null || plan.review_projection === undefined) {
    throw new IntelligenceBuildApiError(409, 'ACE returned a plan without exact review material.')
  }
  return plan
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
      resource_authority_grant_ref: RESOURCE_AUTHORITY_GRANT_REF,
      approved_effects: APPROVED_ONBOARDING_EFFECTS,
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
