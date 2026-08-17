import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  IntelligenceResourceKind,
  IntelligenceResourceRecord,
  submitIntelligenceResourceFeedback,
} from '@/api/intelligenceResourcesApi'

import { ExploreIntelligence } from './LivingIntelligence'

vi.mock('@/api/intelligenceResourcesApi', async () => {
  const actual = await vi.importActual<typeof import('@/api/intelligenceResourcesApi')>(
    '@/api/intelligenceResourcesApi',
  )
  return { ...actual, submitIntelligenceResourceFeedback: vi.fn() }
})

const availableAt = '2026-08-14T18:00:00.000Z'

function record(
  kind: IntelligenceResourceKind,
  id: string,
  options: {
    readonly title?: string
    readonly payload?: unknown
    readonly provenance?: IntelligenceResourceRecord['provenance']
  } = {},
): IntelligenceResourceRecord {
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
      as_of: availableAt,
      available_at: availableAt,
    },
    availability: 'available',
    title: options.title ?? `${kind} ${id}`,
    summary: `${kind} summary`,
    subject_refs: [],
    provenance: options.provenance ?? [],
    supersedes: null,
    payload: options.payload ?? {},
    degraded_reason_refs: [],
  }
}

describe('Living Intelligence challenge boundary', () => {
  beforeEach(() => {
    vi.mocked(submitIntelligenceResourceFeedback).mockReset()
  })

  it('records an exact attributed proposal without claiming downstream effects', async () => {
    const source = record('source', 'official-records')
    const shift = record('shift', 'material-change', {
      title: 'Material change',
      payload: { why_it_matters: 'The maintained assessment changed.' },
      provenance: [source.reference],
    })
    const feedback = record('feedback', 'source-weighting', {
      title: 'Feedback proposal: source weighting',
      provenance: [shift.reference],
    })
    vi.mocked(submitIntelligenceResourceFeedback).mockResolvedValue({
      contract: 'ace.intelligence.resource-feedback-admission/v1alpha1',
      feedback: {
        contract: 'ace.intelligence.resource-feedback-receipt/v1alpha1',
        request: {
          feedback_id: 'resource_feedback:recorded',
          feedback_digest: `sha256:${'a'.repeat(64)}`,
          target: shift.reference,
          correction_intent: 'missing_source',
          note: 'The August filing is absent from the evidence set.',
          evidence: [source.reference],
          authenticated_context: { actor_ref: 'user:default' },
        },
        disposition: 'recorded_proposal_only',
        changes_target: false,
        changes_source_trust: false,
        changes_ranking: false,
        triggers_recalculation: false,
        receipt_id: 'resource_feedback_receipt:recorded',
        receipt_digest: `sha256:${'b'.repeat(64)}`,
      },
      record: { storage_id: 'immutable_record:recorded', material_hash: `sha256:${'c'.repeat(64)}` },
      transaction: { receipt_id: 'append_only_receipt:recorded', request_hash: `sha256:${'d'.repeat(64)}` },
    })

    render(
      <MemoryRouter>
        <ExploreIntelligence items={[source, shift, feedback]} />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Open Why?' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByText('Challenge or correct this conclusion'))

    expect(within(dialog).getByText('This claim is outdated')).toBeTruthy()
    expect(within(dialog).getByText('The entity mapping is wrong')).toBeTruthy()
    expect(within(dialog).getByText('ACE missed a source')).toBeTruthy()
    expect(within(dialog).getByText('A source is over-weighted')).toBeTruthy()
    expect(within(dialog).getByText('Feedback proposal: source weighting')).toBeTruthy()
    expect(within(dialog).getByText(/does not claim that it changed authority/)).toBeTruthy()

    fireEvent.click(within(dialog).getByRole('button', { name: 'ACE missed a source' }))
    const note = within(dialog).getByLabelText('What should ACE review?')
    fireEvent.input(note, {
      target: { value: 'The August filing is absent from the evidence set.' },
    })
    expect(note).toHaveProperty('value', 'The August filing is absent from the evidence set.')
    const submit = within(dialog).getByRole('button', { name: 'Record proposal' }) as HTMLButtonElement
    expect(submit.disabled).toBe(false)
    fireEvent.click(submit)

    await waitFor(() => {
      expect(within(dialog).getByText(/Recorded · resource_feedback_receipt:recorded/)).toBeTruthy()
    })
    expect((within(dialog).getByRole('button', { name: 'Record proposal' }) as HTMLButtonElement).disabled).toBe(true)
    expect(submitIntelligenceResourceFeedback).toHaveBeenCalledWith(expect.objectContaining({
      target: shift.reference,
      correctionIntent: 'missing_source',
      note: 'The August filing is absent from the evidence set.',
      evidence: [source.reference],
    }))
  })
})
