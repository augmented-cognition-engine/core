import { describe, expect, it } from 'vitest'

import {
  briefRevisionStory,
  intelligenceStoryForRecord,
  intelligenceStorySections,
  payloadNumber,
  payloadText,
  productDisplayName,
} from './experienceModel'
import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'

describe('Atrium experience model', () => {
  it('orients the shell from a domain-owned product identity', () => {
    expect(productDisplayName('product:ai-command-center')).toBe('AI Command Center')
    expect(productDisplayName('product:b2b-market-intelligence')).toBe('B2B Market Intelligence')
  })

  it('falls back without introducing a domain noun', () => {
    expect(productDisplayName(null)).toBe('Your Intelligence')
    expect(productDisplayName('')).toBe('Your Intelligence')
  })

  it('reads only bounded display hints from opaque payloads', () => {
    expect(payloadText({ why_it_matters: '  Material change. ' }, 'why_it_matters')).toBe('Material change.')
    expect(payloadText([], 'why_it_matters')).toBeNull()
    expect(payloadNumber({ confidence: 0.92 }, 'confidence')).toBe(0.92)
    expect(payloadNumber({ confidence: 'high' }, 'confidence')).toBeNull()
  })

  it('projects the canonical What / Why / How / When intelligence grammar', () => {
    const bodyMarkdown = [
      '# Brief',
      '',
      '## What Changed',
      '',
      '- A directive moved to reported operation\\. (inference supports: case:1; uncertainty: bounded)',
      '',
      '## Why It Matters',
      '',
      '- An operating mechanism now exists\\. (inference supports: signal:1; uncertainty: bounded)',
      '',
      '## How We Know',
      '',
      '- Two admitted records support the change\\. (cited supports: observation:1, observation:2)',
      '',
      '## When It Changed',
      '',
      '- The second report arrived 39 days later\\. (cited supports: observation:1, observation:2)',
    ].join('\n')

    expect(intelligenceStorySections({ value_json: JSON.stringify({ body_markdown: bodyMarkdown }) })).toEqual([
      { id: 'what_changed', label: 'What changed', body: 'A directive moved to reported operation.' },
      { id: 'why_it_matters', label: 'Why it matters', body: 'An operating mechanism now exists.' },
      { id: 'how_we_know', label: 'How we know', body: 'Two admitted records support the change.' },
      { id: 'when_it_changed', label: 'When it changed', body: 'The second report arrived 39 days later.' },
    ])
  })

  it('keeps the grammar visible for decision-facing resources without inventing facts', () => {
    const signal: IntelligenceResourceRecord = {
      contract: 'ace.intelligence.resource-record/v1alpha1',
      reference: {
        contract: 'ace.intelligence.resource-reference/v1alpha1',
        product_id: 'product:test',
        resource_kind: 'signal',
        resource_id: 'signal:1',
        resource_digest: 'sha256:signal',
        resource_contract: 'ace.intelligence.signal/v1alpha1',
        revision: 1,
        as_of: '2026-08-13T12:00:00Z',
        available_at: '2026-08-13T12:05:00Z',
      },
      availability: 'available',
      title: 'A new signal arrived',
      summary: 'An official report followed an issued directive.',
      subject_refs: [],
      provenance: [],
      supersedes: null,
      payload: {},
      degraded_reason_refs: [],
    }

    expect(intelligenceStoryForRecord(signal)).toEqual([
      { id: 'what_changed', label: 'What changed', body: 'An official report followed an issued directive.' },
      { id: 'why_it_matters', label: 'Why it matters', body: 'It met the configured relevance and routing criteria, so it now warrants attention.' },
      { id: 'how_we_know', label: 'How we know', body: 'No upstream evidence link is projected for this record.' },
      { id: 'when_it_changed', label: 'When it changed', body: 'The evidence picture is current as of 2026-08-13T12:00:00Z; a distinct event time was not supplied.' },
    ])
  })

  it('explains an append-only Brief revision from exact claims, evidence, and times', () => {
    const record = (
      id: string,
      asOf: string,
      availableAt: string,
      statement: string,
      citationId: string,
      sourceRef: string,
      evidenceId: string,
    ): IntelligenceResourceRecord => ({
      contract: 'ace.intelligence.resource-record/v1alpha1',
      reference: {
        contract: 'ace.intelligence.resource-reference/v1alpha1',
        product_id: 'product:test',
        resource_kind: 'brief',
        resource_id: id,
        resource_digest: `sha256:${id}`,
        resource_contract: 'ace.intelligence.brief/v1alpha1',
        revision: 1,
        as_of: asOf,
        available_at: availableAt,
      },
      availability: 'available',
      title: 'Market movement',
      summary: statement,
      subject_refs: [],
      provenance: [{
        contract: 'ace.intelligence.resource-reference/v1alpha1',
        product_id: 'product:test',
        resource_kind: 'observation',
        resource_id: evidenceId,
        resource_digest: `sha256:${evidenceId}`,
        resource_contract: 'ace.intelligence.observation/v1alpha1',
        revision: 1,
        as_of: asOf,
        available_at: availableAt,
      }],
      supersedes: null,
      payload: { value_json: JSON.stringify({
        claims: [{ statement }],
        citations: [{ citation_id: citationId, source_ref: sourceRef }],
      }) },
      degraded_reason_refs: [],
    })
    const previous = record(
      'brief:previous',
      '2026-07-09T00:00:00Z',
      '2026-08-13T18:00:00Z',
      'Terra input is listed at USD 2.50 per million tokens.',
      'citation:launch',
      'source:openai-launch',
      'observation:launch',
    )
    const current = record(
      'brief:current',
      '2026-07-30T00:00:00Z',
      '2026-08-13T18:01:00Z',
      'Terra input is listed at USD 2.00 per million tokens.',
      'citation:price-performance',
      'source:openai-price-performance',
      'observation:price-performance',
    )

    expect(briefRevisionStory(current, previous)).toEqual([
      {
        id: 'what_changed',
        label: 'What changed',
        body: 'New grounded claims: “Terra input is listed at USD 2.00 per million tokens.”. Retired grounded claims: “Terra input is listed at USD 2.50 per million tokens.”.',
      },
      {
        id: 'why_it_matters',
        label: 'Why this revision exists',
        body: 'This revision incorporates 1 newly available upstream record and leaves 1 prior record outside its new evidence closure.',
      },
      {
        id: 'how_we_know',
        label: 'Evidence change',
        body: 'Newly cited sources: “source:openai-price-performance”. 1 earlier citation no longer supports the latest Brief.',
      },
      {
        id: 'when_it_changed',
        label: 'When it changed',
        body: 'The prior Brief was current as of 2026-07-09T00:00:00Z; this revision is current as of 2026-07-30T00:00:00Z and became available at 2026-08-13T18:01:00Z.',
      },
    ])
  })
})
