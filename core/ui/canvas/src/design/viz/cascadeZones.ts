import type { CascadeBand, ChartData } from './types'

type LadderRung = NonNullable<ChartData['transition_ladder']>[number]

/** Cascade zones from the self-computed transition ladder (theta view).
 *
 * Doctrine: only CLUSTERS draw — multiple expected transitions stacked in the
 * same-ish area (shared cascade_id) mark an acceleration zone; an isolated
 * crossing carries no zone. Output is the CascadeBand shape the (previously
 * GE-fed, retired 2026-06-04) striped CascadeLayer already renders, so the
 * established zone grammar — stripes, razor emphasis, left-edge greek labels —
 * comes back unchanged.
 */
export function ladderCascades(
  ladder: LadderRung[] | null | undefined,
  spot: number | null | undefined,
  /** Book's median strike gap. Razor = the whole stack within ~ONE strike
   *  (strike-native; a fixed % of spot reads differently on QQQ's $1 grid vs
   *  SPX's $5 grid — Edwin 2026-07-09). Falls back to the legacy 0.15%-of-spot
   *  law when the payload predates strike_spacing. */
  strikeSpacing?: number | null,
): CascadeBand[] {
  if (!ladder || ladder.length === 0) return []
  const groups = new Map<number, LadderRung[]>()
  for (const r of ladder) {
    if (r.cascade_id == null) continue
    const g = groups.get(r.cascade_id)
    if (g) g.push(r)
    else groups.set(r.cascade_id, [r])
  }
  const bands: CascadeBand[] = []
  for (const rows of groups.values()) {
    if (rows.length < 2) continue
    let top = -Infinity
    let bottom = Infinity
    for (const r of rows) {
      if (r.price > top) top = r.price
      if (r.price < bottom) bottom = r.price
    }
    const ref = spot ?? (top + bottom) / 2
    const width_pct = ref > 0 ? ((top - bottom) / ref) * 100 : 0
    const razor = strikeSpacing != null && strikeSpacing > 0
      ? top - bottom <= strikeSpacing
      : width_pct < 0.15
    bands.push({
      top_price: top,
      bottom_price: bottom,
      side: rows[0].side === 'rhp' ? 'upside' : 'downside',
      greeks: [...new Set(rows.map((r) => r.greek))],
      width_pct,
      razor,
    })
  }
  return bands
}
