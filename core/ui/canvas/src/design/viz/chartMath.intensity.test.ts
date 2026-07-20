import { describe, expect, it } from 'vitest'
import { sigmaTierMag, intensityAlpha, SAT_SIGMA, OI_ALPHA_FLOOR, OI_ALPHA_CEIL } from './chartMath'

describe('sigmaTierMag / intensityAlpha (shared OI + Delta intensity law)', () => {
  it('sigmaTierMag: full (1) at ≥ 2.5σ, zero at 0, half-σ tiered', () => {
    expect(sigmaTierMag(0, 100)).toBe(0)
    expect(sigmaTierMag(2.5 * 100, 100)).toBe(1)     // exactly 2.5σ → full
    expect(sigmaTierMag(5 * 100, 100)).toBe(1)        // past 2.5σ clamps to 1
    // 1.0σ → floor(1.0/0.5)*0.5 / 2.5 = 1.0/2.5 = 0.4
    expect(sigmaTierMag(1.0 * 100, 100)).toBeCloseTo(0.4)
  })

  it('intensityAlpha: OI-bar law — floor at m=0, ceil at m=1, gamma via contrast', () => {
    expect(intensityAlpha(0, 1)).toBeCloseTo(OI_ALPHA_FLOOR)   // valley → floor
    expect(intensityAlpha(1, 1)).toBeCloseTo(OI_ALPHA_CEIL)    // peak → ceil
    // contrast>1 suppresses a mid value harder than linear
    expect(intensityAlpha(0.5, 3)).toBeLessThan(intensityAlpha(0.5, 1))
  })

  it('intensityAlpha: Delta heatmap floor 0 → transparent at zero magnitude', () => {
    expect(intensityAlpha(0, 1, 0, OI_ALPHA_CEIL)).toBe(0)
    expect(intensityAlpha(1, 1, 0, OI_ALPHA_CEIL)).toBeCloseTo(OI_ALPHA_CEIL)
  })

  it('SAT_SIGMA is 2.5 (max intensity definition)', () => {
    expect(SAT_SIGMA).toBe(2.5)
  })
})
