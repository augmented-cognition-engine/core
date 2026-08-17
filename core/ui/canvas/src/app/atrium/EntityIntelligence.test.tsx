import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type {
  IntelligenceResourceKind,
  IntelligenceResourceRecord,
} from '@/api/intelligenceResourcesApi'

import { EntityIntelligenceExplore } from './EntityIntelligence'

function record(
  kind: IntelligenceResourceKind,
  id: string,
  options: {
    readonly title?: string
    readonly summary?: string
    readonly asOf?: string
    readonly subjectRefs?: string[]
    readonly provenance?: IntelligenceResourceRecord['provenance']
    readonly payload?: unknown
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
  employees: number,
  provenance: IntelligenceResourceRecord['provenance'] = [],
): IntelligenceResourceRecord {
  return record('entity', id, {
    title: 'entity:atlas-labs',
    asOf,
    subjectRefs: ['entity:atlas-labs'],
    provenance,
    payload: {
      value_json: JSON.stringify({
        entity_ref: 'entity:atlas-labs',
        entity_type_ref: 'entity_type:company',
        attributes: { value_json: JSON.stringify({ name: 'Atlas Labs', employee_count: employees }) },
        confidence: 0.91,
      }),
    },
  })
}

describe('Entity Intelligence Explore', () => {
  it('keeps the answer first and exposes an accessible entity, timeline, evidence, and deliberate depth control', () => {
    const evidence = record('observation', 'pricing', {
      title: 'Published pricing observation',
      summary: 'The public price moved lower.',
      subjectRefs: ['entity:atlas-labs'],
      payload: { value_json: JSON.stringify({ observed_at: '2026-08-13T12:00:00.000Z' }) },
    })
    const current = entity('current', '2026-08-14T12:00:00.000Z', 95, [evidence.reference])
    const previous = entity('previous', '2026-08-10T12:00:00.000Z', 80)
    const signal = record('signal', 'expansion', {
      title: 'Expansion signal',
      summary: 'Hiring and availability moved together.',
      asOf: '2026-08-14T13:00:00.000Z',
      subjectRefs: ['entity:atlas-labs'],
      provenance: [current.reference],
    })

    render(<EntityIntelligenceExplore items={[previous, evidence, current, signal]} />)

    expect(screen.getByRole('heading', { name: 'Ask first. Then inspect the entity.' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Atlas Labs' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'What is admitted now' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'What moved' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Recent admitted developments' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Deliberate expansion' })).toBeTruthy()
    expect(screen.getByText('80 → 95')).toBeTruthy()
    expect(screen.getByText('Expansion signal')).toBeTruthy()

    const depth = screen.getByRole('group', { name: 'Relationship depth' })
    expect(within(depth).getByRole('button', { name: 'Depth 0' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(within(depth).getByRole('button', { name: 'Depth 1' }))
    expect(within(depth).getByRole('button', { name: 'Depth 1' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('list', { name: 'Depth 1 resource relationships' })).toBeTruthy()
    expect(screen.getByText('Exact upstream record')).toBeTruthy()
    expect(screen.getByText('Exact derived record')).toBeTruthy()
  })

  it('states the entity projection dependency instead of fabricating one from search material', () => {
    render(<EntityIntelligenceExplore items={[
      record('brief', 'market-brief', {
        title: 'Market Brief',
        summary: 'A cited market answer without an entity snapshot.',
      }),
    ]} />)

    expect(screen.getByRole('status', { name: 'Entity intelligence unavailable' })).toBeTruthy()
    expect(screen.getByText('No entity snapshot is projected')).toBeTruthy()
  })
})
