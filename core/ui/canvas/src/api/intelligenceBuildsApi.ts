import { clearToken, getToken } from './auth'
import type { IntelligenceResourceCursor, IntelligenceResourceKind, IntelligenceResourcePage } from './intelligenceResourcesApi'

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

export interface IntelligenceBuildCapabilityBinding {
  readonly requirement_id: string
  readonly capability: string
  readonly contract: string
  readonly implementation_id: string
  readonly implementation_version: string
  readonly artifact_digest: string
  readonly configuration_ref: string | null
  readonly secret_ref: string | null
}

export interface IntelligenceBuildAuthorityBinding {
  readonly request_id: string
  readonly authority: string
  readonly grant_ref: string
}

export interface IntelligenceBuildPackReference {
  readonly pack_id: string
  readonly pack_version: string
  readonly compiled_pack_id: string
  readonly pack_digest: string
}

export interface IntelligenceBuildActivationProposal {
  readonly contract: 'ace.application.intelligence-build-activation-proposal/v1alpha1'
  readonly product_id: string
  readonly activation_key: string
  readonly pack: IntelligenceBuildPackReference
  readonly overlay: Readonly<Record<string, unknown>>
  readonly capability_requirement_ids: readonly string[]
  readonly authority_request_ids: readonly string[]
  readonly proposal_id: string
  readonly proposal_digest: string
}

export interface IntelligenceBuildPlan {
  readonly contract: 'ace.application.intelligence-build-plan/v1alpha2' | 'ace.application.intelligence-build-plan/v1alpha3'
  readonly request: IntelligenceBuildPlanPrepareInput & {
    readonly contract: 'ace.application.intelligence-build-plan-request/v1alpha2'
    readonly product_id: string
    readonly actor_ref: string
    readonly request_id: string
    readonly request_digest: string
  }
  readonly pack_reference?: IntelligenceBuildPackReference
  readonly activation_proposal?: IntelligenceBuildActivationProposal
  readonly recorded_source_selection_refs: readonly IntelligenceBuildPlanReviewSource['selection'][]
  readonly review_projection: IntelligenceBuildPlanReviewProjection | null
  readonly plan_id: string
  readonly plan_digest: string
}

export type IntelligenceProjectionSupport = 'measured' | 'derived' | 'observed' | 'unsupported'

export interface IntelligenceProjectionValue {
  readonly support: IntelligenceProjectionSupport
  readonly value: { readonly value_json: string } | null
  readonly reason: string | null
}

export interface IntelligenceSystemProjection {
  readonly contract: 'ace.intelligence.system-projection/v1alpha1'
  readonly product_id: string
  readonly mode: 'proposed' | 'live'
  readonly blueprint: {
    readonly subject: string
    readonly elements: readonly {
      readonly kind: 'entity' | 'relationship' | 'event' | 'signal' | 'question' | 'update' | 'output' | 'consumer'
      readonly element_id: string
      readonly element_ref: string
      readonly label: string
      readonly rationale: string
      readonly confidence: IntelligenceProjectionValue
    }[]
    readonly gaps: readonly string[]
    readonly blueprint_id: string
    readonly blueprint_digest: string
  }
  readonly changes: readonly {
    readonly operation: 'add' | 'update' | 'remove'
    readonly target_ref: string
    readonly rationale: string
    readonly expected_effect: IntelligenceProjectionValue
    readonly requires_review: boolean
    readonly change_id: string
    readonly change_digest: string
  }[]
  readonly source_bindings: readonly {
    readonly binding_id: string
    readonly source_group_id: string
    readonly label: string
    readonly evidence_role: string
    readonly source_type_ref: string
    readonly source_uri: string
    readonly access_requirement_label: string
    readonly binding_state: 'proposed' | 'access_needed' | 'ready' | 'unavailable'
    readonly permission_state: 'not_evaluated' | 'pending' | 'ready' | 'denied' | 'unavailable'
    readonly readiness_state: 'not_evaluated' | 'pending' | 'ready' | 'denied' | 'unavailable'
    readonly requirements: { readonly support: IntelligenceProjectionSupport; readonly reason: string | null }
  }[]
  readonly coverage: readonly {
    readonly dimension: 'entity' | 'event' | 'signal'
    readonly target_ref: string
    readonly target_label: string
    readonly source_binding_ids: readonly string[]
    readonly predicted: IntelligenceProjectionValue
    readonly observed: IntelligenceProjectionValue
  }[]
  readonly initialization: readonly {
    readonly sequence: number
    readonly stage: string
    readonly state: 'complete' | 'in_progress' | 'pending' | 'blocked'
    readonly detail: string
  }[]
  readonly domain_health: readonly {
    readonly dimension: string
    readonly value: IntelligenceProjectionValue
  }[]
  readonly gaps: readonly string[]
  readonly generated_at: string
  readonly projection_id: string
  readonly projection_digest: string
}

