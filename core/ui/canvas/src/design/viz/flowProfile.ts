import { gaussianKernel, convolveSame } from './chartCorridor'
import { robustSigma, sigmaTierMag, spotWindowIndices } from './chartMath'

export type FlowHue = 'green' | 'red' | 'gray'

export interface FlowCell {
  strike: number
  len01: number   // bar length, 0..1 — churn share of the window peak (SHAPE)
  mag01: number   // color intensity, 0..1 — |Δnet| σ-tier (the heatmap law)
  hue: FlowHue    // sign of Δnet; grey when sub-0.5σ (no false direction)
}

// FLOW PROFILE — the always-on overnight-change strip paired with the 0DTE
// profile. TWO INDEPENDENT CHANNELS (Edwin 2026-07-09: "profile shape =
// total (absolute) OI change... color is net" — the retired heatmap's
// coloring, now on the bars):
//   SHAPE (bar length) = churn (|Δcall| + |Δput| — a rotation never cancels)
//   COLOR = the heatmap law on Δnet: hue by sign (green call-building / red
//   put-building), SATURATION by |Δnet| σ-tiers — NOT by bar length (that's
//   the 0DTE strip's law; here a huge-churn balanced strike must read as a
//   LONG DIM bar, not a long bright one). Grey when sub-0.5σ.
//
// RENDERED ON THE 0DTE PROFILE'S OWN ROW GRID (Edwin 2026-07-09: "it should
// be the same as the 0DTE OI profile...the strikes aren't matching up"): the
// raw union ladder is IRREGULAR — fractional strikes from adjusted far books
// (0.22/0.78 gaps) and $5 wing spacing — which hairlined the bars (heights
// size to the densest gap) and misaligned them against the profile's uniform
// $1 rows. Each raw strike's flow is BINNED to the nearest grid strike
// (summed — flow is additive mass; raw strikes beyond the grid edge are
// off-chart and dropped), then both series are smoothed r=3 on the uniform
// grid, so bar geometry, alignment, and smoothing all match the neighboring
// 0DTE strip bar-for-bar. Length normalized within the ±5% spot window
// (OI_NORM_WINDOW_FRAC doctrine) so a deep-OTM lobe can't crush near-spot.
const NORM_WINDOW_FRAC = 0.05

// Grey rel-floor — mirrors the server combined colored-test (grey_sigma 0.5,
// rel_floor 0.05): a bar is COLORED when |net|/σ ≥ 0.5 OR |net| ≥ 5% of the
// window's peak |net|; grey only when BOTH fail. σ-only greying miscolored
// big-but-sub-σ nodes the 0DTE strip paints.
const GREY_REL_FLOOR = 0.05

export function selectFlowProfile(
  gridStrikes: number[],
  rawStrikes: number[],
  churn: number[],
  dNet: number[],
  spot: number | null,
  opts: { radiusLen?: number; radiusNet?: number } = {},
): FlowCell[] {
  const g = gridStrikes.length
  const n = rawStrikes.length
  if (g < 2 || !n || churn.length !== n || dNet.length !== n) return []
  // Shape radius is a USER KNOB (default 3): flow is a SPARSE change series —
  // unlike the dense standing book (radius_total=6), smoothing spreads lobes
  // into empty neighbor bins, so the right width is a read preference. Color
  // radius stays PINNED at 3 — the bar hue must agree with the amber LIS core
  // (both r=3; pixels = doctrine), so the knob never touches it.
  const radiusLen = opts.radiusLen ?? 3
  const radiusNet = opts.radiusNet ?? 3

  const grid = gridStrikes.slice().sort((a, b) => a - b)
  const step = (grid[g - 1] - grid[0]) / (g - 1)
  if (!(step > 0)) return []

  // Bin raw flow to the nearest grid strike (sum within bin).
  const churnBin = new Array<number>(g).fill(0)
  const netBin = new Array<number>(g).fill(0)
  for (let i = 0; i < n; i++) {
    const idx = Math.round((rawStrikes[i] - grid[0]) / step)
    if (idx < 0 || idx >= g) continue
    if (Math.abs(rawStrikes[i] - grid[idx]) > step / 2 + 1e-9) continue
    churnBin[idx] += churn[i]
    netBin[idx] += dNet[i]
  }

  const act = radiusLen > 0 ? convolveSame(churnBin, gaussianKernel(radiusLen)) : churnBin
  const net = radiusNet > 0 ? convolveSame(netBin, gaussianKernel(radiusNet)) : netBin

  const winIdx = spotWindowIndices(grid, spot, NORM_WINDOW_FRAC)
  const maxAct = winIdx.reduce((m, i) => Math.max(m, Math.abs(act[i])), 1)
  const netSigma = robustSigma(winIdx.map((i) => net[i]))
  const netPeak = winIdx.reduce((m, i) => Math.max(m, Math.abs(net[i])), 0)

  return grid.map((strike, i) => {
    const mag = sigmaTierMag(net[i], netSigma)
    const colored = mag > 0 || (netPeak > 0 && Math.abs(net[i]) >= GREY_REL_FLOOR * netPeak)
    return {
      strike,
      len01: Math.min(1, Math.abs(act[i]) / maxAct),
      mag01: mag,
      hue: !colored ? 'gray' : net[i] >= 0 ? 'green' : 'red',
    }
  })
}
