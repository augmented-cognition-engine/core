// app/journey/StageSurfaces.tsx
//
// L8 sentinel marks + L9 prediction tile + L7 inline-decision rendering.
// Built against shadcn primitives.
import {
  Bookmark,
  ChartLineUp,
  ShieldWarning,
  Warning,
} from '@phosphor-icons/react'

import { Badge } from '@/design/shadcn/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/design/shadcn/ui/card'
import { Separator } from '@/design/shadcn/ui/separator'
import { cn } from '@/lib/utils'

import type {
  JourneyDecision,
  JourneyPrediction,
  JourneySentinelMark,
} from '../../types/canvas'

interface SentinelMarkRowProps {
  marks: JourneySentinelMark[]
}

/** L8 — sentinel findings active at this stage. */
export function SentinelMarkRow({ marks }: SentinelMarkRowProps) {
  if (marks.length === 0) return null
  return (
    <div className="flex flex-col gap-1 px-5 py-3">
      <Separator />
      <span className="inline-flex items-center gap-1.5 pt-2 font-mono text-xs uppercase tracking-wide text-muted-foreground">
        <ShieldWarning size={14} weight="duotone" className="text-amber-600 dark:text-amber-400" />
        sentinel · L8
      </span>
      {marks.map((m, i) => (
        <div
          key={`${m.source}-${i}`}
          className="flex items-start gap-2 font-heading text-sm leading-snug text-muted-foreground"
        >
          <Warning
            size={14}
            weight="duotone"
            className={cn(
              'mt-[3px] flex-none',
              m.severity === 'high' && 'text-destructive',
              m.severity === 'medium' && 'text-amber-600 dark:text-amber-400',
              m.severity === 'low' && 'text-muted-foreground',
            )}
          />
          <span>
            <span className="mr-2 font-mono text-xs text-muted-foreground">
              {m.source}
            </span>
            {m.headline}
          </span>
        </div>
      ))}
    </div>
  )
}

interface PredictionTileProps {
  prediction: JourneyPrediction
}

/** L9 — forward prediction attached at a converge stage. */
export function PredictionTile({ prediction }: PredictionTileProps) {
  const { horizonDays, forecast, falsifyIf, reconciled, calibrationScore } = prediction
  const meta =
    reconciled === true
      ? `reconciled · ${formatCalibration(calibrationScore)}`
      : `+${horizonDays}d horizon`

  return (
    <div className="flex flex-col gap-2 px-5 py-4">
      <Separator />
      <div className="flex items-baseline justify-between gap-2 pt-2">
        <span className="inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide text-muted-foreground">
          <ChartLineUp size={14} weight="duotone" />
          prediction · L9
        </span>
        <span className="font-mono text-xs text-muted-foreground">{meta}</span>
      </div>
      <p className="font-heading text-sm leading-snug text-foreground">
        <strong className="font-semibold">I expect: </strong>
        {forecast}
      </p>
      <p className="font-heading text-sm leading-snug text-muted-foreground">
        <span className="mr-2 font-sans text-xs uppercase tracking-wide font-semibold text-muted-foreground">
          falsify if
        </span>
        {falsifyIf}
      </p>
    </div>
  )
}

interface InlineDecisionProps {
  decision: JourneyDecision
}

/** L7 — a decision card landing inline at a converge stage. */
export function InlineDecision({ decision }: InlineDecisionProps) {
  const confPct = decision.confidence !== undefined ? Math.round(decision.confidence * 100) : null
  return (
    <Card size="sm" className="mx-5 mt-3 ring-2 ring-foreground/15">
      <CardHeader>
        <Badge variant="default" className="inline-flex items-center gap-1.5">
          <Bookmark size={12} weight="fill" />
          decision captured · L7
        </Badge>
        <CardTitle className="pt-1">{decision.title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {decision.rationale !== undefined && (
          <p className="font-heading text-sm leading-snug text-muted-foreground">
            {decision.rationale}
          </p>
        )}
        <div className="flex flex-wrap gap-3 font-mono text-xs text-muted-foreground">
          {confPct !== null && <span>confidence {confPct}%</span>}
          {decision.cited !== undefined && decision.cited.length > 0 && (
            <span>cited: {decision.cited.join(' · ')}</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function formatCalibration(score: number | undefined): string {
  if (score === undefined) return '—'
  return `${Math.round(score * 100)}% calibrated`
}
