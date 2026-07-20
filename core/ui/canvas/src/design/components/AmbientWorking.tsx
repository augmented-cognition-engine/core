// core/ui/canvas/src/design/components/AmbientWorking.tsx
//
// The Ambient Working Indicator. Replaces every "Loading..." /
// "Processing..." / "Thinking..." string forbidden by the voice style
// guide. Presence, not summoning.
//
// Visual treatment: a discreet breathing dot + optional italic-serif
// activity line. Lives inline in context, NOT as a modal spinner. The
// dot pulses on the pulse motion token (2400ms ambient breathing
// cadence) so it reads as background ambient activity, not foreground
// blocking work.
//
// Surfaces with no specific activity to name can pass nothing — the
// dot alone communicates presence. Surfaces with context pass a lens
// (to colorize) and activity (to name what's happening).
export interface AmbientWorkingProps {
  /** Optional lens (discipline). Colors the dot. Defaults to accent. */
  accent?: string
  /** Optional italic-serif activity line. ("reading the spec", "writing
   *  up the brief"). When omitted, only the dot renders. */
  activity?: string
  /** Visual size. `inline` = 4px dot, `default` = 6px, `prominent` = 8px. */
  size?: 'inline' | 'default' | 'prominent'
  dataTest?: string
}

const DOT_SIZE: Record<NonNullable<AmbientWorkingProps['size']>, number> = {
  inline: 4,
  default: 6,
  prominent: 8,
}

export function AmbientWorking({
  accent,
  activity,
  size = 'default',
  dataTest,
}: AmbientWorkingProps) {
  const color = accent ?? 'var(--ace-accent)'
  const dot = DOT_SIZE[size]
  return (
    <div
      data-test={dataTest}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--ace-space-2)',
        fontFamily: 'var(--ace-font-serif)',
        fontSize: 'var(--ace-text-sm)',
        color: 'var(--ace-ink-muted)',
        fontStyle: 'italic',
      }}
    >
      <span
        aria-hidden
        className="ace-presence-dot--pulse"
        style={{
          width: dot,
          height: dot,
          borderRadius: 'var(--ace-radius-pill)',
          background: color,
          flex: '0 0 auto',
        }}
      />
      {activity !== undefined && <span>{activity}</span>}
    </div>
  )
}
