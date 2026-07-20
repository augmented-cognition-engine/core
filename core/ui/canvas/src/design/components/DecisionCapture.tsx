// core/ui/canvas/src/design/components/DecisionCapture.tsx
//
// The Decision-Capture-by-Recognition primitive. From the partnership
// thesis: decisions are captured inline — no form, no separate step.
// Renders the "Decision spotted" + brief description shape from the
// voice style guide.
//
// NEVER `Successfully created`, NEVER a form submission, NEVER an
// "Approve / Reject" dialog. Decisions are recognized by ACE from the
// conversation flow; the user can correct or confirm in-line.
//
// Source variants:
//   - recognized:  ACE noticed it (the common case)
//   - explicit:    user typed it directly (rare, for explicit overrides)
import type { ReactNode } from 'react'

export type DecisionSource = 'recognized' | 'explicit'

export interface DecisionCaptureProps {
  source?: DecisionSource
  /** The decision text — what was decided. */
  decision: ReactNode
  /** Optional provenance: link / id / brief context for traceability. */
  provenance?: ReactNode
  /** Optional action row — typically a single quiet Button to amend or
   *  challenge. */
  children?: ReactNode
  dataTest?: string
}

const SOURCE_LABEL: Record<DecisionSource, string> = {
  recognized: 'Decision spotted',
  explicit: 'Decision recorded',
}

export function DecisionCapture({
  source = 'recognized',
  decision,
  provenance,
  children,
  dataTest,
}: DecisionCaptureProps) {
  return (
    <div
      data-test={dataTest}
      data-decision-source={source}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-1)',
        padding: 'var(--ace-space-3) var(--ace-space-4)',
        background: 'var(--ace-surface-tint)',
        borderRadius: 'var(--ace-radius-md)',
        fontFamily: 'var(--ace-font-sans)',
      }}
    >
      <div
        style={{
          fontSize: 'var(--ace-text-xs)',
          fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          letterSpacing: 'var(--ace-track-widest)',
          textTransform: 'uppercase',
          color: 'var(--ace-accent)',
        }}
      >
        {SOURCE_LABEL[source]}
      </div>
      <div
        style={{
          fontFamily: 'var(--ace-font-serif)',
          fontSize: 'var(--ace-text-md)',
          lineHeight: 'var(--ace-leading-snug)',
          color: 'var(--ace-ink)',
        }}
      >
        {decision}
      </div>
      {provenance !== undefined && (
        <div
          style={{
            fontSize: 'var(--ace-text-xs)',
            color: 'var(--ace-ink-muted)',
            fontStyle: 'italic',
            fontFamily: 'var(--ace-font-serif)',
          }}
        >
          {provenance}
        </div>
      )}
      {children !== undefined && (
        <div style={{ marginTop: 'var(--ace-space-2)', display: 'flex', gap: 'var(--ace-space-2)' }}>
          {children}
        </div>
      )}
    </div>
  )
}
