import { describe, expect, it } from 'vitest'

import { payloadNumber, payloadText, productDisplayName } from './experienceModel'

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
})
