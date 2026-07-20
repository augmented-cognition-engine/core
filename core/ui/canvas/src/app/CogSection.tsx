// core/ui/canvas/src/app/CogSection.tsx
//
// One section in the canvas narrative scroll. Mirrors `.cog-section`
// from multiplayer.html: head (glyph + title + status pip) + body
// (polymorphic content per section type).
//
// Section status drives visual state:
//   - done    → full opacity, success-tinted status pip
//   - active  → full opacity, animated voice-accent pulse pip
//   - future  → dim paper + 40% opacity body, ink-muted status pip
//
// Body is whatever the section needs to render — option tree, capability
// graph, contribution rows, decision tile, etc. Passed in as children.
import { Card } from '../design/components'
import type { CogSectionState } from './state'

interface CogSectionProps {
  section: CogSectionState
}

export function CogSection({ section }: CogSectionProps) {
  const isFuture = section.status === 'future'
  const isActive = section.status === 'active'
  const isDone = section.status === 'done'
  const accent = section.accent ?? 'var(--ace-voice-accent)'

  return (
    <section
      id={`cs-${section.id}`}
      data-status={section.status}
      style={{
        opacity: isFuture ? 0.45 : 1,
        transition: 'opacity var(--ace-motion-land) var(--ace-ease-organic)',
      }}
    >
      <Card
        variant={isFuture ? 'dim' : 'default'}
        padding="none"
        accent={isFuture ? undefined : accent}
        interactive={!isFuture}
      >
        <style>{`
          @keyframes ace-section-pulse {
            0%, 100% { opacity: 1; box-shadow: 0 0 4px currentColor; }
            50% { opacity: 0.55; box-shadow: 0 0 10px currentColor; }
          }
        `}</style>

        {/* Head — glyph + title + subtitle + status pip */}
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 'var(--ace-space-3)',
            padding: 'var(--ace-space-3) var(--ace-space-4)',
            borderBottom: '1px solid var(--ace-line-soft)',
          }}
        >
          <span
            aria-hidden
            style={{
              fontSize: 'var(--ace-text-xl)',
              color: accent,
              fontFamily: 'var(--ace-font-sans)',
              lineHeight: 1,
              opacity: isFuture ? 0.6 : 1,
            }}
          >
            {section.glyph}
          </span>
          <span
            style={{
              fontFamily: 'var(--ace-font-sans)',
              fontSize: 'var(--ace-text-xl)',
              color: 'var(--ace-ink)',
              fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
              letterSpacing: 'var(--ace-track-tight)',
            }}
          >
            {section.title}
          </span>
          {section.subtitle !== undefined && (
            <span
              style={{
                fontFamily: 'var(--ace-font-sans)',
                fontSize: 'var(--ace-text-md)',
                color: 'var(--ace-ink-muted)',
                fontStyle: 'italic',
              }}
            >
              · {section.subtitle}
            </span>
          )}
          <span style={{ flex: '1 1 auto' }} />
          <StatusPip status={section.status} accent={accent} />
        </div>

        {/* Body */}
        <div
          style={{
            padding: 'var(--ace-space-4) var(--ace-space-4)',
            opacity: isFuture ? 0.5 : 1,
          }}
        >
          {section.body}
        </div>
      </Card>

      {/* Annotations for tests/dev */}
      <span
        hidden
        data-cog-status={section.status}
        data-cog-id={section.id}
        data-cog-active={isActive ? 'true' : undefined}
        data-cog-done={isDone ? 'true' : undefined}
      />
    </section>
  )
}

function StatusPip({
  status,
  accent,
}: {
  status: CogSectionState['status']
  accent: string
}) {
  const color =
    status === 'done'
      ? 'var(--ace-success)'
      : status === 'active'
        ? accent
        : 'var(--ace-ink-muted)'
  const label = status === 'done' ? 'done' : status === 'active' ? 'working' : 'future'
  return (
    <span
      aria-label={label}
      title={label}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 'var(--ace-text-xs)',
        fontWeight: 'var(--ace-weight-bold)' as unknown as number,
        letterSpacing: 'var(--ace-track-wide)',
        textTransform: 'uppercase',
        color,
        fontFamily: 'var(--ace-font-sans)',
      }}
    >
      <span
        aria-hidden
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: color,
          animation:
            status === 'active'
              ? 'ace-section-pulse 1.4s ease-in-out infinite'
              : 'none',
          boxShadow: status === 'done' ? `0 0 4px ${color}` : 'none',
        }}
      />
      {label}
    </span>
  )
}
