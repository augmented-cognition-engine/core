import { describe, expect, it } from 'vitest'
import { selectFlowProfile } from './flowProfile'

describe('selectFlowProfile (flow binned onto the 0DTE profile grid)', () => {
  const grid = [700, 701, 702, 703, 704]

  it('empty on mismatched/missing arrays or degenerate grid', () => {
    expect(selectFlowProfile(grid, [], [], [], 702)).toEqual([])
    expect(selectFlowProfile(grid, [700], [1, 2], [1], 702)).toEqual([])
    expect(selectFlowProfile([700], [700], [1], [1], 702)).toEqual([])
  })

  it('cells sit EXACTLY on the grid, one per grid strike', () => {
    const cells = selectFlowProfile(grid, [701.78, 703.22], [10, 20], [5, -5], 702, { radiusLen: 0, radiusNet: 0 })
    expect(cells.map((c) => c.strike)).toEqual(grid)
  })

  it('fractional raw strikes bin to the nearest grid strike and SUM', () => {
    // 701.6 and 702.4 both bin to 702 → churn sums; out-of-range 950 dropped.
    const cells = selectFlowProfile(grid, [701.6, 702.4, 950], [4000, 4000, 99999], [1000, 1000, 9], 702, { radiusLen: 0, radiusNet: 0 })
    expect(cells[2].len01).toBe(1)       // 8000 at 702 = window peak
    expect(cells[0].len01).toBe(0)
    expect(cells[4].len01).toBe(0)       // the 950 monster never leaked in
  })

  it('length from churn (unwind as long as build); hue from net sign, grey when balanced', () => {
    const raw = [700, 701, 702, 703, 704]
    const cells = selectFlowProfile(grid, raw,
      [5000, 5000, 5000, 5000, 8000],
      [4000, -4000, 10, 4000, -4000], 702, { radiusLen: 0, radiusNet: 0 })
    expect(cells[4].len01).toBe(1)
    expect(cells[0].hue).toBe('green')
    expect(cells[1].hue).toBe('red')
    expect(cells[2].hue).toBe('gray')    // busy but balanced → grey, not noise-colored
  })

  it('color intensity = the heatmap law (|Δnet| σ-tiers), independent of length', () => {
    const raw = [700, 701, 702, 703, 704]
    const cells = selectFlowProfile(grid, raw,
      [9000, 100, 9000, 100, 100],       // churn: long bars at 700 and 702
      [10, 10, 8000, -8000, 10], 702, { radiusLen: 0, radiusNet: 0 })
    expect(cells[0].len01).toBe(1)
    expect(cells[0].mag01).toBe(0)            // long bar, no winner → DIM (grey)
    expect(cells[0].hue).toBe('gray')
    expect(cells[2].mag01).toBeCloseTo(0.6)   // ±8000 vs σ≈5060 → 1.5σ tier
    expect(cells[2].hue).toBe('green')
    expect(cells[3].mag01).toBeCloseTo(0.6)
    expect(cells[3].hue).toBe('red')
  })
})
