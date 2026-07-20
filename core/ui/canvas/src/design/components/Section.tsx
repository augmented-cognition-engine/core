// frontend/src/design/components/Section.tsx
//
// The cog-section primitive — outlined card with a head (glyph + title +
// status pip) and a body. Generalizes CogSection from the deliberation
// surface so it can represent either a recipe phase OR a lens's
// contribution, depending on the host data model.
//
// The previous deliberation/CogSection.tsx was a one-off using inline
// styles + class names referencing deliberation.css. This is the
// design-system version: zero inline styling beyond token references,
// no dependency on deliberation.css's class system.
import type { ReactNode } from 'react'

import { Byline } from './Byline'
import { Card } from './Card'
import { Eyebrow } from './Eyebrow'
import { Glyph } from './Glyph'

export type SectionStatus = 'future' | 'active' | 'past'

export interface SectionProps {
  /** Section title — usually the discipline name uppercased. */
  title: string
  /** Italic-serif role byline below the title. */
  byline?: string
  /** Single-glyph identity mark + accent color. Use `lens` to pull from
   *  the discipline palette, or pass `glyph` + `tone` directly. */
  lens?: string
  glyph?: string
  accent?: string
  /** Meta line below the title (e.g. "Architecture review · 2 phases"). */
  meta?: ReactNode
  /** Right-aligned status pip — "FRAME · 0.82", "preparing…". */
  statusLabel?: ReactNode
  status?: SectionStatus
  children?: ReactNode
}

export function Section({
  title,
  byline,
  lens,
  glyph,
  accent,
  meta,
  statusLabel,
  status = 'active',
  children,
}: SectionProps) {
  const isDim = status === 'past' || status === 'future'
  return (
    <Card
      variant={isDim ? 'dim' : 'default'}
      padding="none"
      accent={accent}
      dataTest={`section-${title.toLowerCase().replace(/\s+/g, '-')}`}
    >
      {/* Head */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 'var(--ace-space-3)',
          padding: 'var(--ace-space-3) var(--ace-space-4)',
          flexWrap: 'wrap',
        }}
      >
        <Glyph lens={lens} glyph={glyph} tone={accent} size="md" />
        <Eyebrow>{title}</Eyebrow>
        {byline !== undefined && <Byline size="sm">{byline}</Byline>}
        <span style={{ flex: '1 1 auto' }} />
        {statusLabel !== undefined && (
          <span
            style={{
              fontSize: 'var(--ace-text-xs)',
              fontWeight: 'var(--ace-weight-bold)' as unknown as number,
              letterSpacing: 'var(--ace-track-wide)',
              textTransform: 'uppercase',
              color: status === 'future' ? 'var(--ace-ink-muted)' : (accent ?? 'var(--ace-ink)'),
              padding: '3px 8px',
              borderRadius: 'var(--ace-radius-sm)',
              background:
                status === 'future'
                  ? 'var(--ace-line-soft)'
                  : `color-mix(in oklab, ${accent ?? 'var(--ace-ink)'} 14%, transparent)`,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {statusLabel}
          </span>
        )}
      </div>
      {/* Meta line */}
      {meta !== undefined && (
        <div
          style={{
            padding: '0 var(--ace-space-4) var(--ace-space-2)',
            fontSize: 'var(--ace-text-sm)',
            color: 'var(--ace-ink-muted)',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {meta}
        </div>
      )}
      {/* Body */}
      {children !== undefined && (
        <div
          style={{
            borderTop: '1px solid var(--ace-line-soft)',
            padding: 'var(--ace-space-3) var(--ace-space-4)',
          }}
        >
          {children}
        </div>
      )}
    </Card>
  )
}
