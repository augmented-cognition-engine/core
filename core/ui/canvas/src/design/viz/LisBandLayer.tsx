import { selectDeltaLisBand } from './deltaLis'

const X_FULL = 100 // full chart width in viewBox units

interface Props {
  strikes: number[]              // ladder for half-gap padding (full-bar renders)
  lo: number | null | undefined  // quoted whole-strike band bounds (server flip_zone)
  hi: number | null | undefined
  color: string                  // 'r,g,b' token
  dash?: string                  // edge dash pattern; solid when omitted
  fillAlpha?: number
  edgeAlpha?: number
  edgeWidth?: number
  /** Layered-stroke glow under the edges (Edwin 2026-07-09: the flow LIS was
   *  too dark). Stacked translucent strokes, not an SVG filter — a filter on a
   *  zero-height horizontal line has an empty bbox and silently renders nothing. */
  glow?: boolean
  priceToY: (p: number) => number
}

// Generic server-LIS band — one full-width zone: fill + top/bottom edges,
// padded by half the median strike gap (whole-strike quotes → full-bar
// renders). One component, three tenants: amber = flow LIS (overnight-change
// flip), cyan = next-5 rolling LIS, teal = next-3 rolling LIS — same flip
// grammar ("green to red...the change in dominance"), different book.
// Draws nothing when the server found no flip (one-sided book/night).
export function LisBandLayer({ strikes, lo, hi, color, dash = '2 1.2',
                               fillAlpha = 0.10, edgeAlpha = 0.70,
                               edgeWidth = 0.6, glow = false, priceToY }: Props) {
  const band = selectDeltaLisBand(strikes ?? [], lo, hi)
  if (!band) return null
  const yTop = priceToY(band.hi)
  const yBot = priceToY(band.lo)
  if (!isFinite(yTop) || !isFinite(yBot)) return null
  const h = Math.max(0.4, yBot - yTop)
  const edge = (y: number) => (
    <>
      {glow && (
        <>
          <line x1={0} x2={X_FULL} y1={y} y2={y}
                stroke={`rgba(${color},0.14)`} strokeWidth={edgeWidth * 8}
                vectorEffect="non-scaling-stroke" />
          <line x1={0} x2={X_FULL} y1={y} y2={y}
                stroke={`rgba(${color},0.30)`} strokeWidth={edgeWidth * 4}
                vectorEffect="non-scaling-stroke" />
        </>
      )}
      <line x1={0} x2={X_FULL} y1={y} y2={y}
            stroke={`rgba(${color},${edgeAlpha})`} strokeWidth={edgeWidth}
            strokeDasharray={dash} vectorEffect="non-scaling-stroke" />
    </>
  )
  return (
    <g pointerEvents="none">
      <rect x={0} y={yTop} width={X_FULL} height={h}
            fill={`rgba(${color},${fillAlpha})`} stroke="none" />
      <g>{edge(yTop)}</g>
      <g>{edge(yBot)}</g>
    </g>
  )
}
