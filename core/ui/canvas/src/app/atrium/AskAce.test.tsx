import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'

import { AskAce } from './AskAce'

const brief = {
  contract: 'ace.intelligence.resource-plane-record/v1alpha1',
  reference: {
    contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
    product_id: 'product:world-ai',
    resource_kind: 'brief',
    resource_id: 'brief:ai-policy',
    resource_digest: `sha256:${'a'.repeat(64)}`,
    resource_contract: 'ace.intelligence.brief/v1alpha1',
    revision: 1,
    as_of: '2026-08-13T12:00:00Z',
    available_at: '2026-08-13T12:00:00Z',
  },
  availability: 'available',
  title: 'AI policy moved into implementation',
  summary: 'A directive now has reported implementation activity.',
  subject_refs: [],
  provenance: [{
    contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
    product_id: 'product:world-ai',
    resource_kind: 'source',
    resource_id: 'source:federal-register',
    resource_digest: `sha256:${'b'.repeat(64)}`,
    resource_contract: 'ace.intelligence.source/v1alpha1',
    revision: 1,
    as_of: '2026-08-13T11:00:00Z',
    available_at: '2026-08-13T11:00:00Z',
  }],
  supersedes: null,
  payload: {
    what_changed: 'The policy moved from directive to reported implementation.',
    why_it_matters: 'Execution can now be evaluated against the original intent.',
    when_it_changed: 'The implementation report followed the directive.',
  },
  degraded_reason_refs: [],
} satisfies IntelligenceResourceRecord

describe('Ask ACE', () => {
  it('separates the grounded answer from the exact evidence used', () => {
    render(<AskAce items={[brief]} />)

    fireEvent.click(screen.getByRole('button', { name: 'What changed most recently?' }))

    expect(screen.getByRole('region', { name: 'Ask ACE answer' })).toBeTruthy()
    expect(screen.getByText('The policy moved from directive to reported implementation.')).toBeTruthy()
    expect(screen.getByRole('complementary', { name: 'Evidence used for this answer' })).toBeTruthy()
    expect(screen.getByText('AI policy moved into implementation')).toBeTruthy()
  })
})
