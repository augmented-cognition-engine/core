import { describe, it, expect } from 'vitest'
import { wallLabels } from './chartLabels'
import { padBand, medianStrikeGap } from './chartMath'
import type { OIProfileView } from './types'

const oi = {
  rows: [
    { strike: 7580, net_oi: -100, net_change: -2000 },
    { strike: 7590, net_oi: 20, net_change: 500 },
    { strike: 7600, net_oi: 300, net_change: 4200 },
  ],
  net_clusters: [
    { strike: 7600, magnitude: 'major', side: 'call' },
    { strike: 7560, magnitude: 'minor', side: 'put' },
  ],
} as unknown as OIProfileView

describe('wallLabels', () => {
  it('emits a tag only for MAJOR clusters above the 1500 noise floor', () => {
    const out = wallLabels(oi)
    expect(out).toHaveLength(1)
    expect(out[0].strike).toBe(7600)
    expect(out[0].built).toBe(true)
    expect(out[0].text).toBe('▲ +4.2k')
  })
  it('uses tenths under 10k and drops the minor cluster', () => {
    const oi2 = { rows: [{ strike: 7600, net_oi: 1, net_change: -3400 }],
      net_clusters: [{ strike: 7600, magnitude: 'major', side: 'put' }] } as unknown as OIProfileView
    const out = wallLabels(oi2)
    expect(out[0].built).toBe(false)
    expect(out[0].text).toBe('▼ −3.4k')
  })
  it('suppresses wall Δ tags on cold-start (oi_flow_warming) — fabricated flow', () => {
    const warming = { ...oi, oi_flow_warming: true } as unknown as OIProfileView
    expect(wallLabels(warming)).toEqual([])
  })
})


// ── padBand / medianStrikeGap — full-bar fill padding (doctrine 2026-06-10) ─

describe('medianStrikeGap', () => {
  it('returns 1.0 for a pure $1 ladder', () => {
    const rows = [707, 708, 709, 710, 711, 712, 713].map((s) => ({ strike: s }))
    expect(medianStrikeGap(rows)).toBe(1)
  })
  it('returns 1.0 for a mixed $1/$5 ladder (NQ near-term structure)', () => {
    // 241 gaps of 1, 51 gaps of 5 — median is 1.0
    const s1 = Array.from({ length: 242 }, (_, i) => ({ strike: 700 + i }))
    const s5 = Array.from({ length: 52 }, (_, i) => ({ strike: 1000 + i * 5 }))
    expect(medianStrikeGap([...s1, ...s5])).toBe(1)
  })
  it('returns 5.0 for a pure $5 ladder', () => {
    const rows = [700, 705, 710, 715, 720].map((s) => ({ strike: s }))
    expect(medianStrikeGap(rows)).toBe(5)
  })
  it('returns 1.0 fallback for fewer than 2 rows', () => {
    expect(medianStrikeGap([{ strike: 700 }])).toBe(1)
    expect(medianStrikeGap([])).toBe(1)
  })
})

describe('padBand', () => {
  it('pads lo down and hi up by halfSpacing', () => {
    const { lo, hi } = padBand(707, 713, 0.5)
    expect(lo).toBe(706.5)
    expect(hi).toBe(713.5)
  })
  it('is symmetric — pad of 0 is a no-op', () => {
    const { lo, hi } = padBand(707, 713, 0)
    expect(lo).toBe(707)
    expect(hi).toBe(713)
  })
  it('works with fractional spacing (wing strikes at $5 spacing → halfSpacing=2.5)', () => {
    const { lo, hi } = padBand(720, 730, 2.5)
    expect(lo).toBeCloseTo(717.5)
    expect(hi).toBeCloseTo(732.5)
  })
})
