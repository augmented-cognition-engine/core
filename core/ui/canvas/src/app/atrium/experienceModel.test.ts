import { describe, expect, it } from 'vitest'

import {
  intelligenceStorySections,
  payloadNumber,
  payloadText,
  productDisplayName,
} from './experienceModel'

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
})
