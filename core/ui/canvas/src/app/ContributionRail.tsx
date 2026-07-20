// core/ui/canvas/src/app/ContributionRail.tsx
//
// The team's lane — right side of the workspace. Stacks ContributionCards
// vertically with an eyebrow header at top and idle/placeholder voices
// represented as ghosted lanes so the room is always visible.
//
// This is the spatial counterpart to the partner's center column —
// voices live HERE, not in the main reading column. Collaborative
// environment, not article.
import { ContributionCard, ContributionPlaceholder } from './ContributionCard'
import type { ContributionState, PresenceParticipant } from './state'

interface ContributionRailProps {
  contributions: ContributionState[]
  /** Optional roster — used to render ghosted lanes for voices that
   *  haven't fired yet, so the rail shows the full team even at the
   *  start of a deliberation. */
  roster?: PresenceParticipant[]
}

export function ContributionRail({ contributions, roster }: ContributionRailProps) {
  // Build a lookup of lens-id → contribution; ghosted placeholders fill
  // in for roster members who haven't fired yet.
  const byLens = new Map(contributions.map((c) => [c.lens, c]))
  const rosterVoices = (roster ?? []).filter(
    (p) => p.isUser !== true && p.isPartner !== true,
  )
  return (
    <aside
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-3)',
        minWidth: 0,
      }}
      aria-label="Team contributions"
    >
      <div
        style={{
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-xs)',
          fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          letterSpacing: 'var(--ace-track-widest)',
          textTransform: 'uppercase',
          color: 'var(--ace-ink-muted)',
          marginBottom: 'var(--ace-space-1)',
        }}
      >
        The team · {contributions.filter((c) => c.inFlight !== true).length} of{' '}
        {rosterVoices.length > 0 ? rosterVoices.length : contributions.length} in
      </div>

      {rosterVoices.length > 0
        ? rosterVoices.map((voice) => {
            const c = byLens.get(voice.id)
            if (c !== undefined) {
              return <ContributionCard key={voice.id} contribution={c} />
            }
            return (
              <ContributionPlaceholder
                key={voice.id}
                speaker={voice.name}
                accent={voice.accent}
                hint={voice.lastAt ?? 'not yet'}
              />
            )
          })
        : contributions.map((c) => <ContributionCard key={c.id} contribution={c} />)}
    </aside>
  )
}
