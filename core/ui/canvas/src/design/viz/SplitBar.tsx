// core/ui/canvas/src/design/viz/SplitBar.tsx
//
// A two-sided signed proportion bar: THE SPLIT POSITION IS THE RATIO.
//
// There is no middle seam and that is the whole idea. A bar with a fixed centre and two
// growing halves says "here is a deviation from balance". This says "here is where the
// balance actually sits" — 50/50 is not a neutral default it returns to, it is a reading,
// and a meaningful one (two sides of equal size pushing against each other is a locked
// book, not an absent one).
//
// Each segment is coloured by the SIGN of its own side, not by which side it is on. Two
// same-signed sides therefore render the same colour, and the second takes a brightness
// step so the split stays legible when the colour cannot carry it.
//
// GENERIC BY CONSTRUCTION. The kernel does not know what a "greek" is, and must not: this
// is a signed two-sided proportion, and the caller supplies the words. (A consuming
// extension composes it into signed two-sided rows and a two-branch split — the
// same primitive twice, which is why it is one component and not two.)

import { type Rgb, hues, rgba } from './chartTokens'

export interface SplitBarProps {
  /** Left segment's share, 0..100. The split position IS the ratio. */
  leftPct: number
  /** Sign of the LEFT side's quantity. */
  leftPositive: boolean
  /** Sign of the RIGHT side's quantity. */
  rightPositive: boolean
  /** Both sides share a sign → step the right one's brightness so the split stays visible. */
  sameSign?: boolean
  /** Tick text under each end. Absent → no tick row. */
  leftLabel?: string
  rightLabel?: string
  /** Native hover text (the caller owns the full explanation). */
  title?: string
  /** Bar height in px. */
  height?: number
}

const POS: Rgb = hues.up
const NEG: Rgb = hues.down

/** Same-sign sides are still two sides. Dim the second rather than merge them. */
const FULL = 1
const STEPPED = 0.5

export function SplitBar({
  leftPct,
  leftPositive,
  rightPositive,
  sameSign = false,
  leftLabel,
  rightLabel,
  title,
  height = 10,
}: SplitBarProps) {
  const left = Math.max(0, Math.min(100, leftPct))
  const fill = (positive: boolean, stepped: boolean) =>
    rgba(positive ? POS : NEG, stepped ? STEPPED : FULL)

  const tick: React.CSSProperties = {
    fontSize: '8px',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    lineHeight: 1.2,
    color: 'var(--ace-ink-faint)',
    fontFamily: 'var(--ace-font-mono)',
  }

  return (
    <span
      title={title}
      style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}
    >
      <span
        style={{
          display: 'flex',
          height: `${height}px`,
          borderRadius: 'var(--ace-radius-sm)',
          overflow: 'hidden',
          gap: '1px',
          background: 'var(--ace-surface-recessed)',
        }}
      >
        <span style={{ width: `${left}%`, background: fill(leftPositive, false) }} />
        <span style={{ width: `${100 - left}%`, background: fill(rightPositive, sameSign) }} />
      </span>
      {(leftLabel || rightLabel) && (
        <span style={{ display: 'flex', justifyContent: 'space-between', gap: '4px' }}>
          <span style={tick}>{leftLabel ?? ''}</span>
          <span style={{ ...tick, textAlign: 'right' }}>{rightLabel ?? ''}</span>
        </span>
      )}
    </span>
  )
}
