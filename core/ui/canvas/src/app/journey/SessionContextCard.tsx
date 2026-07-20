// app/journey/SessionContextCard.tsx
//
// Brief-me-back card. Surfaces "since you were last here" context above
// the deliberation. Collapsed by default — just the lede + a count
// summary in a single quiet row. Click the row (or chevron) to expand
// the bullet list. Dismissible.
//
// Phosphor icons throughout — no unicode emoji glyphs.
import {
  CaretDown,
  CaretRight,
  CheckSquare,
  Clock,
  Sparkle,
  Warning,
  X,
} from '@phosphor-icons/react'
import type { ComponentType } from 'react'
import { useState } from 'react'

import { Button } from '@/design/shadcn/ui/button'
import { cn } from '@/lib/utils'

export type SessionContextCategory = 'decision' | 'prediction' | 'sentinel' | 'memory'

export interface SessionContextBullet {
  id: string
  category: SessionContextCategory
  text: string
}

interface SessionContextCardProps {
  lede: string
  rangeLabel?: string
  bullets: SessionContextBullet[]
  footnote?: string
  /** Whether the card opens expanded. Defaults to false (collapsed) so the
   *  live deliberation stays above the fold. */
  defaultExpanded?: boolean
}

const CATEGORY_ICON: Record<
  SessionContextCategory,
  ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>
> = {
  decision: CheckSquare as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  prediction: Clock as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  sentinel: Warning as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  memory: Sparkle as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
}

const CATEGORY_TONE: Record<SessionContextCategory, string> = {
  decision: 'text-primary',
  prediction: 'text-foreground',
  sentinel: 'text-amber-600 dark:text-amber-400',
  memory: 'text-violet-600 dark:text-violet-400',
}

/** Build a "3 decisions · 1 prediction · 2 sentinel · 4 memories" summary
 *  from the bullet category distribution. */
function summarize(bullets: SessionContextBullet[]): string {
  const counts: Record<SessionContextCategory, number> = {
    decision: 0,
    prediction: 0,
    sentinel: 0,
    memory: 0,
  }
  bullets.forEach((b) => {
    counts[b.category] += 1
  })
  const parts: string[] = []
  if (counts.decision > 0) parts.push(`${counts.decision} decision${counts.decision === 1 ? '' : 's'}`)
  if (counts.prediction > 0) parts.push(`${counts.prediction} prediction${counts.prediction === 1 ? '' : 's'}`)
  if (counts.sentinel > 0) parts.push(`${counts.sentinel} sentinel`)
  if (counts.memory > 0) parts.push(`${counts.memory} memor${counts.memory === 1 ? 'y' : 'ies'}`)
  return parts.join(' · ')
}

export function SessionContextCard({
  lede,
  rangeLabel,
  bullets,
  footnote,
  defaultExpanded = false,
}: SessionContextCardProps) {
  const [dismissed, setDismissed] = useState(false)
  const [expanded, setExpanded] = useState(defaultExpanded)
  if (dismissed) return null

  return (
    <section
      aria-label="Session context"
      className={cn(
        'mx-8 mt-6 rounded-md bg-muted/40 border border-border/60',
        'transition-colors duration-200',
      )}
    >
      <div
        className={cn(
          'flex items-center justify-between gap-3 px-3 py-2',
          expanded && 'border-b border-border/60',
        )}
      >
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-2 cursor-pointer min-w-0 text-left transition-colors duration-200 hover:text-foreground"
          aria-expanded={expanded}
        >
          {expanded ? (
            <CaretDown size={12} weight="bold" className="shrink-0 text-muted-foreground" />
          ) : (
            <CaretRight size={12} weight="bold" className="shrink-0 text-muted-foreground" />
          )}
          <span className="font-mono text-[10px] uppercase tracking-widest text-primary/80 shrink-0">
            since you were last
          </span>
          <span className="font-heading text-sm text-foreground truncate">
            {lede.replace(/^since you were last here ·\s*/i, '')}
          </span>
          <span className="font-mono text-xs text-muted-foreground shrink-0 hidden sm:inline">
            · {summarize(bullets)}
          </span>
        </button>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Dismiss session context"
          onClick={() => setDismissed(true)}
          className="cursor-pointer shrink-0 -mr-1"
        >
          <X size={12} weight="bold" />
        </Button>
      </div>

      {expanded && (
        <div className="flex flex-col gap-1.5 px-3 pt-2.5 pb-3">
          {rangeLabel !== undefined && (
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {rangeLabel}
            </span>
          )}
          {bullets.map((b) => {
            const Icon = CATEGORY_ICON[b.category]
            return (
              <div
                key={b.id}
                className="flex items-baseline gap-2.5 font-heading text-sm leading-snug text-muted-foreground"
              >
                <Icon
                  size={14}
                  weight="duotone"
                  className={`shrink-0 mt-[3px] ${CATEGORY_TONE[b.category]}`}
                />
                <span>{b.text}</span>
              </div>
            )
          })}
          {footnote !== undefined && (
            <p className="pt-1 font-mono text-[11px] text-muted-foreground">
              {footnote}
            </p>
          )}
        </div>
      )}
    </section>
  )
}
