// core/ui/canvas/src/design/components/AgentPresenceRow.tsx
//
// A single agent's in-flight presence — names the "voice-in-motion"
// semantic from the partnership UI vocabulary. Replaces the inline
// CursorCard pattern in WorkingPanel.tsx (`<div style={{ borderLeft:
// 2px ${id.color}, background: color-mix(...) }}>`).
//
// The row reads as "this agent is at work right now": discipline
// avatar + lens label + italic activity line. Lane uses a 2px solid
// accent border + 6% tinted background — the system signature for
// "partner is moving in this lane."
import type { ReactNode } from 'react'

export type AgentPresenceTone = 'active' | 'dim'

export interface AgentPresenceRowProps {
  /** Lens (discipline) identifier. Used to look up the accent color. */
  lens: string
  /** Color associated with this lens (from disciplineIdentity). */
  accent: string
  /** Optional avatar/glyph slot — typically `<Avatar lens={lens} size="sm" />`. */
  avatar?: ReactNode
  /** Italic-serif activity line: "reading the spec", "running the matrix". */
  activity: string
  /** Optional override of the lens label. Default = formatted lens name. */
  label?: string
  tone?: AgentPresenceTone
  dataTest?: string
}

function formatLens(lens: string): string {
  return lens.replace(/_/g, ' ')
}

export function AgentPresenceRow({
  lens,
  accent,
  avatar,
  activity,
  label,
  tone = 'active',
  dataTest,
}: AgentPresenceRowProps) {
  return (
    <div
      data-test={dataTest}
      data-presence-tone={tone}
      style={{
        display: 'flex',
        gap: 'var(--ace-space-2)',
        alignItems: 'flex-start',
        padding: 'var(--ace-space-2)',
        borderLeft: `2px solid ${accent}`,
        background: `color-mix(in oklab, ${accent} 6%, transparent)`,
        borderRadius: 'var(--ace-radius-sm)',
        opacity: tone === 'dim' ? 0.7 : 1,
        cursor: 'default',
        transition: 'opacity var(--ace-motion-lift) var(--ace-ease-out)',
      }}
    >
      {avatar !== undefined && (
        <div style={{ flex: '0 0 auto' }}>{avatar}</div>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 'var(--ace-text-sm)',
            fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
            color: accent,
            letterSpacing: 'var(--ace-track-normal)',
            textTransform: 'capitalize',
          }}
        >
          {label ?? formatLens(lens)}
        </div>
        <div
          style={{
            fontSize: 'var(--ace-text-sm)',
            color: 'var(--ace-ink-soft)',
            fontStyle: 'italic',
            fontFamily: 'var(--ace-font-serif)',
            lineHeight: 'var(--ace-leading-snug)',
            marginTop: 2,
          }}
        >
          {activity}
        </div>
      </div>
    </div>
  )
}
