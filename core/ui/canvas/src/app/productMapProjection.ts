import type { LandscapeAssertion, LandscapeRecord, LivingProductSnapshot } from '@/api/landscapeApi'

type AssertionStatus = 'accepted' | 'provisional' | 'contested' | 'rejected' | 'unknown'

export interface ProductMapProjection {
  productName: string
  productId: string | null
  status: string
  counts: {
    projects: number
    capabilities: number
    decisions: number
    relationships: number
    attention: number
  }
  assertions: Record<AssertionStatus, LandscapeAssertion[]>
  corrections: LandscapeRecord[]
  outcomes: LandscapeRecord[]
}

function text(record: LandscapeRecord | null | undefined, keys: string[]): string | null {
  if (record === null || record === undefined) return null
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim() !== '') return value.trim()
  }
  return null
}

function assertionStatus(assertion: LandscapeAssertion): AssertionStatus {
  const status = assertion.status?.toLowerCase()
  if (status === 'accepted' || status === 'provisional' || status === 'contested' || status === 'rejected') {
    return status
  }
  return 'unknown'
}

export function projectProductMap(snapshot: LivingProductSnapshot): ProductMapProjection {
  const assertions: ProductMapProjection['assertions'] = {
    accepted: [],
    provisional: [],
    contested: [],
    rejected: [],
    unknown: [],
  }
  for (const assertion of snapshot.relationships.assertions) {
    assertions[assertionStatus(assertion)].push(assertion)
  }

  const corrections = [
    ...snapshot.intelligence.observations,
    ...snapshot.foresight.outcome_observations,
  ].filter((record) => text(record, ['observation_type', 'type'])?.toLowerCase() === 'correction')
  const outcomes = [
    ...snapshot.foresight.prediction_outcomes,
    ...snapshot.foresight.outcome_observations,
    ...snapshot.foresight.action_outcomes,
  ]
  const attention =
    snapshot.issues.length +
    snapshot.source_states.filter((source) => source.status !== 'available').length +
    assertions.contested.length +
    assertions.unknown.length

  return {
    productName: text(snapshot.product, ['name', 'title']) ?? 'Unknown product',
    productId: snapshot.product?.id ?? null,
    status: snapshot.projection_state.status,
    counts: {
      projects: snapshot.projects.length,
      capabilities: snapshot.capabilities.items.length,
      decisions: snapshot.decisions.length,
      relationships: snapshot.relationships.operational.length,
      attention,
    },
    assertions,
    corrections,
    outcomes,
  }
}
