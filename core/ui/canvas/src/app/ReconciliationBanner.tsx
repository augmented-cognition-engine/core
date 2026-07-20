// core/ui/canvas/src/app/ReconciliationBanner.tsx
//
// Top-of-canvas band that overrides normal chrome when a prediction
// window is closing. The +30d mode in multiplayer.html. Names the
// decision being reconciled and surfaces the outcome hint inline so
// the user sees "your call from last month is closing right now"
// without leaving the canvas.
import { Eyebrow } from '../design/components'
import type { ReconciliationBannerState } from './state'

interface ReconciliationBannerProps {
  state: ReconciliationBannerState
}

export function ReconciliationBanner({ state }: ReconciliationBannerProps) {
  if (!state.active) return null

  return (
    <div
      style={{
        padding: 'var(--ace-space-2) var(--ace-space-6)',
        background: 'var(--ace-accent-soft)',
        borderBottom: '1px solid var(--ace-accent)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--ace-space-3)',
        fontFamily: 'var(--ace-font-sans)',
        flex: '0 0 auto',
      }}
      role="status"
      aria-live="polite"
    >
      <Eyebrow tone="var(--ace-accent)">Reconciliation · {state.horizonLabel}</Eyebrow>
      <span
        style={{
          color: 'var(--ace-ink)',
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-md)',
        }}
      >
        {state.decisionTitle}
      </span>
      {state.outcomeHint !== undefined && (
        <span
          style={{
            marginLeft: 'auto',
            color: 'var(--ace-accent)',
            fontSize: 'var(--ace-text-sm)',
            fontFamily: 'var(--ace-font-mono)',
            fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          }}
        >
          {state.outcomeHint}
        </span>
      )}
    </div>
  )
}
