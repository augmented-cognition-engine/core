import { describe, expect, it } from 'vitest'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'

import { groupResources, rankResourcesForQuestion } from './intelligenceModel'

function resource(
  kind: IntelligenceResourceRecord['reference']['resource_kind'],
  title: string,
  availableAt: string,
  availability: IntelligenceResourceRecord['availability'] = 'available',
): IntelligenceResourceRecord {
  return {
    contract: 'ace.intelligence.resource-plane-record/v1alpha1',
    reference: {
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:test',
      resource_kind: kind,
      resource_id: `${kind}:${title.toLowerCase().split(' ').join('-')}`,
      resource_digest: `sha256:${'a'.repeat(64)}`,
      resource_contract: `ace.test.${kind}/v1`,
      revision: 1,
      as_of: availableAt,
      available_at: availableAt,
    },
    availability,
    title,
    summary: `${title} summary with security and price evidence`,
    subject_refs: [],
    provenance: [],
    supersedes: null,
    payload: null,
    degraded_reason_refs:
      availability === 'degraded' ? ['degraded_reason:test'] : [],
  }
}

describe('Atrium intelligence model', () => {
  it('groups first-class surfaces without creating a second resource taxonomy', () => {
    const items = [
      resource('brief', 'Weekly brief', '2026-08-10T00:00:00Z'),
      resource('shift', 'Price shift', '2026-08-11T00:00:00Z'),
      resource('case', 'Launch opportunity', '2026-08-12T00:00:00Z'),
      resource('agent', 'Source scout', '2026-08-09T00:00:00Z'),
      resource('connection', 'Public filings', '2026-08-08T00:00:00Z'),
      resource('decision', 'Respond to move', '2026-08-12T01:00:00Z'),
    ]

    const grouped = groupResources(items)

    expect(grouped.intelligence.map((item) => item.reference.resource_kind)).toEqual([
      'shift',
      'brief',
    ])
    expect(grouped.opportunities.map((item) => item.reference.resource_kind)).toEqual([
      'case',
      'shift',
    ])
    expect(grouped.agents).toHaveLength(1)
    expect(grouped.connections).toHaveLength(1)
    expect(grouped.strategy).toHaveLength(1)
  })

  it('routes degraded records into attention while excluding tombstones', () => {
    const grouped = groupResources([
      resource('source', 'Incomplete source', '2026-08-12T00:00:00Z', 'degraded'),
      resource('case', 'Closed case', '2026-08-11T00:00:00Z', 'tombstoned'),
    ])

    expect(grouped.attention.map((item) => item.title)).toEqual(['Incomplete source'])
    expect(grouped.opportunities).toEqual([])
  })

  it('answers only from matching governed resources and prefers title matches', () => {
    const price = resource('shift', 'Competitor price shift', '2026-08-12T00:00:00Z')
    const security = resource('brief', 'Security posture', '2026-08-12T01:00:00Z')

    const matches = rankResourcesForQuestion('What changed in competitor price?', [security, price])

    expect(matches[0]).toBe(price)
    expect(rankResourcesForQuestion('unrepresented topic', [security, price])).toEqual([])
  })
})
