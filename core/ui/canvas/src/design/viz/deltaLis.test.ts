import { describe, expect, it } from 'vitest'
import { selectDeltaLisBand } from './deltaLis'

describe('selectDeltaLisBand (Delta lens overnight-flow LIS)', () => {
  const strikes = [700, 701, 702, 703, 704, 705]

  it('null when the server shipped no zone (one-sided night)', () => {
    expect(selectDeltaLisBand(strikes, null, null)).toBeNull()
    expect(selectDeltaLisBand(strikes, undefined, undefined)).toBeNull()
    expect(selectDeltaLisBand(strikes, 702, null)).toBeNull()
  })

  it('pads the quoted whole-strike band by half the median gap (full-bar render)', () => {
    const band = selectDeltaLisBand(strikes, 702, 703)
    expect(band).toEqual({ lo: 701.5, hi: 703.5 })
  })

  it('single-strike zone still renders a full bar', () => {
    const band = selectDeltaLisBand(strikes, 702, 702)
    expect(band).toEqual({ lo: 701.5, hi: 702.5 })
  })

  it('falls back to gap 1 when the ladder is empty (half-pad 0.5)', () => {
    const band = selectDeltaLisBand([], 702, 703)
    expect(band).toEqual({ lo: 701.5, hi: 703.5 })
  })
})
