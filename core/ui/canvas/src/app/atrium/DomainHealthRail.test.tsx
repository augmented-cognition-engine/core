import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import type { IntelligenceResourceKind, IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'

import { DomainHealthRail } from './LivingIntelligence'

const availableAt = '2026-08-14T18:00:00.000Z'

function record(
  kind: IntelligenceResourceKind,
  id: string,
  title: string,
  options: {
    readonly availability?: IntelligenceResourceRecord['availability']
  } = {},
): IntelligenceResourceRecord {
  return {
    contract: 'ace.intelligence.resource-plane-record/v1alpha1',
    reference: {
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:world-ai-command-center',
      resource_kind: kind,
      resource_id: `${kind}:${id}`,
      resource_digest: `sha256:${id.padEnd(64, 'a').slice(0, 64)}`,
      resource_contract: `ace.test.${kind}/v1`,
      revision: 1,
      as_of: availableAt,
      available_at: availableAt,
    },
    availability: options.availability ?? 'available',
    title,
    summary: null,
    subject_refs: [],
    provenance: [],
    supersedes: null,
    payload: {},
    degraded_reason_refs: [],
  }
}

const ALL_DIMENSION_LABELS = [
  'Coverage',
  'Freshness',
  'Confidence',
  'Conflicts',
  'Resolution',
  'Source health',
  'Maintenance health',
  'Historical depth',
]

describe('DomainHealthRail', () => {
  it('keeps every dimension present (though subordinated) in the concise, non-compact Overview rail', () => {
    const source = record('source', 'official-releases', 'Official release records')
    const conflict = record('conflict', 'pricing-vs-support', 'Pricing narrative disagreement')
    const healthRecord = record('source_health', 'feed-health', 'Feed health record', { availability: 'degraded' })
    const items = [source, conflict, healthRecord]

    render(
      <MemoryRouter>
        <DomainHealthRail page={null} items={items} />
      </MemoryRouter>,
    )

    const region = screen.getByRole('region', { name: 'Domain Health' })
    for (const label of ALL_DIMENSION_LABELS) {
      expect(within(region).getByText(label)).toBeTruthy()
    }

    expect(within(region).getByText('Needs attention')).toBeTruthy()
    expect(within(region).getByText(/Not currently measured/)).toBeTruthy()
    expect(within(region).queryByText(/^\d+%$/)).toBeNull()
    expect(within(region).getByText(/Contract support/)).toBeTruthy()
  })

  it('retains all eight dimensions expanded with stronger hierarchy in the compact Operate rail', () => {
    const source = record('source', 'official-releases', 'Official release records')
    const items = [source]

    render(
      <MemoryRouter>
        <DomainHealthRail page={null} items={items} compact />
      </MemoryRouter>,
    )

    const region = screen.getByRole('region', { name: 'Domain Health' })
    for (const label of ALL_DIMENSION_LABELS) {
      expect(within(region).getByText(label)).toBeTruthy()
    }
    expect(within(region).queryByText(/^\d+%$/)).toBeNull()
  })
})
