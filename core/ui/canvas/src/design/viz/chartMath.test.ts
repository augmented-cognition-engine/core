import { describe, it, expect } from 'vitest'
import { charmShade, gaugeFractions, balanceSparklinePath } from './chartMath'
import { ewma, balanceZeroCrossings, olsFit } from './chartMath'
import { spotWindowIndices } from './chartMath'

describe('spotWindowIndices', () => {
  const strikes = [60, 95, 98, 100, 102, 105, 140]

  it('keeps only strikes within ±frac of spot, excluding far outliers', () => {
    // spot=100, ±5% → [95,105]; drops the 60 and 140 outliers
    expect(spotWindowIndices(strikes, 100, 0.05)).toEqual([1, 2, 3, 4, 5])
  })

  it('lets a windowed max ignore a deep off-window outlier (the fix)', () => {
    // The deep wall (1000 at strike 60) must NOT set the normalization max.
    const values = [1000, 10, 20, 30, 20, 10, 900]
    const idx = spotWindowIndices(strikes, 100, 0.05)
    const windowedMax = idx.reduce((m, i) => Math.max(m, values[i]), 0)
    expect(windowedMax).toBe(30)
  })

  it('falls back to ALL indices when the window catches fewer than minCount', () => {
    // sparse book: only strike 100 lands in the window → fall back to whole chain
    expect(spotWindowIndices([10, 100, 300], 100, 0.05)).toEqual([0, 1, 2])
  })

  it('falls back to ALL indices when spot is null/non-positive', () => {
    expect(spotWindowIndices([90, 100, 110], null, 0.05)).toEqual([0, 1, 2])
    expect(spotWindowIndices([90, 100, 110], 0, 0.05)).toEqual([0, 1, 2])
  })
})

describe('charmShade', () => {
  it('is warm (more red than blue) for positive charm (tailwind up)', () => {
    const c = charmShade(0.8, 1.0)
    expect(c.r).toBeGreaterThan(c.b)
  })
  it('is cool (more blue than red) for negative charm (headwind down)', () => {
    const c = charmShade(-0.8, 1.0)
    expect(c.b).toBeGreaterThan(c.r)
  })
  it('is near-transparent at zero', () => {
    expect(charmShade(0, 1.0).a).toBeLessThan(0.05)
  })
})

describe('gaugeFractions', () => {
  it('normalizes the stronger side to 1.0', () => {
    expect(gaugeFractions(10, 5)).toEqual({ below: 1, above: 0.5 })
  })
  it('returns zeros when both sides are zero', () => {
    expect(gaugeFractions(0, 0)).toEqual({ below: 0, above: 0 })
  })
})

describe('balanceSparklinePath', () => {
  it('returns an SVG path starting with a moveto', () => {
    const p = balanceSparklinePath([-0.2, 0, 0.3, 0.5], 100, 40)
    expect(p.startsWith('M')).toBe(true)
  })
  it('returns empty string for empty input', () => {
    expect(balanceSparklinePath([], 100, 40)).toBe('')
  })
})

describe('ewma', () => {
  it('returns [] for empty input', () => {
    expect(ewma([], 0.5)).toEqual([])
  })
  it('leaves a constant series unchanged', () => {
    expect(ewma([3, 3, 3], 0.4)).toEqual([3, 3, 3])
  })
  it('alpha=1 is the identity (no smoothing)', () => {
    expect(ewma([1, 5, 2], 1)).toEqual([1, 5, 2])
  })
  it('lags a step: smoothed value sits between old and new', () => {
    const out = ewma([0, 1], 0.5)
    expect(out[0]).toBe(0)
    expect(out[1]).toBeCloseTo(0.5, 6)
  })
  it('preserves length', () => {
    expect(ewma([1, 2, 3, 4], 0.3).length).toBe(4)
  })
})

describe('balanceZeroCrossings', () => {
  it('finds the index where sign flips negative→positive', () => {
    expect(balanceZeroCrossings([-1, -0.5, 0.2, 1])).toEqual([2])
  })
  it('finds multiple flips', () => {
    expect(balanceZeroCrossings([1, -1, 1])).toEqual([1, 2])
  })
  it('returns [] when sign never changes', () => {
    expect(balanceZeroCrossings([1, 2, 3])).toEqual([])
  })
  it('returns [] for empty/singleton', () => {
    expect(balanceZeroCrossings([])).toEqual([])
    expect(balanceZeroCrossings([0.5])).toEqual([])
  })
})

describe('olsFit', () => {
  it('recovers slope and intercept of a clean line', () => {
    const f = olsFit([[0, 1], [1, 3], [2, 5]])   // y = 2x + 1
    expect(f.slope).toBeCloseTo(2, 6)
    expect(f.intercept).toBeCloseTo(1, 6)
  })
  it('returns null slope for <2 points', () => {
    expect(olsFit([[0, 5]]).slope).toBeNull()
    expect(olsFit([]).slope).toBeNull()
  })
  it('y() projects along the fit', () => {
    const f = olsFit([[0, 0], [10, 10]])
    expect(f.y(5)).toBeCloseTo(5, 6)
  })
})
