// frontend/src/design/components/Sparkline.tsx
//
// Compact SVG sparkline for calibration history, prediction accuracy
// over time, or any small ordered series. Includes:
//   - Optional baseline reference line (random-guess marker at 0.5)
//   - Per-point dots colored by threshold (good/poor/neutral)
//   - Recent-N "pills" below the chart showing the last few values as
//     small numeric chips
//
// Domain assumption: values are 0..1 (accuracy / probability /
// confidence). Components needing a different domain should normalize
// before passing in.

export interface SparklineProps {
  values: number[]
  width?: number
  height?: number
  /** Threshold above which a point reads as 'good' (success tone). */
  goodAt?: number
  /** Threshold below which a point reads as 'poor' (warning tone). */
  poorAt?: number
  /** Show the 0.5 baseline (random-guess marker). */
  baseline?: boolean
  ariaLabel?: string
}

export function Sparkline({
  values,
  width = 280,
  height = 28,
  goodAt = 0.85,
  poorAt = 0.75,
  baseline = true,
  ariaLabel,
}: SparklineProps) {
  if (values.length === 0) return null
  const W = width
  const H = height
  const polyline = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * W
      const y = H - clamp01(v) * H
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      style={{ width: '100%', height: H, display: 'block' }}
      aria-label={ariaLabel}
    >
      {baseline && (
        <line
          x1={0}
          x2={W}
          y1={H * 0.5}
          y2={H * 0.5}
          stroke="var(--ace-line-soft)"
          strokeDasharray="2 3"
          strokeWidth={1}
        />
      )}
      <polyline
        points={polyline}
        fill="none"
        stroke="var(--ace-ink)"
        strokeWidth={1.5}
      />
      {values.map((v, i) => {
        const x = (i / Math.max(values.length - 1, 1)) * W
        const y = H - clamp01(v) * H
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={1.6}
            fill={v >= goodAt ? 'var(--ace-success)' : v < poorAt ? 'var(--ace-warning)' : 'var(--ace-ink-muted)'}
          />
        )
      })}
    </svg>
  )
}

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n))
}
