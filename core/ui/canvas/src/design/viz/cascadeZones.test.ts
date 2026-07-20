import { describe, it, expect } from 'vitest'
import { ladderCascades } from './cascadeZones'

const rung = (over: Partial<NonNullable<Parameters<typeof ladderCascades>[0]>[number]>) => ({
  price: 700,
  pct: 0,
  greek: 'delta',
  side: 'rhp',
  from: 'ITM Puts',
  to: 'OTM Calls',
  cascade: true,
  cascade_id: 1 as number | null,
  ...over,
})

describe('ladderCascades', () => {
  it('returns empty for null/empty ladder', () => {
    expect(ladderCascades(null, 700)).toEqual([])
    expect(ladderCascades([], 700)).toEqual([])
  })

  it('ignores isolated rungs (null cascade_id) — a lone crossing is not a cascade', () => {
    const bands = ladderCascades(
      [rung({ cascade_id: null, cascade: false }), rung({ cascade_id: null, cascade: false, price: 710 })],
      700,
    )
    expect(bands).toEqual([])
  })

  it('groups by cascade_id and spans the cluster, deduping greeks', () => {
    const bands = ladderCascades(
      [
        rung({ price: 717.65, greek: 'charm', cascade_id: 2 }),
        rung({ price: 717.65, greek: 'vanna', cascade_id: 2 }),
        rung({ price: 725.23, greek: 'gamma', cascade_id: 3 }),
        rung({ price: 725.66, greek: 'delta', cascade_id: 3 }),
        rung({ price: 708.96, greek: 'delta', cascade: false, cascade_id: null }),
      ],
      712.29,
    )
    expect(bands).toHaveLength(2)
    const upper = bands.find((b) => b.top_price === 725.66)!
    expect(upper.bottom_price).toBe(725.23)
    expect(upper.greeks).toEqual(['gamma', 'delta'])
    const pair = bands.find((b) => b.top_price === 717.65)!
    expect(pair.bottom_price).toBe(717.65)
    expect(pair.greeks).toEqual(['charm', 'vanna'])
  })

  it('drops degenerate single-row groups', () => {
    expect(ladderCascades([rung({ cascade_id: 7 })], 700)).toEqual([])
  })

  it('maps side rhp→upside, lhp→downside', () => {
    const bands = ladderCascades(
      [
        rung({ price: 701, greek: 'charm', side: 'lhp', cascade_id: 1 }),
        rung({ price: 702, greek: 'vanna', side: 'lhp', cascade_id: 1 }),
        rung({ price: 720, greek: 'charm', side: 'rhp', cascade_id: 2 }),
        rung({ price: 721, greek: 'vanna', side: 'rhp', cascade_id: 2 }),
      ],
      710,
    )
    expect(bands.find((b) => b.top_price === 702)!.side).toBe('downside')
    expect(bands.find((b) => b.top_price === 721)!.side).toBe('upside')
  })

  it('computes width_pct vs spot and flags razor under 0.15% (legacy law, no spacing)', () => {
    const bands = ladderCascades(
      [
        rung({ price: 725.23, greek: 'gamma', cascade_id: 1 }),
        rung({ price: 725.66, greek: 'delta', cascade_id: 1 }),
        rung({ price: 700, greek: 'charm', side: 'lhp', cascade_id: 2 }),
        rung({ price: 704, greek: 'vanna', side: 'lhp', cascade_id: 2 }),
      ],
      712.29,
    )
    const tight = bands.find((b) => b.top_price === 725.66)!
    expect(tight.width_pct).toBeCloseTo(((725.66 - 725.23) / 712.29) * 100, 6)
    expect(tight.razor).toBe(true)
    const wide = bands.find((b) => b.top_price === 704)!
    expect(wide.razor).toBe(false)
  })

  it('razor is strike-native when spacing ships: stack within one strike', () => {
    const ladder = [
      rung({ price: 725.2, greek: 'gamma', cascade_id: 1 }),
      rung({ price: 726.0, greek: 'delta', cascade_id: 1 }),   // 0.8 span
      rung({ price: 700, greek: 'charm', side: 'lhp', cascade_id: 2 }),
      rung({ price: 702.5, greek: 'vanna', side: 'lhp', cascade_id: 2 }),  // 2.5 span
    ]
    // QQQ-style $1 grid: 0.8 <= 1 -> razor; 2.5 > 1 -> wide.
    const q = ladderCascades(ladder, 712.29, 1.0)
    expect(q.find((b) => b.top_price === 726.0)!.razor).toBe(true)
    expect(q.find((b) => b.top_price === 702.5)!.razor).toBe(false)
    // SPX-style $5 grid: both stacks sit within one strike -> both razor.
    const spx = ladderCascades(ladder, 712.29, 5.0)
    expect(spx.every((b) => b.razor)).toBe(true)
  })

  it('falls back to the band midpoint when spot is null', () => {
    const bands = ladderCascades(
      [rung({ price: 710, cascade_id: 1, greek: 'gamma' }), rung({ price: 714, cascade_id: 1 })],
      null,
    )
    expect(bands[0].width_pct).toBeCloseTo((4 / 712) * 100, 6)
  })
})
