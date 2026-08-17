import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type {
  IntelligenceResourceKind,
  IntelligenceResourceRecord,
} from '@/api/intelligenceResourcesApi'

import { ResourceCard } from './ResourceCard'

function record(kind: IntelligenceResourceKind): IntelligenceResourceRecord {
  return {
    contract: 'ace.intelligence.resource-plane-record/v1alpha1',
    reference: {
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:test',
      resource_kind: kind,
      resource_id: `${kind}:test`,
      resource_digest: `sha256:${'a'.repeat(64)}`,
      resource_contract: `ace.test.${kind}/v1`,
      revision: 1,
      as_of: '2026-08-14T18:00:00.000Z',
      available_at: '2026-08-14T18:00:00.000Z',
    },
    availability: 'available',
    title: `Test ${kind}`,
    summary: `A ${kind} record.`,
    subject_refs: [],
    provenance: [],
    supersedes: null,
    payload: {},
    degraded_reason_refs: [],
  }
}

describe('ResourceCard icon semantics', () => {
  it('uses the source glyph for a source rather than a generic shield', () => {
    const { container } = render(<ResourceCard record={record('source')} compact />)

    expect(container.querySelector('svg.lucide-database')).toBeTruthy()
    expect(container.querySelector('svg.lucide-shield-check')).toBeNull()
  })

  it('uses the signal glyph for a signal rather than a generic shield', () => {
    const { container } = render(<ResourceCard record={record('signal')} compact />)

    expect(container.querySelector('svg.lucide-radio')).toBeTruthy()
    expect(container.querySelector('svg.lucide-shield-check')).toBeNull()
  })
})
