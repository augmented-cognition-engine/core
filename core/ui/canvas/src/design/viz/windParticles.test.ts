import { describe, it, expect } from 'vitest'
import { windToParticles } from './windParticles'
import type { WindSide } from './types'

const side = (over: Partial<WindSide>): WindSide => ({
  bias: 'up',
  kind: 'tailwind',
  conviction: { band: 'strong', score: 0.7, directional: true, chop_likely: false },
  ratio: 2,
  heavy: 'left',
  strength: 0.7,
  active: true,
  imbalance: 0.3,
  left: 1,
  right: 0,
  ...over,
})

describe('windToParticles', () => {
  it('maps an active up wind to intensity + direction', () => {
    expect(windToParticles(side({}))).toEqual({ intensity: 0.7, direction: 'up' })
  })

  it('maps an active down wind to direction down', () => {
    expect(windToParticles(side({ bias: 'down' }))).toEqual({ intensity: 0.7, direction: 'down' })
  })

  it('sheaths an asleep wind (active=false) → none', () => {
    expect(windToParticles(side({ active: false }))).toEqual({ intensity: 0, direction: 'none' })
  })

  it('treats null bias as none', () => {
    expect(windToParticles(side({ bias: null }))).toEqual({ intensity: 0, direction: 'none' })
  })

  it('treats null/undefined side as none', () => {
    expect(windToParticles(null)).toEqual({ intensity: 0, direction: 'none' })
    expect(windToParticles(undefined)).toEqual({ intensity: 0, direction: 'none' })
  })

  it('clamps conviction.score to [0,1]', () => {
    const hi = windToParticles(side({ conviction: { band: 'x', score: 1.8, directional: true, chop_likely: false } }))
    expect(hi.intensity).toBe(1)
    const lo = windToParticles(side({ conviction: { band: 'x', score: -0.5, directional: true, chop_likely: false } }))
    expect(lo.intensity).toBe(0)
  })
})
