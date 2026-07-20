// core/ui/canvas/src/design/components/HandOff.tsx
//
// The Hand-Off conversational dispatch primitive. Replaces "Agent run
// launched" / "Task queued" / "Submitted to processor" slop. From the
// partnership thesis: approving a direction in the canvas triggers
// agent runs; ACE commands, agents execute, results return.
//
// Three phases (each with its own voice rule from voice-style-guide.md):
//
//   announce  → first-person action: "I'll send this to claude-code…"
//   running   → gerund plain language: "Running tests…"
//   summary   → observation + offer after completion: "Tests passed.
//               Want me to draft the PR?"
//
// The primitive switches treatment per phase. Surfaces pass `phase` +
// the corresponding message; phase transitions are the surface's
// responsibility (typically driven by run state from the backend).
import type { ReactNode } from 'react'

export type HandOffPhase = 'announce' | 'running' | 'summary'

export interface HandOffProps {
  phase: HandOffPhase
  /** Agent name being dispatched to. Renders as semibold inline. */
  to: string
  /** The message body per the phase's voice rule. */
  message: ReactNode
  /** Summary-phase only: optional offer action row. */
  children?: ReactNode
  dataTest?: string
}

const PHASE_PREFIX: Record<HandOffPhase, string> = {
  announce: 'I’ll send this to',
  running: 'Running through',
  summary: 'Returned from',
}

export function HandOff({ phase, to, message, children, dataTest }: HandOffProps) {
  return (
    <div
      data-test={dataTest}
      data-handoff-phase={phase}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-2)',
        padding: 'var(--ace-space-3) var(--ace-space-4)',
        background: phase === 'running' ? 'var(--ace-surface-recessed)' : 'var(--ace-surface-raised)',
        borderRadius: 'var(--ace-radius-md)',
        boxShadow: phase === 'summary' ? 'var(--ace-shadow-card)' : 'none',
        fontFamily: 'var(--ace-font-sans)',
        fontSize: 'var(--ace-text-md)',
        color: 'var(--ace-ink-soft)',
        transition: 'background var(--ace-motion-flow) var(--ace-ease-organic)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--ace-space-2)' }}>
        <span
          style={{
            color: 'var(--ace-ink-muted)',
            fontSize: 'var(--ace-text-sm)',
            fontStyle: phase === 'running' ? 'italic' : 'normal',
          }}
        >
          {PHASE_PREFIX[phase]}
        </span>
        <span
          style={{
            color: 'var(--ace-accent)',
            fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
            fontFamily: 'var(--ace-font-mono)',
            fontSize: 'var(--ace-text-sm)',
          }}
        >
          {to}
        </span>
        {phase === 'running' && (
          <span
            aria-hidden
            className="ace-presence-dot--pulse"
            style={{
              marginLeft: 'auto',
              width: 6,
              height: 6,
              borderRadius: 'var(--ace-radius-pill)',
              background: 'var(--ace-accent)',
            }}
          />
        )}
      </div>
      <div
        style={{
          fontFamily: phase === 'summary' ? 'var(--ace-font-serif)' : 'var(--ace-font-sans)',
          color: 'var(--ace-ink)',
          lineHeight: 'var(--ace-leading-snug)',
        }}
      >
        {message}
      </div>
      {phase === 'summary' && children !== undefined && (
        <div style={{ display: 'flex', gap: 'var(--ace-space-2)', flexWrap: 'wrap' }}>
          {children}
        </div>
      )}
    </div>
  )
}
