// app/journey/StageCard.tsx
//
// One stage of the deliberation journey. Three visual states:
//
//   past     — collapsed to a one-line summary
//   current  — fully visible, tracks animate in, gate is live
//   future   — quiet hint (icon + label + waiting indicator)
//
// Phosphor icons throughout via PhaseIcon. No unicode glyphs.
import { Check, Hourglass } from '@phosphor-icons/react'

import { Badge } from '@/design/shadcn/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/design/shadcn/ui/card'
import { cn } from '@/lib/utils'

import type { JourneyForkTrace, JourneyStage } from '../../types/canvas'
import { CapabilityGraph } from './CapabilityGraph'
import { PhaseIcon } from './PhaseIcon'
import { ReasoningForkSurface } from './ReasoningForkSurface'
import { StageGate } from './StageGate'
import { InlineDecision, PredictionTile, SentinelMarkRow } from './StageSurfaces'
import { StageSynthesis } from './StageSynthesis'
import { StageTrack } from './StageTrack'
import type { ToolSignal } from './WorkingRoomRibbon'
import { deriveSignalsFromTracks, WorkingRoomRibbon } from './WorkingRoomRibbon'

interface StageCardProps {
  stage: JourneyStage
  continueLabel?: string
  onRespond?: (text: string) => void
  onContinue?: () => void
  /** Live tool signals — passed from live orchestration into the
   *  WorkingRoomRibbon on the current stage. Fixture stages omit. */
  toolSignals?: ToolSignal[]
  /** Live, on-demand fork compute for THIS stage's conclusion (the 'paths not taken' offer). When
   *  present, the ReasoningForkSurface shows even without a pre-computed stage.forkTrace. */
  forkFetch?: () => Promise<JourneyForkTrace | null>
}

export function StageCard({ stage, continueLabel, onRespond, onContinue, toolSignals, forkFetch }: StageCardProps) {
  if (stage.status === 'future') return <FutureStub stage={stage} />
  if (stage.status === 'past') return <PastSummary stage={stage} />
  return (
    <CurrentStage
      stage={stage}
      continueLabel={continueLabel}
      onRespond={onRespond}
      onContinue={onContinue}
      toolSignals={toolSignals}
      forkFetch={forkFetch}
    />
  )
}

// ---------------------------------------------------------------------------
// Current stage — the live working surface
// ---------------------------------------------------------------------------

