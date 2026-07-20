export type CorridorBar = { strike: number; width: number; sign: -1 | 0 | 1 }

/** Max |value| across the supplied arrays → shared scale so bands are
 *  comparable. Never returns 0 (safe divisor); 1 when everything is empty. */
export function corridorMaxAbs(valueArrays: number[][]): number {
  const all = valueArrays.flat().map(Math.abs)
  const m = all.length ? Math.max(...all) : 0
  return m > 0 ? m : 1
}

/** One bar per strike: width = |value| / maxAbs (clamped to [0,1]), sign of value. */
export function bandBars(strikes: number[], values: number[], maxAbs: number): CorridorBar[] {
  return values.map((v, i) => ({
    strike: strikes[i],
    width: Math.min(1, Math.abs(v) / maxAbs),
    sign: v > 0 ? 1 : v < 0 ? -1 : 0,
  }))
}

/** Row index (in the DESCENDING-rendered bars — highest strike first) where the
 *  spot line inserts; the line renders ABOVE the bar at this index. First bar
 *  with strike <= spot; bars.length when spot is below the whole ladder (the
 *  above-all case yields 0 naturally). null = no line (no bars / no spot). */
export function spotRowIndex(
  bars: CorridorBar[],
  spot: number | null | undefined,
): number | null {
  if (spot == null || bars.length === 0) return null
  const i = bars.findIndex((b) => b.strike <= spot)
  return i === -1 ? bars.length : i
}

/** Port of derive/kde.py build_gaussian_kernel — sigma = radius/3. Returns
 *  2*radius+1 normalized weights summing to 1; radius <= 0 → [1] (delta
 *  kernel, no smoothing). Must stay numerically identical to the backend. */
export function gaussianKernel(radius: number): number[] {
  if (radius <= 0) return [1]
  radius = Math.round(radius) // python range() requires an int; a float would silently diverge
  const sigma = radius / 3
  const denom = 2 * sigma * sigma
  const raw: number[] = []
  for (let o = -radius; o <= radius; o++) raw.push(Math.exp(-(o * o) / denom))
  let s = raw.reduce((a, b) => a + b, 0)
  if (s <= 0) s = 1 // unreachable (center tap is 1.0) — kept for parity with kde.py
  return raw.map((w) => w / s)
}

/** Port of derive/kde.py convolve_same — 1D "same" convolution with
 *  EDGE-RENORMALIZED boundaries: taps falling outside the array are dropped
 *  and the remaining weights renormalized to sum 1, so edge values are the
 *  weighted average of the neighbors we actually have (no zero-pad droop). */
export function convolveSame(values: number[], kernel: number[]): number[] {
  const n = values.length
  const k = kernel.length
  const radius = Math.floor(k / 2)
  const out = new Array<number>(n).fill(0)
  for (let i = 0; i < n; i++) {
    let acc = 0
    let wsum = 0
    for (let j = 0; j < k; j++) {
      const src = i + (j - radius)
      if (src >= 0 && src < n) {
        acc += values[src] * kernel[j]
        wsum += kernel[j]
      }
    }
    out[i] = wsum > 0 ? acc / wsum : 0
  }
  return out
}
