import { describe, expect, it } from 'vitest'

import type {
  IntelligenceResourceKind,
  IntelligenceResourceRecord,
} from '@/api/intelligenceResourcesApi'

import { projectEntityIntelligence } from './entityIntelligenceModel'

function record(
  kind: IntelligenceResourceKind,
  id: string,
  options: {
    readonly asOf?: string
    readonly title?: string
    readonly summary?: string
    readonly subjectRefs?: string[]
    readonly provenance?: IntelligenceResourceRecord['provenance']
    readonly payload?: Record<string, unknown>
  } = {},
): IntelligenceResourceRecord {
  const asOf = options.asOf ?? '2026-08-14T12:00:00.000Z'
  return {
    contract: 'ace.intelligence.resource-plane-record/v1alpha1',
    reference: {
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:world-intelligence',
      resource_kind: kind,
      resource_id: `${kind}:${id}`,
      resource_digest: `sha256:${id.padEnd(64, 'a').slice(0, 64)}`,
      resource_contract: `ace.test.${kind}/v1`,
      revision: 1,
      as_of: asOf,
      available_at: asOf,
    },
    availability: 'available',
    title: options.title ?? id,
    summary: options.summary ?? null,
    subject_refs: options.subjectRefs ?? [],
    provenance: options.provenance ?? [],
    supersedes: null,
    payload: options.payload ?? {},
    degraded_reason_refs: [],
  }
}

function entity(
  id: string,
  asOf: string,
  attributes: Record<string, unknown>,
  confidence: unknown,
  provenance: IntelligenceResourceRecord['provenance'] = [],
): IntelligenceResourceRecord {
  return record('entity', id, {
    asOf,
    title: 'entity:atlas-labs',
    subjectRefs: ['entity:atlas-labs'],
    provenance,
    payload: {
      value_json: JSON.stringify({
        entity_ref: 'entity:atlas-labs',
        entity_type_ref: 'entity_type:company',
        attributes: { value_json: JSON.stringify(attributes) },
        projected_at: asOf,
        confidence,
      }),
    },
  })
}

describe('entity intelligence projection', () => {
  it('projects current state, supported confidence, and directional attribute change from immutable snapshots', () => {
    const previous = entity(
      'atlas-previous',
      '2026-08-10T12:00:00.000Z',
      { name: 'Atlas Labs', employee_count: 80, posture: 'steady' },
      0.82,
    )
    const current = entity(
      'atlas-current',
      '2026-08-14T12:00:00.000Z',
      { name: 'Atlas Labs', employee_count: 95, posture: 'expanding' },
      0.91,
    )

    const [projection] = projectEntityIntelligence([previous, current])

    expect(projection?.name).toBe('Atlas Labs')
    expect(projection?.confidence).toBe(0.91)
    expect(projection?.current).toBe(current)
    expect(projection?.previous).toBe(previous)
    expect(projection?.attributes).toContainEqual({
      key: 'posture',
      label: 'Posture',
      value: 'expanding',
    })
    expect(projection?.changes).toContainEqual({
      key: 'employee_count',
      label: 'Employee Count',
      direction: 'increased',
      previous: '80',
      current: '95',
      detail: '80 → 95',
    })
  })

  it('keeps malformed confidence unsupported and does not infer direction from one snapshot', () => {
    const [projection] = projectEntityIntelligence([
      entity('atlas-current', '2026-08-14T12:00:00.000Z', { name: 'Atlas Labs' }, 7),
    ])

    expect(projection?.confidence).toBeNull()
    expect(projection?.changes).toEqual([])
  })

  it('orders a subject-scoped timeline by explicit event/publication/observation time without relabeling records as events', () => {
    const current = entity('atlas-current', '2026-08-14T12:00:00.000Z', { name: 'Atlas Labs' }, 0.9)
    const observation = record('observation', 'pricing-observation', {
      asOf: '2026-08-12T12:00:00.000Z',
      title: 'Pricing page observation',
      subjectRefs: ['entity:atlas-labs'],
      payload: {
        value_json: JSON.stringify({
          event_effective_at: '2026-08-13T09:00:00.000Z',
          observed_at: '2026-08-13T12:00:00.000Z',
        }),
      },
    })
    const signal = record('signal', 'hiring-signal', {
      asOf: '2026-08-14T08:00:00.000Z',
      title: 'Hiring signal',
      subjectRefs: ['entity:atlas-labs'],
      payload: {
        value_json: JSON.stringify({ detected_at: '2026-08-14T07:30:00.000Z' }),
      },
    })

    const [projection] = projectEntityIntelligence([current, observation, signal])

    expect(projection?.timeline.map((item) => item.kindLabel)).toEqual(['Signal', 'Observation'])
    expect(projection?.timeline[0]).toMatchObject({
      occurredAt: '2026-08-14T07:30:00.000Z',
      timeBasis: 'detected',
    })
    expect(projection?.timeline[1]).toMatchObject({
      occurredAt: '2026-08-13T09:00:00.000Z',
      timeBasis: 'event effective',
    })
  })

  it('expands only exact depth-one provenance and keeps conflicts and unknowns subject-scoped', () => {
    const evidence = record('observation', 'exact-observation', {
      asOf: '2026-08-13T12:00:00.000Z',
      title: 'Exact observation',
      subjectRefs: ['entity:atlas-labs'],
    })
    const merelySimilar = record('observation', 'similar-observation', {
      asOf: '2026-08-13T13:00:00.000Z',
      title: 'Merely subject-similar observation',
      subjectRefs: ['entity:atlas-labs'],
    })
    const current = entity(
      'atlas-current',
      '2026-08-14T12:00:00.000Z',
      { name: 'Atlas Labs' },
      0.9,
      [evidence.reference],
    )
    const derivedSignal = record('signal', 'derived-signal', {
      asOf: '2026-08-14T13:00:00.000Z',
      subjectRefs: ['entity:atlas-labs'],
      provenance: [current.reference],
    })
    const conflict = record('conflict', 'pricing-conflict', {
      subjectRefs: ['entity:atlas-labs'],
      title: 'Pricing sources disagree',
    })
    const uncertainty = record('uncertainty', 'adoption-unknown', {
      subjectRefs: ['entity:atlas-labs'],
      title: 'Regional adoption is unknown',
    })

    const [projection] = projectEntityIntelligence([
      evidence,
      merelySimilar,
      current,
      derivedSignal,
      conflict,
      uncertainty,
    ])

    expect(projection?.relationships.map((item) => item.record.title)).toEqual([
      'derived-signal',
      'Exact observation',
    ])
    expect(projection?.evidence.map((item) => item.title)).toEqual(['Exact observation'])
    expect(projection?.conflicts.map((item) => item.title)).toEqual(['Pricing sources disagree'])
    expect(projection?.unknowns.map((item) => item.title)).toEqual(['Regional adoption is unknown'])
  })
})
