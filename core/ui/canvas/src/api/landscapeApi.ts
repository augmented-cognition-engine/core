import { authGet } from './canvasApi'

export const LIVING_PRODUCT_SCHEMA_VERSION = 'ace.living-product-snapshot.v1'
export const LIVING_PRODUCT_PROJECTION_VERSION = 'ace.living-product-projection.g1.v1'

export interface LandscapeRecord {
  id: string
  [key: string]: unknown
}

export interface LandscapeAssertion extends LandscapeRecord {
  subject?: string
  predicate?: string
  object?: string
  status?: string
  proposal_confidence?: number
  evidence_strength?: number
  resolver_certainty?: number
  provenance_quality?: number
  freshness?: number
  evidence_refs?: string[]
  contradicting_assertions?: string[]
  assumptions?: string[]
  explanation?: string
  degraded_reason?: string | null
  projection_eligible?: boolean
}

export interface LandscapeRelationship extends LandscapeRecord {
  subject?: string
  predicate?: string
  object?: string
  source_id?: string
  target_id?: string
  relationship_type?: string
}

export interface LandscapeIssue extends LandscapeRecord {
  code?: string
  detail?: string
  related?: string[]
  recovery?: string
}

export interface LandscapeSourceState {
  source: string
  status: string
  record_count: number
  reason?: string | null
  required: boolean
  limit: number | null
}

export interface LivingProductSnapshot {
  schema_version: string
  projection_version: string
  snapshot_id: string
  authority: {
    mode: string
    writes_permitted: boolean
    autonomous_dispatch: boolean
    operational_truth: string
    assertions_are_operational_only_when: string
    model_proposals_define_truth: boolean
    [key: string]: unknown
  }
  projection_state: {
    status: string
    assertion_states: Record<string, number>
    issue_count: number
  }
  product: LandscapeRecord | null
  intent: {
    directions: LandscapeRecord[]
    visions: LandscapeRecord[]
  }
  projects: LandscapeRecord[]
  capabilities: {
    items: LandscapeRecord[]
    quality: LandscapeRecord[]
  }
  relationships: {
    operational: LandscapeRelationship[]
    assertions: LandscapeAssertion[]
    structural: LandscapeRelationship[]
  }
  history: {
    assertion_events: LandscapeRecord[]
  }
  decisions: LandscapeRecord[]
  foresight: {
    predictions: LandscapeRecord[]
    prediction_outcomes: LandscapeRecord[]
    outcome_observations: LandscapeRecord[]
    action_outcomes: LandscapeRecord[]
  }
  intelligence: {
    observations: LandscapeRecord[]
    insights: LandscapeRecord[]
  }
  work: {
    authority: string
    tasks: LandscapeRecord[]
    initiatives: LandscapeRecord[]
    milestones: LandscapeRecord[]
    work_items: LandscapeRecord[]
    agent_specs: LandscapeRecord[]
    roadmap_phases: LandscapeRecord[]
  }
  source_states: LandscapeSourceState[]
  issues: LandscapeIssue[]
}

export interface LandscapeRequest {
  projectionVersion?: string
}

function queryString(request: LandscapeRequest): string {
  const params = new URLSearchParams()
  params.set(
    'projection_version',
    request.projectionVersion ?? LIVING_PRODUCT_PROJECTION_VERSION,
  )
  return params.toString()
}

export const landscapeApi = {
  get: (request: LandscapeRequest = {}) =>
    authGet<LivingProductSnapshot>(`/product/landscape?${queryString(request)}`),
}
