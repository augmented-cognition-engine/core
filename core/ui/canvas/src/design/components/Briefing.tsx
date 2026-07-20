// core/ui/canvas/src/design/components/Briefing.tsx
//
// The persistent briefing artifact — what ACE wrote while the user was
// away. NOT a daily digest, NOT a notification summary, NOT an inbox.
// A briefing is a long-form partner-voice narrative the user can read,
// react to, and discuss.
//
// Visual treatment: wide reading column, serif body, period header,
// generous leading. The container is purposefully sparse — the body is
// the experience.
//
// Voice rule (from voice-style-guide.md): "Briefing — Narrative,
// longer-form, partner voice throughout." Children are paragraphs +
// any inline primitives (ProactiveLine, ContributionLane references,
// SeverityFinding) the briefing wants to surface.
import type { ReactNode } from 'react'

export interface BriefingProps {
  /** The period this briefing covers ("Since you stepped away",
   *  "This morning", "Last Thursday's session"). Renders as small-caps
   *  eyebrow above the title. */
  period: string
  /** Briefing title. Renders as display-serif. */
  title: string
  /** The briefing body. Pass paragraphs as ReactNode children. */
  children: ReactNode
  dataTest?: string
}

export function Briefing({ period, title, children, dataTest }: BriefingProps) {
  return (
    <article
      data-test={dataTest}
      style={{
        maxWidth: '64ch',
        margin: '0 auto',
        padding: 'var(--ace-space-8) var(--ace-space-6)',
        fontFamily: 'var(--ace-font-serif)',
        color: 'var(--ace-ink)',
        lineHeight: 'var(--ace-leading-prose)',
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
          marginBottom: 'var(--ace-space-2)',
        }}
      >
        {period}
      </div>
      <h1
        style={{
          margin: 0,
          fontFamily: 'var(--ace-font-serif)',
          fontSize: 'var(--ace-text-3xl)',
          fontWeight: 'var(--ace-weight-regular)' as unknown as number,
          letterSpacing: 'var(--ace-track-tight)',
          lineHeight: 'var(--ace-leading-tight)',
          color: 'var(--ace-ink-strong)',
        }}
      >
        {title}
      </h1>
      <div
        style={{
          marginTop: 'var(--ace-space-5)',
          fontSize: 'var(--ace-text-prose)',
          color: 'var(--ace-ink-soft)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--ace-space-4)',
        }}
      >
        {children}
      </div>
    </article>
  )
}
