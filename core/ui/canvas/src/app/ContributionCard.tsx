// core/ui/canvas/src/app/ContributionCard.tsx
//
// One voice's contribution as a pinned note in the team's rail.
// Composes the design-system ContributionLane primitive — the lane
// owns the visual shape (border-accent, byline, in-flight thinking
// indicator); this surface wires up state mapping and the live caret.
//
// State mapping from ContributionState:
//   - in-flight       → ContributionLane state="in-flight" + live caret
//   - landedAt set    → state="active" (or "idle" downstream if visually
//                       dimmer treatment is needed)
//   - placeholder     → ContributionPlaceholder below (state="placeholder")
import { ContributionLane } from '../design/components'
import type { ContributionState } from './state'

interface ContributionCardProps {
  contribution: ContributionState
}

export function ContributionCard({ contribution: c }: ContributionCardProps) {
  const state = c.inFlight === true ? 'in-flight' : 'active'
  return (
    <ContributionLane
      voice={{ speaker: c.speaker, accent: c.accent }}
      state={state}
      landedAt={c.landedAt}
      thinkingAbout={c.thinkingAbout}
    >
      {c.framing}
      {c.inFlight === true && (
        <span
          aria-hidden
          className="ace-caret"
          style={{
            display: 'inline-block',
            width: 2,
            height: '1.05em',
            background: c.accent,
            marginLeft: 2,
            verticalAlign: 'text-bottom',
            transform: 'translateY(2px)',
          }}
        />
      )}
    </ContributionLane>
  )
}

/** Placeholder card for a voice that hasn't fired yet. Renders ghosted
 *  in the rail so the lane is visible — the user can see WHO is
 *  expected to speak next without imagining absent voices. */
export function ContributionPlaceholder({
  speaker,
  accent,
  hint,
}: {
  speaker: string
  accent: string
  hint?: string
}) {
  return (
    <ContributionLane voice={{ speaker, accent }} state="placeholder">
      <span
        style={{
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-xs)',
          color: 'var(--ace-ink-muted)',
          fontStyle: 'italic',
        }}
      >
        {hint ?? 'not yet'}
      </span>
    </ContributionLane>
  )
}
