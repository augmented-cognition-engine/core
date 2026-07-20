// core/ui/canvas/src/design/viz/chartTokens.ts
//
// Visualization tokens — the JS mirror of the Layer 4 --ace-chart-* vars in
// tokens.css, plus the chart's layout anchors.
//
// WHY A MIRROR EXISTS AT ALL. The house rule is `style={{ color: 'var(--ace-ink)' }}`,
// not imported constants. A data chart is the sanctioned exception tokens.ts already
// carves out ("SVG fill, JS computed colors"): the renderer multiplies a hue by a
// COMPUTED opacity — σ-tier intensity, OI magnitude, conviction alpha — and you
// cannot do arithmetic on the string "var(--ace-chart-call)". So the hue lives in
// CSS as channels and is mirrored here as numbers.
//
// CONTRACT: every triplet below MUST equal its --ace-chart-* counterpart in
// tokens.css. __enforcement__/chartTokensParity.test.ts asserts it and fails the day
// they drift — the same guarantee tokensContract.test.ts gives the rest of the system.

/** Canvas layout anchors, in viewBox units (the chart draws into a 0..100 box). */
export const chartLayout = {
  dataEnd: 82, // right edge of the plot area
  labelGutter: 18, // 82..100 — right-side level labels
  annotationX: 1.5, // left anchor for in-canvas Δ/flow tags
  profileWidth: 18, // default OI/greek bar length cap
} as const

/** Tabular numerals — proportional digits make a ticking price column jitter. */
export const chartNumericFont = 'var(--ace-font-mono)' as const

export type Rgb = readonly [number, number, number]

/**
 * Domain hues as RGB channels — the canonical source for color math in the chart.
 * Directional/domain semantics (call vs put, one Greek vs another), deliberately NOT
 * the discipline palette and NOT semantic success/danger: a rising market is not
 * "success".
 */
export const hues = {
  call: [74, 222, 128],
  put: [248, 113, 113],
  up: [16, 185, 129],
  down: [239, 68, 68],
  pin: [251, 191, 36],
  accel: [56, 189, 248],
  gamma: [96, 165, 250],
  delta: [192, 132, 252],
  charm: [244, 114, 182],
  vanna: [52, 211, 153],
} as const satisfies Record<string, Rgb>

export type HueName = keyof typeof hues

/**
 * The chart's own vocabulary beyond the domain hues.
 *
 * `tape` is a domain lens (the day's tape read against the standing book). The tints
 * are the same meaning as their parent hue, quieter — a fill under a stroke, never a
 * separate signal. The gold family is a market FORCE (wind, charm pressure), which is
 * why it is not --ace-warning: a strong wind is not a UI warning state. The neutrals
 * exist because the plot area is its own visual world — axis ink and label chips must
 * read against candles and density bands, not against the page.
 */
export const chartInk = {
  tape: [167, 139, 250],
  // DEEP call green — OTM calls (fuel). NOT hues.call: moneyness is encoded as
  // lightness on the same hue, and these two must stay distinguishable.
  callDeep: [34, 197, 94],
  callTint: [134, 239, 172],
  putTint: [252, 165, 165],
  deltaTint: [216, 180, 254],
  gold: [234, 179, 8],
  goldBright: [250, 204, 21],
  goldDeep: [180, 140, 60],
  wind: [255, 205, 90],
  orange: [251, 146, 60],
  ink: [226, 232, 240],
  inkDim: [160, 160, 170],
  inkBright: [245, 248, 252],
  chipBg: [20, 20, 20],
  scrim: [0, 0, 0],
  highlight: [255, 255, 255],
  // A razor cascade is the tight, dangerous one; the amber is the ordinary cascade.
  razor: [251, 146, 60],
  cascade: [251, 191, 36],
  // Linreg fans sit lighter than the parent hue, so a fan never competes with the
  // wall it is drawn beside.
  linregCall: [110, 231, 183],
  linregPut: [252, 165, 165],
} as const satisfies Record<string, Rgb>

/** Horizon lenses — which window's flip zone price is respecting, tellable at a glance. */
export const SHORT_TERM_COLOR = '251,191,36' // overnight Δ — amber
export const ROLL3_LIS_COLOR = '45,212,191' // next-3 rolling LIS — teal
export const FUTURE_LIS_COLOR = '34,211,238' // next-5 rolling LIS — cyan

/** Corridor diff, by the SIDE the net moved (same convention as call/put). */
export const DIFF_CALL_COLOR = '34,197,94'
export const DIFF_PUT_COLOR = '248,113,113'

/** `rgb(r,g,b)` — for an SVG fill/stroke that needs a concrete color. */
export function rgb(hue: Rgb): string {
  return `rgb(${hue[0]},${hue[1]},${hue[2]})`
}

/** `rgba(r,g,b,a)` — the whole reason the channels are numbers. */
export function rgba(hue: Rgb, alpha: number): string {
  return `rgba(${hue[0]},${hue[1]},${hue[2]},${clamp01(alpha)})`
}

function clamp01(n: number): number {
  return n < 0 ? 0 : n > 1 ? 1 : n
}
