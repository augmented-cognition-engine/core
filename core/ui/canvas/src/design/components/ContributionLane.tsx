// core/ui/canvas/src/design/components/ContributionLane.tsx
//
// A voice's contribution as a pinned note in the team's rail. Names
// the "voice-in-rail" semantic — one of the five distinct meanings of
// left-edge accent in the partnership UI vocabulary.
//
// Replaces the inline `<div style={{ borderLeft: 2px ${voice.accent} }}>`
// pattern in ContributionCard.tsx (active state) and
// ContributionPlaceholder (placeholder state). The lane itself encodes
// "this voice has a lane in the multiplayer rail"; the state encodes
// where the voice is in its contribution cycle.
//
// State semantics:
//   - active:      voice is the lead speaker right now; solid 2px accent
//   - idle:        voice spoke earlier this turn; same shape, 95% opacity
//   - placeholder: voice not yet fired; dashed 2px accent, 55% opacity,
//                  ghosted placeholder text in body
//   - in-flight:   voice composing right now; raised shadow + caret in
//                  body (caret managed by consumer in the children slot)
import type { ReactNode } from 'react'

export type ContributionLaneState =
  | 'active'      // voice is the lead speaker right now
  | 'idle'        // voice spoke earlier in the turn
  | 'placeholder' // voice not yet fired (ghosted lane marker)
  | 'in-flight'   // voice composing now (raised shadow + caret)

export interface ContributionLaneVoice {
  /** Display name shown in the byline. */
  speaker: string
  /** Voice accent color (from disciplineIdentity). Used for the left
   *  edge marker, speaker label, and any inline accents the body
   *  passes through. */
  accent: string
  /** Optional small glyph mark beside the speaker name. */
  glyph?: string
}

export interface ContributionLaneProps {
  voice: ContributionLaneVoice
  state: ContributionLaneState
  /** Optional landed-at marker rendered in the byline. */
  landedAt?: string
  /** Optional "considering ..." note shown only in `in-flight` state. */
  thinkingAbout?: string
  /** Body content — the contribution itself, or a placeholder hint when
   *  `state === 'placeholder'`. */
  children: ReactNode
  dataTest?: string
}

export function ContributionLane({
  voice,
  state,
  landedAt,
  thinkingAbout,
  children,
  dataTest,
}: ContributionLaneProps) {
  const isPlaceholder = state === 'placeholder'
  const isInFlight = state === 'in-flight'
  const isIdle = state === 'idle'
  return (
    <div
      data-test={dataTest}
      data-lane-state={state}
      style={{
        position: 'relative',
        background: isPlaceholder ? 'var(--ace-surface-canvas)' : 'var(--ace-surface-raised)',
        borderRadius: 'var(--ace-radius-lg)',
        boxShadow: isInFlight ? 'var(--ace-shadow-card-hover)' : 'var(--ace-shadow-card)',
        padding: 'var(--ace-space-3) var(--ace-space-4)',
        borderLeft: `2px ${isPlaceholder ? 'dashed' : 'solid'} ${voice.accent}`,
        opacity: isPlaceholder ? 0.55 : isIdle ? 0.95 : 1,
        transition:
          'box-shadow var(--ace-motion-lift) var(--ace-ease-out), opacity var(--ace-motion-flow) var(--ace-ease-organic)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--ace-space-2)',
          marginBottom: 'var(--ace-space-2)',
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-sm)',
        }}
      >
        {voice.glyph !== undefined && (
          <span aria-hidden style={{ color: voice.accent, fontSize: 'var(--ace-text-md)' }}>
            {voice.glyph}
          </span>
        )}
        <span
          style={{
            color: voice.accent,
            fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
            letterSpacing: 'var(--ace-track-tight)',
          }}
        >
          {voice.speaker}
        </span>
        {landedAt !== undefined && !isInFlight && (
          <span
            style={{
              marginLeft: 'auto',
              color: 'var(--ace-ink-muted)',
              fontSize: 'var(--ace-text-xs)',
              fontFamily: 'var(--ace-font-mono)',
            }}
          >
            {landedAt}
          </span>
        )}
        {isInFlight && (
          <span
            className="ace-presence-dot--pulse"
            style={{
              marginLeft: 'auto',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              color: 'var(--ace-ink-muted)',
              fontSize: 'var(--ace-text-xs)',
            }}
          >
            <span
              aria-hidden
              style={{
                width: 6,
                height: 6,
                borderRadius: 'var(--ace-radius-pill)',
                background: voice.accent,
              }}
            />
            thinking
          </span>
        )}
      </div>
      <div
        style={{
          margin: 0,
          fontFamily: 'var(--ace-font-serif)',
          fontSize: 'var(--ace-text-md)',
          lineHeight: 'var(--ace-leading-snug)',
          color: 'var(--ace-ink)',
          letterSpacing: '-0.003em',
        }}
      >
        {children}
      </div>
      {isInFlight && thinkingAbout !== undefined && (
        <div
          style={{
            marginTop: 'var(--ace-space-2)',
            paddingTop: 'var(--ace-space-2)',
            borderTop: '1px dashed var(--ace-line)',
            fontFamily: 'var(--ace-font-sans)',
            fontSize: 'var(--ace-text-xs)',
            color: 'var(--ace-ink-muted)',
            fontStyle: 'italic',
            letterSpacing: 'var(--ace-track-tight)',
          }}
        >
          considering {thinkingAbout}
        </div>
      )}
    </div>
  )
}
