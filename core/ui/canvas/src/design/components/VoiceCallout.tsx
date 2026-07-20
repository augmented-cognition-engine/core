// core/ui/canvas/src/design/components/VoiceCallout.tsx
//
// A voice addressing the user inline in the reading flow. Names the
// "voice-addressing-you" semantic — one of the five distinct meanings
// of left-edge accent in the partnership UI vocabulary.
//
// Replaces the inline outer shell of AttentionCallout.tsx (avatar gutter
// + bordered editorial card + header line + body + action row). The
// callout is a *conversation moment*, never a notification or modal —
// it lives in the reading flow, stacks vertically with siblings, and
// has no dismiss affordance because conversation moments don't get
// dismissed, they get replied to.
//
// Tone variants:
//   - question:        voice asking the user for input (the AttentionCallout default)
//   - pushback:        voice disagreeing — accent shifts to warning tone
//   - acknowledgment:  voice confirming a state change (light variant)
import type { ReactNode } from 'react'

export type VoiceCalloutTone = 'question' | 'pushback' | 'acknowledgment'

export interface VoiceCalloutFrom {
  /** Display name of the addressing voice. */
  speaker: string
  /** Voice accent color (from disciplineIdentity). */
  accent: string
  /** Single-character initial or short glyph shown in the avatar gutter. */
  initial: string
}

export interface VoiceCalloutProps {
  from: VoiceCalloutFrom
  /** Who the voice is addressing. Default 'you'. Pass a name for
   *  voice-to-voice exchanges. */
  to?: string
  tone?: VoiceCalloutTone
  askedAt?: string
  /** Optional "what triggered this" small muted line under the body.
   *  ReactNode so consumers can render inline emphasis or links. */
  triggeredBy?: ReactNode
  /** The question or statement being addressed. Renders as serif prose. */
  question: ReactNode
  /** Optional action row at the bottom — input + quick action buttons.
   *  Compose Input + Button from the design system; don't inline. */
  children?: ReactNode
  dataTest?: string
}

const TONE_BORDER: Record<VoiceCalloutTone, string> = {
  question: '3px solid',
  pushback: '3px solid',
  acknowledgment: '2px solid',
}

export function VoiceCallout({
  from,
  to = 'you',
  tone = 'question',
  askedAt,
  triggeredBy,
  question,
  children,
  dataTest,
}: VoiceCalloutProps) {
  // Pushback retints the accent; the voice's own color stays in byline,
  // the edge marker pulls warning.
  const edgeColor = tone === 'pushback' ? 'var(--ace-warning)' : from.accent
  return (
    <div
      data-test={dataTest}
      data-callout-tone={tone}
      className="ace-just-landed"
      style={{
        position: 'relative',
        display: 'grid',
        gridTemplateColumns: 'auto 1fr',
        gap: 'var(--ace-space-3)',
        padding: 'var(--ace-space-4) var(--ace-space-4) var(--ace-space-4) var(--ace-space-3)',
        background: 'var(--ace-surface-raised)',
        borderRadius: 'var(--ace-radius-lg)',
        boxShadow: 'var(--ace-shadow-card)',
        maxWidth: '64ch',
        borderLeft: `${TONE_BORDER[tone]} ${edgeColor}`,
      }}
    >
      <span
        aria-hidden
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 32,
          height: 32,
          borderRadius: 'var(--ace-radius-pill)',
          background: 'var(--ace-surface-raised)',
          color: from.accent,
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-md)',
          fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          boxShadow: `0 0 0 1.5px ${from.accent}`,
        }}
      >
        {from.initial}
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-2)', minWidth: 0 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 'var(--ace-space-2)',
            fontFamily: 'var(--ace-font-sans)',
            fontSize: 'var(--ace-text-sm)',
            color: 'var(--ace-ink-muted)',
            letterSpacing: 'var(--ace-track-tight)',
          }}
        >
          <span style={{ color: from.accent, fontWeight: 'var(--ace-weight-semibold)' as unknown as number }}>
            {from.speaker}
          </span>
          <span aria-hidden style={{ color: 'var(--ace-ink-faint)' }}>→</span>
          <span style={{ color: 'var(--ace-ink)' }}>{to}</span>
          {askedAt !== undefined && (
            <span
              style={{
                color: 'var(--ace-ink-muted)',
                fontSize: 'var(--ace-text-xs)',
                fontFamily: 'var(--ace-font-mono)',
              }}
            >
              · {askedAt}
            </span>
          )}
        </div>
        <div
          style={{
            margin: 0,
            fontFamily: 'var(--ace-font-serif)',
            fontSize: 'var(--ace-text-prose)',
            lineHeight: 'var(--ace-leading-prose)',
            color: 'var(--ace-ink)',
            letterSpacing: '-0.005em',
          }}
        >
          {question}
        </div>
        {triggeredBy !== undefined && (
          <div
            style={{
              fontFamily: 'var(--ace-font-sans)',
              fontSize: 'var(--ace-text-xs)',
              color: 'var(--ace-ink-muted)',
              fontStyle: 'italic',
            }}
          >
            {triggeredBy}
          </div>
        )}
        {children !== undefined && (
          <div
            style={{
              marginTop: 'var(--ace-space-2)',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--ace-space-2)',
              flexWrap: 'wrap',
            }}
          >
            {children}
          </div>
        )}
      </div>
    </div>
  )
}