function CurrentStage({ stage, continueLabel, onRespond, onContinue, toolSignals, forkFetch }: StageCardProps) {
  const signals = stage.workingSignals ?? deriveSignalsFromTracks(stage.tracks)
  return (
    <Card className="overflow-hidden ring-1 ring-foreground/15 shadow-md">
      <StageHead stage={stage} live />

      {/* Optional inline capability graph (Frame stage usually) */}
      {stage.capabilityGraph !== undefined && (
        <CardContent>
          <CapabilityGraph
            nodes={stage.capabilityGraph.nodes}
            edges={stage.capabilityGraph.edges}
          />
        </CardContent>
      )}

      {/* L4 parallel tracks */}
      {stage.tracks.length > 0 && (
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {stage.tracks.map((track) => (
              <StageTrack
                key={track.metaSkill}
                track={track}
                matchedSignals={stage.matchedSignalsByMetaSkill?.[track.metaSkill]}
              />
            ))}
          </div>
        </CardContent>
      )}

      {/* L6 synthesis */}
      {stage.synthesis !== undefined && <StageSynthesis synthesis={stage.synthesis} />}

      {/* L7 inline-captured decisions */}
      {stage.decisions !== undefined &&
        stage.decisions.map((d) => <InlineDecision key={d.id} decision={d} />)}

      {/* L9 prediction tile */}
      {stage.prediction !== undefined && <PredictionTile prediction={stage.prediction} />}

      {/* L8 sentinel marks */}
      {stage.sentinel !== undefined && stage.sentinel.length > 0 && (
        <SentinelMarkRow marks={stage.sentinel} />
      )}

      {/* Forkable foresight — "paths not taken": branch-from-checkpoint comparison, inline.
          Pre-computed (demo / cached) via stage.forkTrace, or live on-demand via forkFetch. */}
      {(stage.forkTrace !== undefined || forkFetch !== undefined) && (
        <ReasoningForkSurface trace={stage.forkTrace} fetchTrace={forkFetch} />
      )}

      {/* Working-room ribbon — live activity micro-signals (voice + tools) */}
      <WorkingRoomRibbon signals={signals} toolSignals={toolSignals} />

      {/* gate */}
      <StageGate
        respondPlaceholder={`respond at ${stage.phase}…`}
        continueLabel={continueLabel ?? 'continue'}
        onRespond={onRespond}
        onContinue={onContinue}
      />
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Past stage — collapsed summary
// ---------------------------------------------------------------------------

function PastSummary({ stage }: { stage: JourneyStage }) {
  const summary = pickSummary(stage)
  return (
    <Card size="sm" className="bg-muted/40 shadow-none ring-0">
      <CardHeader className="border-b pb-3">
        <StageHead stage={stage} live={false} compact />
      </CardHeader>
      {stage.capabilityGraph !== undefined && (
        <CardContent>
          <CapabilityGraph
            nodes={stage.capabilityGraph.nodes}
            edges={stage.capabilityGraph.edges}
          />
        </CardContent>
      )}
      {summary !== undefined && (
        <CardContent>
          <p className="font-heading text-sm leading-snug text-muted-foreground">
            {summary}
          </p>
        </CardContent>
      )}
    </Card>
  )
}

function pickSummary(stage: JourneyStage): string | undefined {
  if (stage.synthesis !== undefined) return stage.synthesis.implication
  if (stage.tracks.length > 0) return stage.tracks[0].contribution
  return undefined
}

// ---------------------------------------------------------------------------
// Future stage — placeholder
// ---------------------------------------------------------------------------

function FutureStub({ stage }: { stage: JourneyStage }) {
  return (
    <Card
      size="sm"
      className="border-dashed border-border bg-card/30 shadow-none ring-0 opacity-70 transition-opacity duration-200"
    >
      <CardHeader className="flex flex-row items-center gap-3">
        <span className="inline-flex h-6 w-6 items-center justify-center text-muted-foreground">
          <PhaseIcon phase={stage.phase} size="default" />
        </span>
        <span className="font-mono text-sm uppercase tracking-wide text-muted-foreground">
          {stage.title}
        </span>
        <Badge
          variant="ghost"
          className="ml-auto inline-flex items-center gap-1 text-muted-foreground"
        >
          <Hourglass size={12} weight="regular" />
          waiting
        </Badge>
      </CardHeader>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Stage head
// ---------------------------------------------------------------------------

interface StageHeadProps {
  stage: JourneyStage
  live: boolean
  compact?: boolean
}

function StageHead({ stage, live, compact = false }: StageHeadProps) {
  const isConverge = stage.phase === 'validate' || stage.phase === 'critique'
  const isPast = stage.status === 'past'
  const inner = (
    <>
      <span
        className={cn(
          'inline-flex h-7 w-7 items-center justify-center rounded-full',
          live && 'bg-live/15 text-live',
          isPast && 'bg-[var(--chart-1)]/10 text-[var(--chart-1)] ring-1 ring-[var(--chart-1)]/30',
          !live && !isPast && 'bg-muted text-muted-foreground',
        )}
      >
        {isPast ? (
          <Check size={16} weight="bold" />
        ) : (
          <PhaseIcon phase={stage.phase} size="default" filled={isConverge && live} />
        )}
      </span>
      <CardTitle className="text-base font-medium">
        {stage.title}
      </CardTitle>
      {stage.subtitle !== undefined && (
        <span className="font-heading italic text-sm text-muted-foreground">
          {stage.subtitle}
        </span>
      )}
      {live && (
        <span className="ml-auto inline-flex items-center gap-2 font-mono text-xs text-live">
          <span
            aria-hidden
            className="h-1.5 w-1.5 rounded-full bg-live animate-pulse"
          />
          in motion
        </span>
      )}
      {isPast && (
        <span className="ml-auto font-mono text-xs uppercase tracking-wide text-[var(--chart-1)]">
          done
        </span>
      )}
    </>
  )

  if (compact) {
    return <div className="flex items-center gap-3">{inner}</div>
  }

  return (
    <CardHeader className="flex flex-row items-center gap-3 border-b pb-3">
      {inner}
    </CardHeader>
  )
}
