// core/ui/canvas/src/app/Footer.tsx
//
// Persistent "ask the team" input footer — the partnership-thesis
// affordance. Replaces any session-start gate; the user can interject
// at any moment. Per feedback_partner_never_asks, this is *always*
// available, never gated.
import { AskInput } from '../design/components'
import type { FooterState } from './state'

interface FooterProps {
  state: FooterState
}

export function Footer({ state }: FooterProps) {
  return (
    <footer
      style={{
        padding: 'var(--ace-space-3) var(--ace-space-6)',
        borderTop: '1px solid var(--ace-line-soft)',
        background: 'var(--ace-surface-card)',
        flex: '0 0 auto',
      }}
    >
      <AskInput
        label="Ask the team"
        placeholder={state.placeholder}
        onSubmit={state.onAsk}
        dataTest="ace-ask-the-team"
      />
    </footer>
  )
}
