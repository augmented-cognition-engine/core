// core/ui/canvas/src/app/BriefMeBack.tsx
//
// "Since you were last here…" — the lead-in to the team's read.
//
// Rendered as journalist's dek, not a card. A small-caps eyebrow,
// the lede in serif prose, then a thin paragraph block of follow-up
// signals (what previously appeared as bullets) — set tighter,
// with a hairline source-tint mark at the start of each line.
//
// No card frame, no left-border bullet rails. The narrative IS the
// container.
import type { BriefMeBackState } from './state'

interface BriefMeBackProps {
  state: BriefMeBackState
}

export function BriefMeBack({ state }: BriefMeBackProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-3)',
        maxWidth: '64ch',
        padding: 'var(--ace-space-2) 0',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-xs)',
          fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          letterSpacing: 'var(--ace-track-widest)',
          textTransform: 'uppercase',
          color: 'var(--ace-ink-muted)',
        }}
      >
        Since you were last here
      </div>

      <p
        style={{
          margin: 0,
          fontFamily: 'var(--ace-font-serif)',
          fontSize: 'var(--ace-text-prose)',
          lineHeight: 'var(--ace-leading-prose)',
          color: 'var(--ace-ink)',
          letterSpacing: '-0.005em',
        }}
      >
        {state.lede}
      </p>

      {state.bullets.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--ace-space-1)',
            marginTop: 'var(--ace-space-1)',
          }}
        >
          {state.bullets.map((bullet) => (
            <p
              key={bullet.id}
              style={{
                margin: 0,
                fontFamily: 'var(--ace-font-serif)',
                fontSize: 'var(--ace-text-md)',
                lineHeight: 1.55,
                color: 'var(--ace-ink-soft)',
                paddingLeft: 'var(--ace-space-3)',
                position: 'relative',
              }}
            >
              <span
                aria-hidden
                style={{
                  position: 'absolute',
                  left: 0,
                  top: '0.6em',
                  width: 8,
                  height: 1,
                  background: bullet.toneVar ?? 'var(--ace-line-strong)',
                }}
              />
              {bullet.text}
            </p>
          ))}
        </div>
      )}

      {state.onExpand !== undefined && (
        <button
          type="button"
          onClick={state.onExpand}
          style={{
            alignSelf: 'flex-start',
            marginTop: 'var(--ace-space-2)',
            background: 'none',
            border: 'none',
            padding: 0,
            cursor: 'pointer',
            color: 'var(--ace-accent)',
            fontSize: 'var(--ace-text-sm)',
            fontFamily: 'var(--ace-font-sans)',
            fontWeight: 'var(--ace-weight-medium)' as unknown as number,
            textDecoration: 'underline',
            textUnderlineOffset: 3,
            textDecorationColor: 'var(--ace-line-strong)',
          }}
        >
          tell me more →
        </button>
      )}
    </div>
  )
}
