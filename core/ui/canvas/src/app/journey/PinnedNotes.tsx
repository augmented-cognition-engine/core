// app/journey/PinnedNotes.tsx
//
// Side-rail of accumulated artifacts — L7 prior decisions + L8 ambient
// sentinel findings. Collapsible (toggle button on the rail head) and
// internally scrollable so long sentinel lists don't run off the screen.
//
// Phosphor icons + shadcn primitives.
import {
  Bookmark,
  CaretDoubleLeft,
  CaretDoubleRight,
  ShieldWarning,
  Warning,
} from '@phosphor-icons/react'
import { useState } from 'react'

import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import { ScrollArea } from '@/design/shadcn/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/design/shadcn/ui/tooltip'
import { cn } from '@/lib/utils'

import type {
  JourneyDecision,
  JourneySentinelMark,
} from '../../types/canvas'
import { MetaSkillAvatar } from './MetaSkillAvatar'

interface PinnedNotesProps {
  decisions?: JourneyDecision[]
  sentinel?: JourneySentinelMark[]
}

export function PinnedNotes({ decisions, sentinel }: PinnedNotesProps) {
  const [collapsed, setCollapsed] = useState(false)

  const hasAnything =
    (decisions !== undefined && decisions.length > 0) ||
    (sentinel !== undefined && sentinel.length > 0)
  if (!hasAnything) return null

  const decisionCount = decisions?.length ?? 0
  const sentinelCount = sentinel?.length ?? 0

  if (collapsed) {
    return (
      <aside
        aria-label="Pinned artifacts (collapsed)"
        className="flex flex-col items-center gap-3 py-3 flex-none w-12 border-l border-border bg-background/60"
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Expand pinned artifacts"
              className="cursor-pointer"
              onClick={() => setCollapsed(false)}
            >
              <CaretDoubleLeft size={14} weight="bold" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>expand pinned artifacts</TooltipContent>
        </Tooltip>
        {decisionCount > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex flex-col items-center gap-1 cursor-help text-primary">
                <Bookmark size={18} weight="duotone" />
                <span className="font-mono text-xs">{decisionCount}</span>
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {decisionCount} decision{decisionCount === 1 ? '' : 's'} this session · L7
            </TooltipContent>
          </Tooltip>
        )}
        {sentinelCount > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex flex-col items-center gap-1 cursor-help text-amber-600 dark:text-amber-400">
                <ShieldWarning size={18} weight="duotone" />
                <span className="font-mono text-xs">{sentinelCount}</span>
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {sentinelCount} sentinel mark{sentinelCount === 1 ? '' : 's'} · L8
            </TooltipContent>
          </Tooltip>
        )}
      </aside>
    )
  }

  return (
    <aside
      aria-label="Pinned artifacts"
      className="flex flex-col flex-none w-72 max-w-80 border-l border-border bg-background/60"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <span className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
          pinned · this session
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Collapse pinned artifacts"
              className="cursor-pointer"
              onClick={() => setCollapsed(true)}
            >
              <CaretDoubleRight size={14} weight="bold" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>collapse pinned artifacts</TooltipContent>
        </Tooltip>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col gap-5 p-4">
          {decisions !== undefined && decisions.length > 0 && (
            <section className="flex flex-col gap-2">
              <h4 className="inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide text-muted-foreground">
                <Bookmark size={14} weight="duotone" className="text-primary" />
                decisions · L7
              </h4>
              {decisions.map((d) => (
                <Card key={d.id} size="sm">
                  <CardContent className="flex flex-col gap-2">
                    <p className="font-heading text-sm leading-snug text-foreground">
                      {d.title}
                    </p>
                    {d.cited !== undefined && d.cited.length > 0 && (
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-xs text-muted-foreground">
                          cited:
                        </span>
                        <div className="flex -space-x-1.5">
                          {d.cited.map((c) => (
                            <MetaSkillAvatar
                              key={c}
                              slug={c}
                              size="sm"
                              fullName={c.replace(/_/g, ' ')}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </section>
          )}

          {sentinel !== undefined && sentinel.length > 0 && (
            <section className="flex flex-col gap-2">
              <h4 className="inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide text-muted-foreground">
                <ShieldWarning size={14} weight="duotone" className="text-amber-600 dark:text-amber-400" />
                sentinel · L8
              </h4>
              {sentinel.map((m, i) => (
                <Card
                  key={`${m.source}-${i}`}
                  size="sm"
                  className="border-dashed bg-card/40 shadow-none"
                >
                  <CardContent className="flex items-start gap-2">
                    <Warning
                      size={14}
                      weight="duotone"
                      className={cn(
                        'mt-0.5 flex-none',
                        m.severity === 'high' && 'text-destructive',
                        m.severity === 'medium' && 'text-amber-600 dark:text-amber-400',
                        m.severity === 'low' && 'text-muted-foreground',
                      )}
                    />
                    <div className="flex flex-col gap-1 min-w-0">
                      <Badge variant="outline" className="w-fit font-mono text-[10px]">
                        {m.source}
                      </Badge>
                      <p className="font-heading text-sm leading-snug text-muted-foreground">
                        {m.headline}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </section>
          )}
        </div>
      </ScrollArea>
    </aside>
  )
}
