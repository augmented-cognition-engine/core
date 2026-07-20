/**
 * WindParticleLayer — animated, threshold-gated wind "push" (one wind per instance).
 *
 * Particles RISE from the bottom (tailwind / up) or FALL from the top (headwind / down)
 * within the price-action band. Density + speed scale with how decisive the wind is
 * (intensity). Renders NOTHING when intensity < THRESHOLD or direction is 'none' — so
 * the chart stays quiet until there's a real wind.
 *
 * Parameterized so charm (steady gold motes) and vanna (sharp cyan streaks, gated on its
 * own `active` upstream) share one engine:
 *   - shape='mote'   → soft round circles, slower drift (charm)
 *   - shape='streak' → thin vertical slivers, faster (vanna — the sword)
 *
 * Native SVG SMIL animation (no requestAnimationFrame, no canvas) — it lives in the
 * chart's viewBox (0..100) and paints behind the price action. (Under
 * preserveAspectRatio='none' the marks render slightly stretched — fine for ambient motion.)
 */
const Y_DATA_TOP = 4
const Y_DATA_BOTTOM = 93
const THRESHOLD = 0.2 // dead-zone: below this, nothing shows

// Display law — deliberately CALM (Edwin 2026-07-09: the max-drive render was
// obnoxious). intensity = conviction.score, which is a decisiveness gate that
// SATURATES at 1.0 on any decisive day — so full drive is the common case,
// not the rare one, and the ceiling must read as ambient weather, not an
// alarm. Few motes, slow drift, low opacity; the ReadPanel carries the
// magnitude story (ramp + ratio + percentile), the chart only whispers it.
const MAX_EXTRA_PARTICLES = 5 // n = 3..8 (was 6..22)
const MOTE_DUR_BASE = 5.0 // s (was 2.6)
const MOTE_DUR_MIN = 3.0 // s (was 0.6 — strobe territory)
const STREAK_DUR_BASE = 2.4 // s (was 1.6)
const STREAK_DUR_MIN = 1.4 // s
const OPACITY_FLOOR = 0.1 // peak opacity 0.10..0.32 (was 0.3..0.8)
const OPACITY_SPAN = 0.22

export type ParticleShape = 'mote' | 'streak'

export function WindParticleLayer({
  intensity,
  direction,
  color,
  shape = 'mote',
  xLeft = 4,
  xRight = 80,
}: {
  intensity: number // 0..1
  direction: 'up' | 'down' | 'none'
  color: string // e.g. 'rgb(255,205,90)'
  shape?: ParticleShape
  xLeft?: number
  xRight?: number
}) {
  if (direction === 'none' || intensity < THRESHOLD) return null
  const strength = Math.min(1, (intensity - THRESHOLD) / (1 - THRESHOLD))
  const n = 3 + Math.round(strength * MAX_EXTRA_PARTICLES)
  const baseDur = shape === 'streak' ? STREAK_DUR_BASE : MOTE_DUR_BASE // streaks blow faster (sharper wind)
  const durMin = shape === 'streak' ? STREAK_DUR_MIN : MOTE_DUR_MIN
  const dur = Math.max(durMin, baseDur - strength * 1.6) // s; faster = stronger, floored well above strobe
  const up = direction === 'up'
  const yStart = up ? Y_DATA_BOTTOM : Y_DATA_TOP
  const yEnd = up ? Y_DATA_BOTTOM - 52 : Y_DATA_TOP + 52 // travels ~half the band, then fades
  const peakOpacity = (OPACITY_FLOOR + strength * OPACITY_SPAN).toFixed(2)
  return (
    <g style={{ pointerEvents: 'none' }}>
      {Array.from({ length: n }, (_, i) => {
        const frac = (i * 0.6180339887) % 1 // golden-ratio spread for even x
        const cx = xLeft + frac * (xRight - xLeft)
        const begin = `${((i / n) * dur).toFixed(2)}s`
        const opacityAnim = (
          <animate
            attributeName="opacity"
            values={`0;${peakOpacity};0`}
            keyTimes="0;0.3;1"
            dur={`${dur}s`}
            begin={begin}
            repeatCount="indefinite"
          />
        )
        if (shape === 'streak') {
          // thin vertical sliver — a sharp blade vs charm's soft mote
          const w = 0.22
          const h = 2.4
          return (
            <rect key={i} x={cx - w / 2} y={yStart} width={w} height={h} fill={color} opacity={0}>
              <animate
                attributeName="y"
                from={yStart}
                to={yEnd}
                dur={`${dur}s`}
                begin={begin}
                repeatCount="indefinite"
              />
              {opacityAnim}
            </rect>
          )
        }
        const r = 0.25 + ((i * 7) % 5) / 14
        return (
          <circle key={i} cx={cx} cy={yStart} r={r} fill={color} opacity={0}>
            <animate
              attributeName="cy"
              from={yStart}
              to={yEnd}
              dur={`${dur}s`}
              begin={begin}
              repeatCount="indefinite"
            />
            {opacityAnim}
          </circle>
        )
      })}
    </g>
  )
}
