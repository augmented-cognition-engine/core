// core/ui/canvas/src/app/ContributionBody.tsx
//
// One lens's contribution to a deliberation. Lives inside a CogSection
// as its body. Lean — italic-serif framing + optional confidence pip +
// optional in-flight indicator + byline.
//
// Editorial-density text on a paper card surface; the byline anchors
// who is speaking.
import { Byline } from '../design/components'

interface ContributionBodyProps {
  /** The lens's framing of the problem, in their voice. Italic-serif. */
  framing: string
  /** 0..1 confidence. Renders as a small pip + numeric badge. */
  confidence?: number
  /** Who's speaking — shown as a small byline below the framing. */
  byline?: string
  /** Whether this contribution is actively forming (vs. landed) — drives
   *  the muted "in flight" cue. */
  inFlight?: boolean
}

export function ContributionBody({
  framing,
  confidence,
  byline,
  inFlight,
}: ContributionBodyProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-2)',
      }}
    >
      <p
        style={{
          margin: 0,
          fontFamily: 'var(--ace-font-serif)',
          fontStyle: 'italic',
          fontSize: 'var(--ace-text-md)',
          lineHeight: 'var(--ace-leading-normal)',
          color: 'var(--ace-ink)',
        }}
      >
        “{framing}”
      </p>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--ace-space-2)',
          marginTop: 'var(--ace-space-1)',
        }}
      >
        {byline !== undefined && <Byline size="sm">— {byline}</Byline>}
        {confidence !== undefined && (
          <ConfidencePip value={confidence} />
        )}
        {inFlight === true && <InFlightCue />}
      </div>
    </div>
  )
}

function ConfidencePip({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const tone =
    value >= 0.8
      ? 'var(--ace-success)'
      : value >= 0.6
        ? 'var(--ace-tone-medium)'
        : 'var(--ace-warning)'
  return (
    <span
      title={`Confidence ${pct}%`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 'var(--ace-text-xs)',
        fontFamily: 'var(--ace-font-mono)',
        fontVariantNumeric: 'tabular-nums',
        color: tone,
        background: `color-mix(in oklab, ${tone} 10%, transparent)`,
        border: `1px solid color-mix(in oklab, ${tone} 30%, transparent)`,
        borderRadius: 'var(--ace-radius-sm)',
        padding: '1px 6px',
      }}
    >
      <span
        aria-hidden
        style={{ width: 6, height: 6, borderRadius: '50%', background: tone }}
      />
      conf · {value.toFixed(2)}
    </span>
  )
}

function InFlightCue() {
  return (
    <>
      <style>{`
        @keyframes ace-inflight-pulse {
          0%, 100% { opacity: 0.55; }
          50% { opacity: 1; }
        }
      `}</style>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          fontSize: 'var(--ace-text-xs)',
          fontFamily: 'var(--ace-font-sans)',
          color: 'var(--ace-voice-accent)',
          fontStyle: 'italic',
          animation: 'ace-inflight-pulse 1.8s ease-in-out infinite',
        }}
      >
        <span aria-hidden>·</span>
        thinking…
      </span>
    </>
  )
}
