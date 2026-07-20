// core/ui/canvas/src/design/components/CompositionLens.tsx
//
// L3 composition visibility — renders "the orchestra" on the canvas.
// Subscribes (when wired) to canvas.composition.selected events and shows
// which of the 22 meta-intelligences self-nominated for the current task.
//
// The substrate's anti-predefined commitment becomes visible here: instead
// of a hardcoded "task X = these meta-skills" mapping, the user sees the
// problem-derived selection that emerged from activation_signals + affinities
// + composability.
//
// Voice rules:
//   - Reads as observation, not announcement ("X is weighing in", not
//     "[INFO] X engaged")
//   - Quiet when no composition is active — does not insist
//   - The classification line below the meta-skills is the "why this set"
//     hint — the lightest possible provenance affordance
//
// Usage:
//   <CompositionLens payload={lastCompositionPayload} />
//
// payload mirrors CompositionSelectedPayload from types/canvas.ts.
import type { ReactNode } from 'react'

import type { CompositionSelectedPayload } from '../../types/canvas'
import { Chip } from './Chip'

export interface CompositionLensProps {
  /** Latest composition.selected payload from the canvas event bus, or null
   *  when no composition has been emitted in the current session. */
  payload: CompositionSelectedPayload | null

  /** Optional title override — defaults to "Weighing in now". */
  title?: string

  /** Optional empty-state slot — rendered when payload is null. */
  emptyState?: ReactNode

  /** Optional click handler per meta-skill chip — useful when the canvas
   *  surfaces want to let users dive into a specific intelligence. */
  onMetaSkillClick?: (slug: string) => void
}

/** Trim the `_intelligence` suffix for display. */
function displaySlug(slug: string): string {
  return slug.endsWith('_intelligence') ? slug.slice(0, -'_intelligence'.length) : slug
}

/** Compose the classification trail — discipline · task_type · mode · archetype. */
function classificationTrail(payload: CompositionSelectedPayload): string {
  const cl = payload.classification
  if (!cl) return ''
  const parts: string[] = []
  if (cl.discipline) parts.push(cl.discipline)
  if (cl.task_type) parts.push(cl.task_type)
  if (cl.mode) parts.push(cl.mode)
  if (cl.archetype) parts.push(cl.archetype)
  return parts.join(' · ')
}

export function CompositionLens({
  payload,
  title = 'Weighing in now',
  emptyState,
  onMetaSkillClick,
}: CompositionLensProps) {
  if (payload === null) {
    if (emptyState !== undefined) return <>{emptyState}</>
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--ace-space-2)',
          padding: 'var(--ace-space-4)',
          background: 'var(--ace-surface-elevated)',
          border: '1px solid var(--ace-line-soft)',
          borderRadius: 'var(--ace-radius-md)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--ace-font-sans)',
            fontSize: 'var(--ace-text-xs)',
            color: 'var(--ace-ink-faint)',
            letterSpacing: 'var(--ace-tracking-wide)',
            textTransform: 'uppercase',
          }}
        >
          The orchestra
        </span>
        <span
          style={{
            fontFamily: 'var(--ace-font-serif)',
            fontSize: 'var(--ace-text-sm)',
            color: 'var(--ace-ink-soft)',
            lineHeight: 'var(--ace-leading-snug)',
          }}
        >
          No task in flight. The substrate is listening.
        </span>
      </div>
    )
  }

  const trail = classificationTrail(payload)
  const depthLabel = payload.fusion_mode
    ? `depth ${payload.depth} · fused`
    : `depth ${payload.depth} · multiphase`

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-3)',
        padding: 'var(--ace-space-4)',
        background: 'var(--ace-surface-elevated)',
        border: '1px solid var(--ace-line-soft)',
        borderRadius: 'var(--ace-radius-md)',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          gap: 'var(--ace-space-3)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--ace-font-sans)',
            fontSize: 'var(--ace-text-xs)',
            color: 'var(--ace-ink-faint)',
            letterSpacing: 'var(--ace-tracking-wide)',
            textTransform: 'uppercase',
          }}
        >
          {title}
        </span>
        <span
          style={{
            fontFamily: 'var(--ace-font-mono)',
            fontSize: 'var(--ace-text-xs)',
            color: 'var(--ace-ink-faint)',
          }}
        >
          {depthLabel}
        </span>
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 'var(--ace-space-2)',
        }}
      >
        {payload.meta_skills.map((slug) => (
          <Chip
            key={slug}
            variant="subtle"
            onClick={onMetaSkillClick !== undefined ? () => onMetaSkillClick(slug) : undefined}
            title={slug}
          >
            {displaySlug(slug)}
          </Chip>
        ))}
      </div>

      {trail !== '' && (
        <span
          style={{
            fontFamily: 'var(--ace-font-serif)',
            fontSize: 'var(--ace-text-xs)',
            color: 'var(--ace-ink-faint)',
            lineHeight: 'var(--ace-leading-snug)',
            fontStyle: 'italic',
          }}
        >
          {trail}
        </span>
      )}
    </div>
  )
}
