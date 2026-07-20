import { medianStrikeGap, padBand } from './chartMath'

export interface DeltaLisBand {
  lo: number
  hi: number
}

// Delta lens LIS — the overnight-flow flip zone, SERVER-COMPUTED (canonical
// flip_zone on the r=3-smoothed union d_net; the client never re-derives a
// LIS). This selector only applies the render-side doctrine: quoted values
// are whole-dollar strikes, so the drawn band is padded by half the median
// adjacent-strike gap to cover the full edge bars (render-only — the quoted
// lo/hi in the API stay unchanged). Null when the server found no clean
// red→green handover (one-sided night) — nothing draws, same as the net-OI
// LIS on a one-sided book.
export function selectDeltaLisBand(
  strikes: number[],
  lisLo: number | null | undefined,
  lisHi: number | null | undefined,
): DeltaLisBand | null {
  if (lisLo == null || lisHi == null) return null
  const half = medianStrikeGap((strikes ?? []).map((s) => ({ strike: s }))) / 2
  return padBand(lisLo, lisHi, half)
}
