// core/ui/canvas/src/app/WorkingPanel.tsx
//
// The right rail from multiplayer.html. Shows the partner's background
// activity — who's working on what right now (agents in flight) and
// what's been written to memory this turn (capture summary).
//
// Two cards stacked:
//   1. Agents in flight — discipline avatar + lens + italic activity line
//   2. Captured this turn — three counters (decisions, perspectives,
//      contributions)
//
// Reads from state.workingPanel. Every value flows in as data.
import {
  AgentPresenceRow,
  Avatar,
  Card,
  Eyebrow,
  Tooltip,
} from '../design/components'
import { disciplineIdentity } from '../design/disciplineIdentity'
import type { WorkingPanelState } from './state'

interface WorkingPanelProps {
  state: WorkingPanelState
}

export function WorkingPanel({ state }: WorkingPanelProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-4)' }}>
      <AgentsInFlight agents={state.agentsInFlight} />
      {state.capturedThisTurn !== undefined && (
        <CapturedThisTurn summary={state.capturedThisTurn} />
      )}
    </div>
  )
}

function AgentsInFlight({
  agents,
}: {
  agents: WorkingPanelState['agentsInFlight']
}) {
  return (
    <Card variant="default" padding="md">
      <Eyebrow>Agents in flight</Eyebrow>
      {agents.length === 0 ? (
        <div
          style={{
            marginTop: 'var(--ace-space-2)',
            fontSize: 'var(--ace-text-sm)',
            color: 'var(--ace-ink-muted)',
            fontStyle: 'italic',
            fontFamily: 'var(--ace-font-serif)',
          }}
        >
          The team is quiet right now.
        </div>
      ) : (
        <div
          style={{
            marginTop: 'var(--ace-space-3)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--ace-space-3)',
          }}
        >
          {agents.map((agent, i) => (
            <CursorCard key={`${agent.lens}-${i}`} lens={agent.lens} activity={agent.activity} />
          ))}
        </div>
      )}
    </Card>
  )
}

function CursorCard({ lens, activity }: { lens: string; activity: string }) {
  const id = disciplineIdentity(lens)
  return (
    <Tooltip content={`${id.role} — ${activity}`}>
      <div>
        <AgentPresenceRow
          lens={lens}
          accent={id.color}
          activity={activity}
          avatar={<Avatar lens={lens} size="sm" />}
        />
      </div>
    </Tooltip>
  )
}

function CapturedThisTurn({
  summary,
}: {
  summary: NonNullable<WorkingPanelState['capturedThisTurn']>
}) {
  const items: Array<{ count: number; label: string }> = [
    { count: summary.decisions, label: summary.decisions === 1 ? 'decision' : 'decisions' },
    { count: summary.perspectives, label: summary.perspectives === 1 ? 'perspective' : 'perspectives' },
    { count: summary.contributions, label: summary.contributions === 1 ? 'contribution' : 'contributions' },
  ]
  return (
    <Card variant="strong" padding="md">
      <Eyebrow>Captured this turn</Eyebrow>
      <div
        style={{
          marginTop: 'var(--ace-space-3)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--ace-space-2)',
        }}
      >
        {items.map((item) => (
          <div
            key={item.label}
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 'var(--ace-space-2)',
              fontSize: 'var(--ace-text-md)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--ace-font-mono)',
                fontVariantNumeric: 'tabular-nums',
                fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
                color: item.count > 0 ? 'var(--ace-ink)' : 'var(--ace-ink-muted)',
                minWidth: 24,
                textAlign: 'right',
              }}
            >
              {item.count}
            </span>
            <span
              style={{
                color: item.count > 0 ? 'var(--ace-ink-soft)' : 'var(--ace-ink-muted)',
                fontFamily: 'var(--ace-font-serif)',
                fontStyle: item.count === 0 ? 'italic' : 'normal',
              }}
            >
              {item.label}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}
