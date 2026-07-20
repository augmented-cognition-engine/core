// core/ui/canvas/src/app/ClosingAsk.tsx
//
// The partner reflects back — names what it's most uncertain about
// and invites the user to engage with that gap. Editorial reflection
// + the persistent ask-input pattern.
//
// Partnership thesis note: the partner asking *back* (reflectively,
// inviting continued dialogue) is fine. What we forbid is the partner
// asking the user to *initiate* (session-start gates). Closing-asks
// land AT THE END of a turn, after convergence; they extend the
// conversation rather than gate it.
import { AskInput, Aphorism, Button, Card, Eyebrow } from '../design/components'
import { disciplineIdentity } from '../design/disciplineIdentity'
import type { ClosingAskState } from './state'

interface ClosingAskProps {
  state: ClosingAskState
}

export function ClosingAsk({ state }: ClosingAskProps) {
  const accent =
    state.uncertainLens !== undefined
      ? disciplineIdentity(state.uncertainLens).color
      : 'var(--ace-warning)'

  return (
    <div style={{ marginTop: 'var(--ace-space-6)' }}>
      <Card variant="default" padding="lg" accent={accent}>
        <Eyebrow>The partner reflects back</Eyebrow>

        <div style={{ marginTop: 'var(--ace-space-2)' }}>
          <Aphorism>{state.reflection}</Aphorism>
        </div>

        <div
          style={{
            marginTop: 'var(--ace-space-4)',
            paddingTop: 'var(--ace-space-3)',
            borderTop: '1px solid var(--ace-line-soft)',
          }}
        >
          <AskInput
            label="Tell the partner"
            placeholder="…what to watch, push back on, or commit to next"
            onSubmit={state.onTell}
            dataTest="ace-closing-ask"
          />
        </div>

        {state.quickActions !== undefined && state.quickActions.length > 0 && (
          <div
            style={{
              marginTop: 'var(--ace-space-3)',
              display: 'flex',
              gap: 'var(--ace-space-2)',
              flexWrap: 'wrap',
            }}
          >
            {state.quickActions.map((action) => (
              <Button
                key={action.id}
                variant="secondary"
                size="sm"
                onClick={action.onClick}
              >
                {action.label}
              </Button>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
