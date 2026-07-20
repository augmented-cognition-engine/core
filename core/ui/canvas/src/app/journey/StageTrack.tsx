// app/journey/StageTrack.tsx
//
// One meta-intelligence's contribution at a single stage (L4 lens × L5
// instrument). Built against shadcn Card primitives. The avatar identity
// + discipline-toned accent give each parallel track its own visual
// signature so the parallel cognition reads as a multi-voice room, not a
// stack of identical blocks.
import { Badge } from '@/design/shadcn/ui/badge'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/design/shadcn/ui/tooltip'
import { cn } from '@/lib/utils'

import type { JourneyTrack } from '../../types/canvas'
import { MetaSkillAvatar } from './MetaSkillAvatar'

interface StageTrackProps {
  track: JourneyTrack
  quiet?: boolean
  /** Optional: signals from L3 that matched this meta-skill on the current task — surfaces via avatar tooltip. */
  matchedSignals?: string[]
}

export function StageTrack({ track, quiet = false, matchedSignals }: StageTrackProps) {
  const confPct = track.confidence !== undefined ? Math.round(track.confidence * 100) : null

  return (
    <Card
      size="sm"
      className={cn(
        'group/track min-w-[14rem] max-w-[20rem] flex-1 transition-shadow',
        track.inFlight === true && 'ring-2 ring-foreground/15',
        quiet && 'opacity-70',
      )}
    >
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <MetaSkillAvatar
              slug={track.metaSkill}
              size="sm"
              fullName={track.metaSkill.replace(/_/g, ' ')}
              matchedSignals={matchedSignals}
            />
            <span className="font-mono text-xs uppercase tracking-wide font-semibold text-foreground truncate">
              {track.label}
            </span>
          </div>
          {track.instrument !== undefined && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge
                  variant="ghost"
                  className="font-mono text-muted-foreground cursor-help"
                >
                  {track.instrument}
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                L5 instrument framework resolved at this phase
              </TooltipContent>
            </Tooltip>
          )}
        </div>

        <p className="font-heading text-sm leading-snug text-foreground">
          {track.contribution}
          {track.inFlight === true && (
            <span
              aria-hidden
              className="inline-block w-[0.5em] h-[1em] ml-1 align-text-bottom bg-live animate-pulse"
            />
          )}
        </p>

        {confPct !== null && <ConfidenceBar value={confPct} />}
      </CardContent>
    </Card>
  )
}

interface ConfidenceBarProps {
  /** 0–100. */
  value: number
}

function ConfidenceBar({ value }: ConfidenceBarProps) {
  const pct = Math.min(100, Math.max(0, value))
  return (
    <div className="flex items-center gap-2 pt-1">
      <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground shrink-0">
        confidence
      </span>
      <div
        role="progressbar"
        aria-label="confidence"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 flex-1 overflow-hidden rounded-full bg-muted ring-1 ring-border/50"
      >
        <div
          className={cn(
            'h-full transition-all duration-300',
            pct >= 70 ? 'bg-brand' : pct >= 40 ? 'bg-amber-500' : 'bg-destructive/60',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span
        className={cn(
          'font-mono text-xs tabular-nums font-semibold shrink-0',
          pct >= 70 ? 'text-brand' : pct >= 40 ? 'text-amber-600 dark:text-amber-400' : 'text-destructive',
        )}
      >
        {pct}%
      </span>
    </div>
  )
}
