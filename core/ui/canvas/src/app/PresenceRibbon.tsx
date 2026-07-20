// core/ui/canvas/src/app/PresenceRibbon.tsx
//
// Multiplayer presence at the top of the readout. Five lens voices + the
// partner + the user, always shown — even at idle. The partner-never-asks
// thesis as visual fact: the room is never empty.
//
// Each avatar carries a status (active / just-spoke / idle / listening)
// that drives a small overlay dot. The partner gets a separate status
// pill ("Partner warm" / "Partner thinking" / "Partner synthesizing")
// inline with the row.
//
// Avatars stack with -8px overlap (designer-working-file convention,
// not SaaS-progress-strip). Tooltip on hover surfaces what they did
// most recently or what they're doing right now.
import { Tooltip } from '../design/components'
import type { PresenceParticipant, PresenceState } from './state'

interface PresenceRibbonProps {
  state: PresenceState
}

export function PresenceRibbon({ state }: PresenceRibbonProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--ace-space-4)',
        padding: 'var(--ace-space-2) 0',
      }}
    >
      <AvatarStack participants={state.participants} />
      <PartnerStatusPill
        status={state.partnerStatus}
        activity={state.partnerActivity}
      />
    </div>
  )
}

function AvatarStack({ participants }: { participants: PresenceParticipant[] }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        position: 'relative',
      }}
    >
      {participants.map((p, i) => (
        <Tooltip
          key={p.id}
          content={
            <span style={{ fontFamily: 'var(--ace-font-sans)', fontSize: 'var(--ace-text-sm)' }}>
              <b>{p.name}</b>
              {p.status === 'active' && p.activity !== undefined && (
                <> · {p.activity}</>
              )}
              {p.status === 'just-spoke' && p.lastAt !== undefined && (
                <> · spoke {p.lastAt}</>
              )}
              {p.status === 'idle' && p.lastAt !== undefined && (
                <> · last {p.lastAt}</>
              )}
              {p.status === 'listening' && <> · listening</>}
            </span>
          }
        >
          <span
            style={{
              marginLeft: i === 0 ? 0 : -8,
              zIndex: participants.length - i,
              display: 'inline-flex',
              cursor: 'default',
            }}
          >
            <Avatar participant={p} />
          </span>
        </Tooltip>
      ))}
    </div>
  )
}

function Avatar({ participant: p }: { participant: PresenceParticipant }) {
  const ringWidth = p.status === 'active' ? 2 : 1
  const ringOpacity = p.status === 'idle' ? 0.45 : 1
  const dotColor =
    p.status === 'active'
      ? p.accent
      : p.status === 'just-spoke'
        ? p.accent
        : p.status === 'listening'
          ? 'var(--ace-ink-muted)'
          : 'transparent'
  return (
    <span
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 28,
        height: 28,
        borderRadius: '50%',
        background: 'var(--ace-surface-raised)',
        color: p.accent,
        fontFamily: 'var(--ace-font-sans)',
        fontSize: 'var(--ace-text-sm)',
        fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
        boxShadow: `0 0 0 ${ringWidth}px ${p.accent}, 0 0 0 ${ringWidth + 2}px var(--ace-surface-canvas)`,
        opacity: ringOpacity,
        transition: 'opacity var(--ace-motion-flow) var(--ace-ease-organic), box-shadow var(--ace-motion-flow) var(--ace-ease-organic)',
      }}
    >
      {p.initial}
      {p.status !== 'idle' && (
        <span
          aria-hidden
          className={p.status === 'active' ? 'ace-presence-dot--pulse' : undefined}
          style={{
            position: 'absolute',
            bottom: -1,
            right: -1,
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: dotColor,
            boxShadow: '0 0 0 2px var(--ace-surface-canvas)',
          }}
        />
      )}
    </span>
  )
}

function PartnerStatusPill({
  status,
  activity,
}: {
  status: PresenceState['partnerStatus']
  activity?: string
}) {
  const label =
    status === 'warm'
      ? 'Partner warm'
      : status === 'listening'
        ? 'Partner listening'
        : status === 'thinking'
          ? 'Partner thinking'
          : 'Partner synthesizing'
  const isLive = status !== 'warm'
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--ace-space-2)',
        padding: '4px 10px 4px 8px',
        borderRadius: 'var(--ace-radius-pill)',
        background: isLive ? 'var(--ace-accent-soft)' : 'var(--ace-surface-recessed)',
        color: isLive ? 'var(--ace-accent)' : 'var(--ace-ink-muted)',
        fontFamily: 'var(--ace-font-sans)',
        fontSize: 'var(--ace-text-sm)',
        fontWeight: 'var(--ace-weight-medium)' as unknown as number,
        letterSpacing: 'var(--ace-track-tight)',
        transition: 'background var(--ace-motion-flow) var(--ace-ease-organic), color var(--ace-motion-flow) var(--ace-ease-organic)',
      }}
    >
      <span
        aria-hidden
        className={isLive ? 'ace-presence-dot--pulse' : undefined}
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: isLive ? 'var(--ace-accent)' : 'var(--ace-ink-faint)',
        }}
      />
      {label}
      {activity !== undefined && (
        <span
          style={{
            color: 'var(--ace-ink-muted)',
            fontWeight: 'var(--ace-weight-regular)' as unknown as number,
          }}
        >
          · {activity}
        </span>
      )}
    </span>
  )
}
