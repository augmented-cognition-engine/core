// core/ui/canvas/src/app/ConvergenceBeat.tsx
//
// What lands when the committee converges — rendered as a single
// synthesized note, not a 3-cell grid of artifact cards.
//
// Reads as the synthesizer's voice writing the call: a pull-quote
// verdict in serif display, then a tight paragraph of body context,
// then a one-line falsifiability anchor ("Reverse if …") set in
// mono-eyebrow language. No "Decision · Prediction · Capture"
// chrome — those concepts live in the words.
//
// The capture and prediction details surface inline in the body and
// in a thin tabular footer (small caps + monospace numbers) — the
// way you'd see them in a designer's working file, not a SaaS
// dashboard.
import type { ConvergenceBeatState } from './state'

interface ConvergenceBeatProps {
  state: ConvergenceBeatState
}

export function ConvergenceBeat({ state }: ConvergenceBeatProps) {
  if (!state.converged) return null
  const { decision, prediction, capture } = state
  return (
    <div
      className="ace-converge-reveal"
      style={{
        marginTop: 'var(--ace-space-8)',
        paddingTop: 'var(--ace-space-6)',
        borderTop: '1px solid var(--ace-line)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-4)',
        maxWidth: '72ch',
      }}
    >
      {/* Editorial eyebrow — small caps, names the moment without
          inventing a "Decision" header. */}
      <div
        style={{
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-xs)',
          fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          letterSpacing: 'var(--ace-track-widest)',
          textTransform: 'uppercase',
          color: 'var(--ace-ink-muted)',
        }}
      >
        Where the team landed
        <span
          style={{
            marginLeft: 'var(--ace-space-2)',
            color: 'var(--ace-ink-faint)',
            letterSpacing: 'var(--ace-track-normal)',
            textTransform: 'none',
            fontWeight: 'var(--ace-weight-regular)' as unknown as number,
            fontFamily: 'var(--ace-font-mono)',
            fontSize: 'var(--ace-text-xs)',
          }}
        >
          · synthesized {decision.synthesizedAt ?? 'just now'}
        </span>
      </div>

      {/* The call — pull-quote in serif display. The single
          load-bearing line of the readout. */}
      <p
        style={{
          margin: 0,
          fontFamily: 'var(--ace-font-serif)',
          fontSize: 'var(--ace-text-2xl)',
          lineHeight: 1.3,
          letterSpacing: '-0.012em',
          color: 'var(--ace-ink)',
        }}
      >
        {decision.verdict}
      </p>

      {/* Prediction context, inline body. Reads as the synthesizer
          explaining what they expect to happen. */}
      <p
        style={{
          margin: 0,
          fontFamily: 'var(--ace-font-serif)',
          fontSize: 'var(--ace-text-prose)',
          lineHeight: 'var(--ace-leading-prose)',
          color: 'var(--ace-ink-soft)',
          letterSpacing: '-0.005em',
        }}
      >
        {prediction.forecast} The window closes in{' '}
        <span style={{ color: 'var(--ace-ink)' }}>{prediction.horizonDays} days</span>.
      </p>

      {/* Reverse-if — the falsifiability anchor. Mono prefix, serif
          consequence — the only place the workshop voice gets
          adversarial. */}
      {decision.reverseIf !== undefined && (
        <p
          style={{
            margin: 0,
            fontFamily: 'var(--ace-font-serif)',
            fontSize: 'var(--ace-text-lg)',
            lineHeight: 1.5,
            color: 'var(--ace-ink-soft)',
            fontStyle: 'italic',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--ace-font-mono)',
              fontStyle: 'normal',
              fontSize: 'var(--ace-text-xs)',
              fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
              letterSpacing: 'var(--ace-track-wide)',
              textTransform: 'uppercase',
              color: 'var(--ace-ink-muted)',
              marginRight: 'var(--ace-space-2)',
            }}
          >
            Reverse if
          </span>
          {decision.reverseIf}
        </p>
      )}

      {/* Capture footer — tabular note, designer's-working-file
          style. Tiny mono numbers + small-caps labels. No card
          wrapper. */}
      <div
        style={{
          marginTop: 'var(--ace-space-3)',
          paddingTop: 'var(--ace-space-3)',
          borderTop: '1px dashed var(--ace-line)',
          display: 'flex',
          gap: 'var(--ace-space-6)',
          fontFamily: 'var(--ace-font-mono)',
          fontSize: 'var(--ace-text-xs)',
          color: 'var(--ace-ink-muted)',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        <CapturePair n={capture.decisions} label="decisions" />
        <CapturePair n={capture.perspectives} label="voices" />
        <CapturePair n={capture.contributions} label="contributions" />
        {capture.specId !== undefined && (
          <span
            style={{
              marginLeft: 'auto',
              color: 'var(--ace-ink-faint)',
              letterSpacing: 'var(--ace-track-tight)',
            }}
          >
            {capture.specId}
          </span>
        )}
      </div>
    </div>
  )
}

function CapturePair({ n, label }: { n: number; label: string }) {
  return (
    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'baseline' }}>
      <span
        style={{
          color: 'var(--ace-ink)',
          fontWeight: 'var(--ace-weight-medium)' as unknown as number,
        }}
      >
        {n}
      </span>
      <span style={{ letterSpacing: 'var(--ace-track-tight)' }}>{label}</span>
    </span>
  )
}
