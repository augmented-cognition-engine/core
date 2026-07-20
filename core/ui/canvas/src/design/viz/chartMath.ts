// Shared chart math + palette consts, extracted from PriceChart so both the SVG layers and the label helpers/overlay can use them without an import cycle.

function _median(sorted: number[]): number {
  const n = sorted.length
  if (n === 0) return 0
  const m = Math.floor(n / 2)
  return n % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2
}

/** Median-centered standard deviation — center on the median (robust to a
 *  skewed/lopsided book), then take the actual stdev (root-mean-square
 *  deviation) around it. "Median then stdev": robust center + real spread. */
export function robustSigma(values: number[]): number {
  if (values.length === 0) return 1
  const med = _median(values.slice().sort((a, b) => a - b))
  const variance = values.reduce((s, v) => s + (v - med) * (v - med), 0) / values.length
  return Math.max(Math.sqrt(variance), 1e-9)
}

// ── Shared intensity law — the SINGLE source both the OI profile bars and the
// Delta heatmap use, so their color/alpha logic is provably identical (Edwin
// 2026-07-08: "same logic", but kept as SEPARATE knobs). Max intensity is
// defined by SIGMA, not a percentile: a value hits full brightness at
// SAT_SIGMA·σ from balance, banded into SIGMA_STEP tiers.
export const SAT_SIGMA = 2.5          // full intensity at 2.5σ
export const SIGMA_STEP = 0.5         // half-sigma tiers
export const OI_ALPHA_FLOOR = 0.10    // OI bars: every bar ≥10% visible
export const OI_ALPHA_CEIL = 0.97

/** Normalized magnitude 0..1 for a signed value against σ: |value|/σ banded
 *  into SIGMA_STEP tiers, full (1) at SAT_SIGMA. This is "how max intensity is
 *  defined" — identical for the OI net bars and the Delta heatmap. */
export function sigmaTierMag(value: number, sigma: number): number {
  const z = Math.abs(value) / (sigma || 1)
  return Math.min(1, (Math.floor(z / SIGMA_STEP) * SIGMA_STEP) / SAT_SIGMA)
}

/** Alpha from a normalized magnitude: floor + m^contrast·(ceil−floor). The
 *  `contrast` is the ratio_scale / delta_scale gamma (1 = linear, >1 dims
 *  valleys harder). Clamped ≥0.2 so the knob can't invert. The OI bars pass
 *  floor 0.10; the Delta heatmap passes floor 0 (transparent at zero flow). */
export function intensityAlpha(
  m: number,
  contrast: number,
  floor = OI_ALPHA_FLOOR,
  ceil = OI_ALPHA_CEIL,
): number {
  const mm = Math.min(1, Math.max(0, m))
  return floor + Math.pow(mm, Math.max(0.2, contrast)) * (ceil - floor)
}

/** Indices of `strikes` within ±`frac` of `center` (spot). The normalization
 *  frame for the OI profile: bar LENGTH and color σ scale against the max/spread
 *  of the strikes in THIS window, not the whole chain — so a real but deep OI
 *  wall (a 580 put cluster ~20% below a 735 spot) can't set the denominator and
 *  crush every near-spot bar to a sliver.
 *
 *  Falls back to ALL indices when `center` isn't a positive number, or when the
 *  window catches fewer than `minCount` strikes (sparse book, spot near the
 *  scrape edge) — a too-tight window must never blank the scale. */
export function spotWindowIndices(
  strikes: readonly number[],
  center: number | null | undefined,
  frac: number,
  minCount = 5,
): number[] {
  const all = strikes.map((_, i) => i)
  if (center == null || !(center > 0) || !(frac > 0)) return all
  const lo = center * (1 - frac)
  const hi = center * (1 + frac)
  const win = all.filter((i) => strikes[i] >= lo && strikes[i] <= hi)
  return win.length >= minCount ? win : all
}

// Per-profile color palette (rgb tuples) — used by Greek peak markers.
export const VA_COLOR_GAMMA = '96,165,250'   // blue (Tailwind blue-400)
export const VA_COLOR_DELTA = '192,132,252'  // purple (Tailwind purple-400)
export const VA_COLOR_CHARM = '244,114,182'  // pink (Tailwind pink-400)
export const VA_COLOR_VANNA = '52,211,153'   // emerald (Tailwind emerald-400)

/** Median adjacent-strike gap across a rows array.
 *  Rows may mix $1 core and $5 wing strikes, so median beats mean.
 *  Returns 1.0 as a safe fallback when fewer than 2 rows are present. */
