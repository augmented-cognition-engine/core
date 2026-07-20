// core/ui/canvas/src/app/TeamReadout.tsx
//
// The team's read — flowing-prose rendering of multi-lens contributions.
// Replaces the uniform-card stack with a workshop-transcript voice:
// each contribution is a paragraph in serif body, with the byline tucked
// at the end (right-aligned, in the lens's accent). No status pips, no
// confidence chips, no "NEXT VOICE" arrows.
//
// The visual rhythm comes from typography (serif body for reading,
// sans-mono for bylines) and from light asymmetric indentation between
// voices — every other paragraph indents 24px so the eye can tell five
// voices are speaking without needing five identical card frames.
import type { ContributionState } from './state'

interface TeamReadoutProps {
  /** Editorial intro shown above the running narrative. */
  header?: React.ReactNode
  contributions: ContributionState[]
}

export function TeamReadout({ header, contributions }: TeamReadoutProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-5)',
        padding: 'var(--ace-space-2) 0',
      }}
    >
      {header !== undefined && (
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
          {header}
        </div>
      )}

      {contributions.map((c, i) => (
        <Voice key={c.id} contribution={c} index={i} />
      ))}
    </div>
  )
}

function Voice({
  contribution: c,
  index,
}: {
  contribution: ContributionState
  index: number
}) {
  // Alternating indentation gives the eye rhythm without using cards.
  // Every other voice indents slightly so the contributions feel like a
  // conversation, not a list.
  const indent = index % 2 === 1
  return (
    <div
      className="ace-voice"
      style={{
        marginLeft: indent ? 'var(--ace-space-8)' : 0,
        maxWidth: '64ch',
        position: 'relative',
        opacity: c.inFlight ? 0.92 : 1,
      }}
    >
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
      </p>
      <div
        style={{
          marginTop: 'var(--ace-space-2)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--ace-space-2)',
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-sm)',
          color: c.accent,
          letterSpacing: 'var(--ace-track-tight)',
        }}
      >
        <span
          aria-hidden
          style={{
            width: 18,
            height: 1,
            background: c.accent,
            display: 'inline-block',
          }}
        />
        <span style={{ fontWeight: 'var(--ace-weight-medium)' as unknown as number }}>
          {c.speaker}
        </span>
        {c.inFlight === true ? (
          <span
            className="ace-presence-dot--pulse"
            style={{
              color: 'var(--ace-ink-muted)',
              fontSize: 'var(--ace-text-xs)',
              marginLeft: 'var(--ace-space-1)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <span
              aria-hidden
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: c.accent,
              }}
            />
            still thinking
          </span>
        ) : c.landedAt !== undefined ? (
          <span
            style={{
              color: 'var(--ace-ink-muted)',
              fontSize: 'var(--ace-text-xs)',
              fontFamily: 'var(--ace-font-mono)',
              marginLeft: 'var(--ace-space-1)',
              letterSpacing: 'var(--ace-track-normal)',
            }}
          >
            · {c.landedAt}
          </span>
        ) : null}
      </div>
      {/* Thinking-about note — visible only when in-flight. Shows
          reasoning in motion: "considering X" rather than waiting
          silently for the full contribution to land. */}
      {c.inFlight === true && c.thinkingAbout !== undefined && (
        <div
          style={{
            marginTop: 'var(--ace-space-1)',
            fontFamily: 'var(--ace-font-sans)',
            fontSize: 'var(--ace-text-xs)',
            color: 'var(--ace-ink-muted)',
            fontStyle: 'italic',
            letterSpacing: 'var(--ace-track-tight)',
          }}
        >
          considering {c.thinkingAbout}
        </div>
      )}
    </div>
  )
}
