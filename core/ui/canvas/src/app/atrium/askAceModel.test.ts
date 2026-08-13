import { describe, expect, it } from 'vitest'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'

import { answerQuestionFromResources } from './askAceModel'

function record(
  kind: IntelligenceResourceRecord['reference']['resource_kind'],
  title: string,
  availableAt: string,
  payload: unknown,
  provenanceCount = 1,
): IntelligenceResourceRecord {
  return {
    contract: 'ace.intelligence.resource-plane-record/v1alpha1',
    reference: {
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:test',
      resource_kind: kind,
      resource_id: `${kind}:${title.toLocaleLowerCase().replace(/ /g, '-')}`,
      resource_digest: `sha256:${'a'.repeat(64)}`,
      resource_contract: `ace.test.${kind}/v1`,
      revision: 1,
      as_of: availableAt,
      available_at: availableAt,
    },
    availability: 'available',
    title,
    summary: `${title} summary`,
    subject_refs: [],
    provenance: Array.from({ length: provenanceCount }, (_, index) => ({
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:test',
      resource_kind: 'source' as const,
      resource_id: `source:${index}`,
      resource_digest: `sha256:${String(index).padStart(64, '0')}`,
      resource_contract: 'ace.test.source/v1',
      revision: 1,
      as_of: availableAt,
      available_at: availableAt,
    })),
    supersedes: null,
    payload,
    degraded_reason_refs: [],
  }
}

describe('Ask ACE answer projection', () => {
  const brief = record('brief', 'AI policy brief', '2026-08-12T01:00:00Z', {
    what_changed: 'The directive moved into reported implementation activity.',
    why_it_matters: 'The change moves the issue from intent to execution.',
    how_we_know: 'Two official publication lineages support the progression.',
    when_it_changed: 'The later implementation report was published on August 12.',
  }, 2)

  it('answers the question directly from the leading governed record', () => {
    const answer = answerQuestionFromResources('What changed in the AI policy brief?', [brief])

    expect(answer?.conclusion).toBe('The directive moved into reported implementation activity.')
    expect(answer?.whyItMatters).toBe('The change moves the issue from intent to execution.')
    expect(answer?.evidence).toEqual([brief])
    expect(answer?.limitation).toContain('has not inferred beyond')
  })

  it('uses the evidence statement when the operator asks how ACE knows', () => {
    expect(answerQuestionFromResources('What evidence supports the AI policy brief?', [brief])?.conclusion)
      .toBe('Two official publication lineages support the progression.')
  })

  it('refuses to fabricate an answer when no governed record matches', () => {
    expect(answerQuestionFromResources('What happened on Mars?', [brief])).toBeNull()
  })
})
