// app/journey/PipelineStrip.tsx
//
// Small horizontal narration of the journey at the top — shows the user
// where they are in the cognitive flow at a glance.
//
// Three visual states (left to right):
//   past    — emerald CheckCircle, done is unambiguous
//   current — filled primary + pulsing dot, in motion
//   future  — bordered muted, waiting
import { Check } from '@phosphor-icons/react'

import { cn } from '@/lib/utils'

import type { JourneyStage } from '../../types/canvas'
import { PhaseIcon } from './PhaseIcon'
import { SessionsMenu } from './SessionsMenu'

interface PipelineStripProps {
  stages: JourneyStage[]
}

export function PipelineStrip({ stages }: PipelineStripProps) {
  if (stages.length <= 1) return null
  return (
    <nav
      aria-label="Deliberation pipeline"
      className="flex items-center gap-3 px-8 py-2.5 border-b border-border bg-background shadow-xs"
    >
      <div className="flex items-center gap-1 min-w-0 overflow-x-auto">
        {stages.map((stage, i) => (
          <PipelineStep
            key={stage.id}
            stage={stage}
            isLast={i === stages.length - 1}
          />
        ))}
      </div>
      {/* Sessions switcher lives here — re-entering a past deliberation is a
          move through the work, so it sits with the stage track. */}
      <div className="ml-auto shrink-0">
        <SessionsMenu />
      </div>
    </nav>
  )
}

function PipelineStep({ stage, isLast }: { stage: JourneyStage; isLast: boolean }) {
  const past = stage.status === 'past'
  const current = stage.status === 'current'
  const isConverge = stage.phase === 'validate' || stage.phase === 'critique'

  return (
    <>
      <div className="flex items-center gap-2 shrink-0">
        <span
          aria-hidden
          className={cn(
            'inline-flex h-6 w-6 items-center justify-center rounded-full ring-1 transition-all duration-200',
            past && 'text-emerald-700 bg-emerald-50 ring-emerald-300 dark:text-emerald-300 dark:bg-emerald-950 dark:ring-emerald-800',
            current && 'text-live-foreground bg-live ring-2 ring-live ring-offset-1 ring-offset-background shadow-sm',
            !past && !current && 'text-muted-foreground bg-transparent ring-border',
          )}
        >
          {past ? (
            <Check size={14} weight="bold" />
          ) : (
            <PhaseIcon phase={stage.phase} size="sm" filled={isConverge && current} />
          )}
        </span>
        <span
          className={cn(
            'font-mono text-xs uppercase tracking-wide transition-colors duration-200',
            current && 'text-foreground font-semibold',
            past && 'text-emerald-700 dark:text-emerald-300',
            !past && !current && 'text-muted-foreground',
          )}
        >
          {stage.phase}
        </span>
        {current && (
          <span
            aria-hidden
            className="h-1.5 w-1.5 rounded-full bg-live animate-pulse"
          />
        )}
      </div>
      {!isLast && (
        <div
          aria-hidden
          className={cn(
            'h-0.5 w-7 shrink-0 rounded-full transition-colors duration-200',
            past
              ? 'bg-emerald-400/70 dark:bg-emerald-600/70'
              : current
                ? 'bg-gradient-to-r from-live to-border'
                : 'bg-border/60',
          )}
        />
      )}
    </>
  )
}
