// core/ui/canvas/src/design/viz/RampBars.tsx
//
// A directional ramp: DIRECTION LIVES IN THE GEOMETRY, not in a label.
//
// The bars hang DOWN from a top rule for a negative push and grow UP from a bottom rule
// for a positive one. You read the sign before you read anything else, which is the point
// — a row of bars with a minus sign beside it makes you parse; a row of bars hanging
// downward makes you *see*. Colour then agrees with the geometry rather than carrying it
// alone, so the reading survives a glance, a colour-blind eye, and a bad monitor.
//
// A null direction is a real state, not a missing value: the force exists and is asleep.
// It renders as a flat dim rule — visibly present, visibly doing nothing — because
// hiding it would say "no such force", which is a different and false claim.
//
// GENERIC BY CONSTRUCTION. The kernel does not know what "into the close" means. This is a
// signed sequence of magnitudes; the caller supplies the words. (A consuming extension
// might compose it as a decay ramp toward a session close.)

import { type Rgb, hues, rgb } from './chartTokens'

export interface RampBarsProps {
  /** Bar heights in px, in order. Empty → the flat/asleep rule. */
  heights: number[]
  /** Which way the ramp points. `null` = the force is present but asleep. */
  direction: 'up' | 'down' | null
  /** Trailing caption (e.g. a total, or where the ramp is heading). */
  caption?: string
  title?: string
  /** Width of each bar in px. */
  barWidth?: number
}

const UP: Rgb = hues.up
const DOWN: Rgb = hues.down

export function RampBars({
  heights,
  direction,
  caption,
  title,
  barWidth = 8,
}: RampBarsProps) {
  const asleep = direction === null || heights.length === 0
  const down = direction === 'down'
  const color = asleep ? 'var(--ace-ink-faint)' : rgb(down ? DOWN : UP)

  return (
    <span
      title={title}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', minWidth: 0 }}
    >
      <span
        style={{
          display: 'inline-flex',
          gap: '1px',
          height: '16px',
          // The rule the bars hang from / stand on. Direction is structural, so the
          // border moves rather than the colour changing.
          //
          // LONGHAND, deliberately: `border-top: 1px solid var(--ace-line)` round-trips
          // as `var(--ace-line) var(--ace-line) var(--ace-line)` through a CSSOM that
          // cannot resolve a custom property inside a shorthand — the width and style
          // silently become the colour, and the rule vanishes. Longhands cannot be
          // misparsed that way.
          alignItems: down ? 'flex-start' : 'flex-end',
          [down ? 'borderTopWidth' : 'borderBottomWidth']: '1px',
          [down ? 'borderTopStyle' : 'borderBottomStyle']: 'solid',
          [down ? 'borderTopColor' : 'borderBottomColor']: 'var(--ace-line)',
          opacity: asleep ? 0.4 : 1,
        }}
      >
        {(asleep ? [2, 2, 2, 2] : heights).map((h, i) => (
          <span
            key={i}
            style={{
              width: `${barWidth}px`,
              height: `${asleep ? 2 : h}px`,
              background: color,
              // Later bars are the ones further into the future: they read louder.
              opacity: asleep ? 1 : 0.45 + i * 0.18,
            }}
          />
        ))}
      </span>
      {caption && (
        <span
          style={{
            fontSize: '9px',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--ace-ink-faint)',
            fontFamily: 'var(--ace-font-mono)',
            whiteSpace: 'nowrap',
          }}
        >
          {caption}
        </span>
      )}
    </span>
  )
}