export function medianStrikeGap(strikes: ReadonlyArray<{ strike: number }>): number {
  if (strikes.length < 2) return 1
  const sorted = strikes.map((r) => r.strike).slice().sort((a, b) => a - b)
  const gaps: number[] = []
  for (let i = 1; i < sorted.length; i++) {
    const g = sorted[i] - sorted[i - 1]
    if (g > 0) gaps.push(g)
  }
  if (gaps.length === 0) return 1
  const g = gaps.slice().sort((a, b) => a - b)
  const m = Math.floor(g.length / 2)
  return g.length % 2 ? g[m] : (g[m - 1] + g[m]) / 2
}

/** Pad a quoted band [lo, hi] outward by half a strike spacing so the rendered
 *  rectangle covers the full edge bars (not just their centres).
 *
 *  Doctrine (2026-06-10): band levels are QUOTED at whole-dollar strikes (e.g.
 *  LIS 707–713). Drawing the rectangle at the exact quoted values cuts each edge
 *  bar in half — the 707-bar is only half inside the grey region. Padding by
 *  half the median adjacent gap extends both edges to the bar boundary:
 *    lo_render = lo − halfSpacing
 *    hi_render = hi + halfSpacing
 *  Quoted values in levels.txt / API / read logic are unchanged — render only. */
export function padBand(lo: number, hi: number, halfSpacing: number): { lo: number; hi: number } {
  return { lo: lo - halfSpacing, hi: hi + halfSpacing }
}

// ── Charm-gradient render helpers (Phase 1) ──────────────────────────────────

export interface Rgba { r: number; g: number; b: number; a: number }

/** Diverging tint for the charm field: warm = tailwind up (charm >= 0),
 *  cool = headwind down (charm < 0). Opacity scales with |value| / maxAbs,
 *  capped at 0.46 so the underlying heatmap stays visible. */
export function charmShade(value: number, maxAbs: number): Rgba {
  const m = maxAbs > 0 ? Math.min(1, Math.abs(value) / maxAbs) : 0
  const a = Math.min(0.46, m * 0.6)
  return value >= 0
    ? { r: 255, g: 150, b: 60, a }   // warm
    : { r: 70, g: 150, b: 255, a }   // cool
}

/** Tug-of-war gauge: normalize each side's charm strength to the stronger side. */
export function gaugeFractions(lhp: number, rhp: number): { below: number; above: number } {
  const mx = Math.max(lhp, rhp)
  if (mx <= 0) return { below: 0, above: 0 }
  return { below: lhp / mx, above: rhp / mx }
}

/** Zero-centered sparkline of charm_balance (each value in [-1, 1]) across a
 *  w×h strip. Returns an SVG path; '' for empty input. */
export function balanceSparklinePath(balances: number[], w: number, h: number): string {
  if (balances.length === 0) return ''
  const mid = h / 2
  const amp = h / 2 - 2
  const dx = balances.length > 1 ? w / (balances.length - 1) : 0
  return balances
    .map((b, i) => {
      const x = i * dx
      const y = mid - Math.max(-1, Math.min(1, b)) * amp
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

/** Exponential weighted moving average — the "rolling 0" smoother for the charm
 *  balance series. out[0] = values[0]; out[i] = alpha*values[i] + (1-alpha)*out[i-1].
 *  alpha in (0,1]; alpha=1 is the identity. Returns same-length series; [] for []. */
export function ewma(values: number[], alpha: number): number[] {
  if (values.length === 0) return []
  const out: number[] = [values[0]]
  for (let i = 1; i < values.length; i++) {
    out.push(alpha * values[i] + (1 - alpha) * out[i - 1])
  }
  return out
}

/** Indices where a (smoothed) series crosses zero — sign flips between i-1 and i.
 *  Returns the index i of the first sample on the new side. Treats 0 as matching
 *  the previous sign so a touch-and-return is not a crossing. */
export function balanceZeroCrossings(values: number[]): number[] {
  const out: number[] = []
  for (let i = 1; i < values.length; i++) {
    const prev = values[i - 1]
    const curr = values[i]
    if ((prev < 0 && curr > 0) || (prev > 0 && curr < 0)) out.push(i)
  }
  return out
}

/** Ordinary least-squares fit of [x,y] points → slope/intercept + a projector.
 *  slope is null for <2 points (and y() returns the lone y, or NaN if empty). */
export function olsFit(points: Array<[number, number]>): {
  slope: number | null; intercept: number | null; y: (x: number) => number
} {
  const n = points.length
  if (n < 2) {
    const only = n === 1 ? points[0][1] : NaN
    return { slope: null, intercept: null, y: () => only }
  }
  let sx = 0, sy = 0, sxx = 0, sxy = 0
  for (const [x, y] of points) { sx += x; sy += y; sxx += x * x; sxy += x * y }
  const denom = n * sxx - sx * sx
  if (Math.abs(denom) < 1e-12) { const mean = sy / n; return { slope: 0, intercept: mean, y: () => mean } }
  const slope = (n * sxy - sx * sy) / denom
  const intercept = (sy - slope * sx) / n
  return { slope, intercept, y: (x: number) => intercept + slope * x }
}