export interface IntelligenceBuildPlanBindInput {
  readonly contract: 'ace.application.intelligence-build-plan-bind-request/v1alpha1'
  readonly plan: IntelligenceBuildPlan
  readonly capability_bindings: readonly IntelligenceBuildCapabilityBinding[]
  readonly authority_bindings: readonly IntelligenceBuildAuthorityBinding[]
  readonly bound_at: string
}

export interface BoundIntelligenceBuildPlan {
  readonly contract: 'ace.application.bound-intelligence-build-plan/v1alpha1'
  readonly binding_request: IntelligenceBuildPlanBindInput & {
    readonly request_id: string
    readonly request_digest: string
  }
  readonly activation_spec: {
    readonly spec_id: string
    readonly [key: string]: unknown
  }
  readonly execution_request_id: string
  readonly execution_request_digest: string
  readonly bound_plan_id: string
  readonly bound_plan_digest: string
}

export interface IntelligenceBuildStartInput {
  readonly authority_grant_ref: string
  readonly resource_authority_grant_ref: string
  readonly activation_approval_receipt_ref: string
  readonly activation_approval_subject_ref: string
  readonly client_request_id: string
  readonly profile_id: string
  readonly subject: string
  readonly outcome_id: string
  readonly source_group_ids: readonly string[]
  readonly recorded_source_selection_refs: readonly IntelligenceBuildPlanReviewSource['selection'][]
  readonly cadence_id: string
  readonly approved_effects: typeof APPROVED_ONBOARDING_EFFECTS
  readonly requested_at: string
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

export interface DomainActivationPlanPrepareInput {
  readonly current: Readonly<Record<string, unknown>>
  readonly bound_plan: BoundIntelligenceBuildPlan
  readonly requested_at: string
}

export interface DomainActivationPlanApproveInput {
  readonly decision: 'approve'
  readonly current: Readonly<Record<string, unknown>>
  readonly bound_plan: BoundIntelligenceBuildPlan
  readonly approved_at: string
}

export interface IntelligenceBuilderPlanActivateInput {
  readonly bound_plan: BoundIntelligenceBuildPlan
  readonly activation_approval_receipt_ref: string
  readonly requested_at: string
}

/**
 * Side-effect-free preview of the exact v1alpha2 activation plan an owner is
 * about to separately approve. Never the reviewed activation specification's
 * own approval: compatibility with canonical v1alpha1 activation requires
 * the two receipts to differ.
 */
export interface IntelligenceActivationPlan {
  readonly contract: 'ace.application.intelligence-activation-plan/v1alpha2'
  readonly action: 'initial_activation' | 'upgrade' | 'suspend' | 'reactivate' | 'rollback' | 'retire'
  readonly onboarding_handoff: { readonly session_id: string; readonly [key: string]: unknown }
  readonly spec: { readonly spec_id: string; readonly activation_key: string; readonly [key: string]: unknown }
  readonly requested_effects: readonly string[]
  readonly requested_capabilities: readonly IntelligenceBuildCapabilityBinding[]
  readonly requested_authorities: readonly IntelligenceBuildAuthorityBinding[]
  readonly created_at: string
  readonly plan_id: string
  readonly plan_digest: string
}

/** Opaque historical coordinates from admitting the plan's own approval. Grants no present runtime authority. */
export interface DomainActivationCommitReference {
  readonly contract: 'ace.application.domain-activation-commit-reference/v1alpha2'
  readonly authority_stage: 'historical_reference'
  readonly live_authority: false
  readonly product_id: string
  readonly activation_key: string
  readonly activation_id: string
  readonly state: 'active' | 'suspended' | 'retired'
  readonly plan_id: string
  readonly plan_digest: string
  readonly revision: number
  readonly revision_id: string
  readonly revision_digest: string
  readonly commit_receipt_id: string
  readonly commit_receipt_digest: string
  readonly committed_at: string
}

export interface IntelligenceBuilderActivationResult {
  readonly contract: 'ace.http.intelligence-builder-activation-result/v1alpha1'
  readonly receipt: { readonly session_id: string; readonly activated_at: string; readonly [key: string]: unknown }
  readonly replayed: boolean
}

export interface IntelligenceBuildApprovalResult {
  readonly contract: 'ace.http.intelligence-activation-approval-result/v1alpha1'
  readonly approval: {
    readonly receipt_ref: string
    readonly product_id: string
    readonly subject_ref: string
    readonly actor_ref: string
    readonly receipt_hash: string
    readonly approved_at: string
  }
  readonly bound_plan_id: string
  readonly bound_plan_digest: string
  readonly start_request: IntelligenceBuildStartInput
}

export interface IntelligenceBuildSessionAssociationResult {
  readonly contract: 'ace.http.intelligence-build-session-association-result/v1alpha1'
  readonly bound_plan_id: string
  readonly bound_plan_digest: string
  readonly approval: IntelligenceBuildApprovalResult['approval']
  readonly session: Readonly<Record<string, unknown>>
  readonly replayed: boolean
}

/**
 * The exact resource kinds the backend Domain Health aggregator supports:
 * `ace.application.intelligence_system_projection.DOMAIN_HEALTH_RESOURCE_KINDS`.
 * Any other kind, a subject filter, or a non-null cursor makes the resource
 * read fail closed to `mode: proposed` server-side.
 */
export const DOMAIN_HEALTH_RESOURCE_KINDS: readonly IntelligenceResourceKind[] = [
  'entity',
  'observation',
  'shift',
  'signal',
  'source_health',
]

export interface IntelligenceResourceSelectorInput {
  readonly authority_grant_ref: string
  readonly resource_kinds: readonly IntelligenceResourceKind[]
  readonly subject_refs: readonly string[]
  readonly as_of: string
  readonly available_at: string
  readonly page_size: number
  readonly cursor: IntelligenceResourceCursor | null
}

export interface IntelligenceBuildResourceStateInput {
  readonly bound_plan: BoundIntelligenceBuildPlan
  readonly activation_approval_receipt_ref: string
  readonly selector: IntelligenceResourceSelectorInput
}

/**
 * Build the exact request for `POST /v1/intelligence/builds/projection/resource-state`.
 *
 * Every value here is either the exact bound plan the server already
 * approved and started, or a timestamp/grant the server itself returned from
 * that same governed `/start` call — never a client-manufactured timestamp,
 * grant, or plan/session/activation material.
 */
export function createIntelligenceBuildResourceStateInput(
  boundPlan: BoundIntelligenceBuildPlan,
  activationApprovalReceiptRef: string,
  resourceAuthorityGrantRef: string,
  resourcePage: IntelligenceResourcePage,
): IntelligenceBuildResourceStateInput {
  return {
    bound_plan: boundPlan,
    activation_approval_receipt_ref: activationApprovalReceiptRef,
    selector: {
      authority_grant_ref: resourceAuthorityGrantRef,
      resource_kinds: DOMAIN_HEALTH_RESOURCE_KINDS,
      subject_refs: [],
      as_of: resourcePage.as_of,
      available_at: resourcePage.available_at,
      page_size: 200,
      cursor: null,
    },
  }
}

export interface IntelligenceBuildActivationInputs {
  readonly capability_bindings: readonly IntelligenceBuildCapabilityBinding[]
  readonly authority_bindings: readonly IntelligenceBuildAuthorityBinding[]
}

export type IntelligenceBuildActivationSetup =
  | { readonly state: 'configured'; readonly inputs: IntelligenceBuildActivationInputs }
  | { readonly state: 'unavailable'; readonly detail: string }

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

export function createIntelligenceBuildPlanBindInput(
  plan: IntelligenceBuildPlan,
  bindings: {
    readonly capability_bindings: readonly IntelligenceBuildCapabilityBinding[]
    readonly authority_bindings: readonly IntelligenceBuildAuthorityBinding[]
  },
): IntelligenceBuildPlanBindInput {
  if (plan.contract !== 'ace.application.intelligence-build-plan/v1alpha3' || plan.activation_proposal === undefined) {
    throw new IntelligenceBuildApiError(409, 'Only an exact v1alpha3 activation proposal can be bound.')
  }
  return {
    contract: 'ace.application.intelligence-build-plan-bind-request/v1alpha1',
    plan,
    capability_bindings: bindings.capability_bindings,
    authority_bindings: bindings.authority_bindings,
    bound_at: new Date().toISOString(),
  }
}

export function createIntelligenceBuildStartInput(
  bound: BoundIntelligenceBuildPlan,
  activationApprovalReceiptRef: string,
): IntelligenceBuildStartInput {
  const request = bound.binding_request.plan.request
  return {
    authority_grant_ref: BUILD_AUTHORITY_GRANT_REF,
    resource_authority_grant_ref: RESOURCE_AUTHORITY_GRANT_REF,
    activation_approval_receipt_ref: activationApprovalReceiptRef,
    activation_approval_subject_ref: bound.activation_spec.spec_id,
    client_request_id: request.client_request_id,
    profile_id: request.profile_id,
    subject: request.subject,
    outcome_id: request.outcome_id,
    source_group_ids: request.source_group_ids,
    recorded_source_selection_refs: bound.binding_request.plan.recorded_source_selection_refs,
    cadence_id: request.cadence_id,
    approved_effects: request.proposed_effects,
    requested_at: request.requested_at,
  }
}

function configuredBindings<T>(value: string | undefined, label: string): readonly T[] {
  if (value === undefined || value.trim() === '') return []
  let parsed: unknown
  try {
    parsed = JSON.parse(value)
  } catch {
    throw new IntelligenceBuildApiError(503, `${label} are not valid JSON.`)
  }
  if (!Array.isArray(parsed)) {
    throw new IntelligenceBuildApiError(503, `${label} must be a JSON array.`)
  }
  return parsed as readonly T[]
}

export function configuredIntelligenceBuildActivation(): IntelligenceBuildActivationSetup {
  const capabilityBindings = import.meta.env.VITE_INTELLIGENCE_CAPABILITY_BINDINGS_JSON
  const authorityBindings = import.meta.env.VITE_INTELLIGENCE_AUTHORITY_BINDINGS_JSON
  if (
    typeof capabilityBindings !== 'string'
    || capabilityBindings.trim() === ''
    || typeof authorityBindings !== 'string'
    || authorityBindings.trim() === ''
  ) {
    return {
      state: 'unavailable',
      detail: 'This host has no exact capability and authority binding configuration. The plan remains review-only.',
    }
  }
  try {
    return {
      state: 'configured',
      inputs: {
        capability_bindings: configuredBindings<IntelligenceBuildCapabilityBinding>(
          capabilityBindings,
          'Capability bindings',
        ),
        authority_bindings: configuredBindings<IntelligenceBuildAuthorityBinding>(
          authorityBindings,
          'Authority bindings',
        ),
      },
    }
  } catch (reason: unknown) {
    return {
      state: 'unavailable',
      detail: reason instanceof Error ? reason.message : 'Activation binding configuration is invalid.',
    }
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

async function postProjection(token: string, plan: IntelligenceBuildPlan): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/projection`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ plan }),
  })
}

export async function projectIntelligenceBuild(plan: IntelligenceBuildPlan): Promise<IntelligenceSystemProjection> {
  let token = await getToken()
  let response = await postProjection(token, plan)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postProjection(token, plan)
  }
  if (!response.ok) {
    let detail = `ACE could not project this Intelligence system (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as IntelligenceSystemProjection
}

async function postBind(token: string, input: IntelligenceBuildPlanBindInput): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/bind`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
  })
}

export async function bindIntelligenceBuildPlan(input: IntelligenceBuildPlanBindInput): Promise<BoundIntelligenceBuildPlan> {
  let token = await getToken()
  let response = await postBind(token, input)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postBind(token, input)
  }
  if (!response.ok) {
    let detail = `ACE could not bind this exact Intelligence plan (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as BoundIntelligenceBuildPlan
}

async function postApproval(token: string, boundPlan: BoundIntelligenceBuildPlan): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/approve`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      decision: 'approve',
      bound_plan: boundPlan,
      approved_at: new Date().toISOString(),
    }),
  })
}

export async function approveIntelligenceBuildPlan(
  boundPlan: BoundIntelligenceBuildPlan,
): Promise<IntelligenceBuildApprovalResult> {
  let token = await getToken()
  let response = await postApproval(token, boundPlan)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postApproval(token, boundPlan)
  }
  if (!response.ok) {
    let detail = `ACE could not record approval for this exact Intelligence plan (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as IntelligenceBuildApprovalResult
}

async function postSessionAssociation(
  token: string,
  boundPlan: BoundIntelligenceBuildPlan,
  approvalReceiptRef: string,
): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/session/associate`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      bound_plan: boundPlan,
      approval_receipt_ref: approvalReceiptRef,
    }),
  })
}

/**
 * Replays or admits only the exact GOAL_SELECTED Builder revision derived by
 * the server from reviewed execution/outcome identity. No session, goal,
 * timestamp, source readiness, or later progress is authored by the client.
 */
export async function associateIntelligenceBuildSession(
  boundPlan: BoundIntelligenceBuildPlan,
  approvalReceiptRef: string,
): Promise<IntelligenceBuildSessionAssociationResult> {
  let token = await getToken()
  let response = await postSessionAssociation(token, boundPlan, approvalReceiptRef)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postSessionAssociation(token, boundPlan, approvalReceiptRef)
  }
  if (!response.ok) {
    let detail = `ACE could not associate this reviewed plan with its Builder session (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as IntelligenceBuildSessionAssociationResult
}

/**
 * Only assembles the exact caller-supplied session revision, bound plan, and
 * server-derived timestamp. Never fabricates a session, handoff, plan, or
 * timestamp: `current` must be the exact durable session revision the
 * resource payload supplied, and `requestedAt`/`approvedAt` must be a
 * server-returned instant (typically the reviewed specification's own
 * `/approve` `approved_at`) so compatibility with the canonical activation
 * approval window is preserved.
 */
export function createDomainActivationPlanPrepareInput(
  current: Readonly<Record<string, unknown>>,
  boundPlan: BoundIntelligenceBuildPlan,
  requestedAt: string,
): DomainActivationPlanPrepareInput {
  return { current, bound_plan: boundPlan, requested_at: requestedAt }
}

export function createDomainActivationPlanApproveInput(
  current: Readonly<Record<string, unknown>>,
  boundPlan: BoundIntelligenceBuildPlan,
  approvedAt: string,
): DomainActivationPlanApproveInput {
  return { decision: 'approve', current, bound_plan: boundPlan, approved_at: approvedAt }
}

export function createIntelligenceBuilderPlanActivateInput(
  boundPlan: BoundIntelligenceBuildPlan,
  activationApprovalReceiptRef: string,
  requestedAt: string,
): IntelligenceBuilderPlanActivateInput {
  return {
    bound_plan: boundPlan,
    activation_approval_receipt_ref: activationApprovalReceiptRef,
    requested_at: requestedAt,
  }
}

async function postActivationPlanPrepare(token: string, input: DomainActivationPlanPrepareInput): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/activation-plan/prepare`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
  })
}

/** Side-effect-free preview: never treated as this plan's own approval. */
export async function prepareDomainActivationPlan(
  input: DomainActivationPlanPrepareInput,
): Promise<IntelligenceActivationPlan> {
  let token = await getToken()
  let response = await postActivationPlanPrepare(token, input)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postActivationPlanPrepare(token, input)
  }
  if (!response.ok) {
    let detail = `ACE could not preview this exact activation plan (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as IntelligenceActivationPlan
}

async function postActivationPlanApprove(token: string, input: DomainActivationPlanApproveInput): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/activation-plan/approve`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
  })
}

/**
 * Records the plan's own distinct owner approval, separate from the
 * reviewed activation specification's `/approve` receipt, then durably
 * admits it. Returns opaque historical coordinates that grant no present
 * runtime authority.
 */
export async function approveDomainActivationPlan(
  input: DomainActivationPlanApproveInput,
): Promise<DomainActivationCommitReference> {
  let token = await getToken()
  let response = await postActivationPlanApprove(token, input)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postActivationPlanApprove(token, input)
  }
  if (!response.ok) {
    let detail = `ACE could not record this exact activation-plan approval (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as DomainActivationCommitReference
}

async function postActivationPlanActivate(token: string, input: IntelligenceBuilderPlanActivateInput): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/activation-plan/activate`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
  })
}

/** Derives the Builder session from the already-admitted plan; safe to retry. */
export async function activateIntelligenceBuilderPlan(
  input: IntelligenceBuilderPlanActivateInput,
): Promise<IntelligenceBuilderActivationResult> {
  let token = await getToken()
  let response = await postActivationPlanActivate(token, input)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postActivationPlanActivate(token, input)
  }
  if (!response.ok) {
    let detail = `ACE could not activate this exact plan (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as IntelligenceBuilderActivationResult
}

async function postRetry(
  token: string,
  current: Readonly<Record<string, unknown>>,
): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/retry`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ current, requested_at: new Date().toISOString() }),
  })
}

export async function retryIntelligenceBuildSession(
  current: Readonly<Record<string, unknown>>,
): Promise<Readonly<Record<string, unknown>>> {
  let token = await getToken()
  let response = await postRetry(token, current)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postRetry(token, current)
  }
  if (!response.ok) {
    let detail = `ACE could not retry this exact Intelligence build session (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as Readonly<Record<string, unknown>>
}

async function postBuild(token: string, input: IntelligenceBuildStartInput): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/start`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
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

async function postResourceState(token: string, input: IntelligenceBuildResourceStateInput): Promise<Response> {
  return fetch(`${BASE}/v1/intelligence/builds/projection/resource-state`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
  })
}

/**
 * Enrich the started build's own projection from one authorized, exact
 * resource-plane read. Returns `mode: 'proposed'` with explicit gaps unless
 * the exact bound plan is durably approved and durably active; never
 * client-side health, coverage, or mode values.
 */
export async function projectIntelligenceBuildResourceState(
  input: IntelligenceBuildResourceStateInput,
): Promise<IntelligenceSystemProjection> {
  let token = await getToken()
  let response = await postResourceState(token, input)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postResourceState(token, input)
  }
  if (!response.ok) {
    let detail = `ACE could not project this Intelligence system's live resource state (${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new IntelligenceBuildApiError(response.status, detail)
  }
  return (await response.json()) as IntelligenceSystemProjection
}
