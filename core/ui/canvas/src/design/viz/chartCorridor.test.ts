import { describe, it, expect } from 'vitest'
import { bandBars, corridorMaxAbs, spotRowIndex, gaussianKernel, convolveSame } from './chartCorridor'
import type { CorridorBar } from './chartCorridor'

describe('corridorMaxAbs', () => {
  it('is the max absolute value across all arrays', () => {
    expect(corridorMaxAbs([[10, -40], [5], [-100, 20]])).toBe(100)
  })

  it('returns 1 (safe divisor) when every array is empty', () => {
    expect(corridorMaxAbs([[], [], []])).toBe(1)
  })
})

describe('bandBars', () => {
  it('normalizes |value| to [0,1] width against the shared max and keeps sign', () => {
    const bars = bandBars([7500, 7510, 7520], [50, -100, 0], 100)
    expect(bars).toEqual([
      { strike: 7500, width: 0.5, sign: 1 },
      { strike: 7510, width: 1.0, sign: -1 },
      { strike: 7520, width: 0.0, sign: 0 },
    ])
  })
})

describe('spotRowIndex', () => {
  // Descending strikes, matching BandColumn's render order (highest on top).
  const ladder = [7530, 7520, 7510, 7500].map(
    (strike): CorridorBar => ({ strike, width: 0.5, sign: 1 }),
  )

  it('inserts between the bracketing strikes', () => {
    expect(spotRowIndex(ladder, 7515)).toBe(2)
  })

  it('lands directly above an exact strike hit', () => {
    expect(spotRowIndex(ladder, 7520)).toBe(1)
  })

  it('clamps to the top when spot is above the range', () => {
    expect(spotRowIndex(ladder, 7600)).toBe(0)
  })

  it('clamps to the bottom when spot is below the range', () => {
    expect(spotRowIndex(ladder, 7400)).toBe(4)
  })

  it('returns null for empty bars', () => {
    expect(spotRowIndex([], 7500)).toBeNull()
  })

  it('returns null for null spot', () => {
    expect(spotRowIndex(ladder, null)).toBeNull()
  })

  it('returns null for undefined spot', () => {
    expect(spotRowIndex(ladder, undefined)).toBeNull()
  })
})

describe('gaussianKernel (port of derive/kde.py build_gaussian_kernel)', () => {
  it('radius <= 0 is the delta kernel (no smoothing)', () => {
    expect(gaussianKernel(0)).toEqual([1])
  })

  it('radius 3 reproduces the python kernel', () => {
    const expected = [
      0.004433048175, 0.054005582622, 0.242036229376, 0.399050279652,
      0.242036229376, 0.054005582622, 0.004433048175,
    ]
    const k = gaussianKernel(3)
    expect(k).toHaveLength(7)
    k.forEach((w, i) => expect(w).toBeCloseTo(expected[i], 10))
  })

  it('radius 6 reproduces the python kernel', () => {
    const expected = [
      0.002218195855, 0.008773134792, 0.027023157603, 0.064825185139,
      0.121109390075, 0.176213122789, 0.199675627498, 0.176213122789,
      0.121109390075, 0.064825185139, 0.027023157603, 0.008773134792,
      0.002218195855,
    ]
    const k = gaussianKernel(6)
    expect(k).toHaveLength(13)
    k.forEach((w, i) => expect(w).toBeCloseTo(expected[i], 10))
  })
})

describe('convolveSame (port of derive/kde.py convolve_same)', () => {
  // Signed vector shorter than the radius-6 kernel — exercises the
  // edge-renormalized boundary on every output position.
  const v = [0.0, -50.0, 200.0, 1000.0, -300.0, 40.0, 0.0, 5.0]

  it('radius-3 smoothing matches the backend output (round-trip fidelity)', () => {
    const expected = [
      4.47782796155, 86.165812145811, 295.027994289817, 374.306600888619,
      142.604224012019, -1.493257136987, -0.931427645867, 4.039254759718,
    ]
    const out = convolveSame(v, gaussianKernel(3))
    out.forEach((x, i) => expect(x).toBeCloseTo(expected[i], 9))
  })

  it('radius-6 smoothing matches the backend output', () => {
    const expected = [
      120.833304375843, 164.953985585848, 194.025560131733, 190.304358009964,
      152.118390426337, 98.835334035784, 53.331465080389, 25.110242505809,
    ]
    const out = convolveSame(v, gaussianKernel(6))
    out.forEach((x, i) => expect(x).toBeCloseTo(expected[i], 9))
  })

  it('empty input returns empty output', () => {
    expect(convolveSame([], gaussianKernel(3))).toEqual([])
  })
})
