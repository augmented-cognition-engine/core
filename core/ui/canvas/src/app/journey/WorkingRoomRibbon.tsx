// app/journey/WorkingRoomRibbon.tsx
//
// Live activity micro-signals at the bottom of the current stage. Two
// classes of signal share the same ribbon, separated by a thin divider:
//
//   1. Voice signals — meta-skills speaking (PM typing, Architect spoke 3s ago)
//   2. Tool signals — tools the partner is firing live (ace_search running,
//      web_search returned 4s ago)
//
// The ribbon is the "I can hear them working" surface — both who is
// thinking AND what tools they're reaching for. Together they make the
// partnership thesis visible: the partner isn't just speaking, it's
// using its tools in the room with you.
//
// Built against shadcn semantic tokens + phosphor icons + MetaSkillAvatar.
import { Hammer } from '@phosphor-icons/react'

import { cn } from '@/lib/utils'

import type { JourneyTrack } from '../../types/canvas'
import { MetaSkillAvatar } from './MetaSkillAvatar'

export interface WorkingSignal {
  /** Meta-skill slug (e.g. 'risk_intelligence'). */
  metaSkill: string
  /** Display label. */
  label: string
  /** State drives the dot/typography. */
  state: 'typing' | 'just-spoke' | 'waiting'
  /** Editorial timestamp shown next to the state (e.g. "3s ago"). */
  whenLabel?: string
}

export interface ToolSignal {
  /** Stable id (typically the backend task_id). */
  id: string
  /** Tool slug (e.g. 'ace_search', 'web_search'). */
  tool: string
  /** Short input summary if the backend provided one. */
  inputSummary?: string
  /** State drives the dot + verb. */
  state: 'running' | 'returned'
  /** Editorial when-label ("4s ago"). */
  whenLabel?: string
}

interface WorkingRoomRibbonProps {
  signals: WorkingSignal[]
  /** Optional tool signals shown alongside voice signals. */
  toolSignals?: ToolSignal[]
}

export function WorkingRoomRibbon({ signals, toolSignals = [] }: WorkingRoomRibbonProps) {
  if (signals.length === 0 && toolSignals.length === 0) return null
  return (
    <div className="flex items-center gap-2 px-5 py-1.5 border-t border-border bg-muted/30">
      <span
        aria-hidden
        className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground/70 shrink-0"
      >
        room
      </span>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 min-w-0">
        {signals.map((s) => (
          <WorkingPip key={s.metaSkill} signal={s} />
        ))}
        {signals.length > 0 && toolSignals.length > 0 && (
          <span aria-hidden className="h-3 w-px bg-border/60 mx-1" />
        )}
        {toolSignals.map((s) => (
          <ToolPip key={s.id} signal={s} />
        ))}
      </div>
    </div>
  )
}

function WorkingPip({ signal }: { signal: WorkingSignal }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span
        aria-hidden
        className={cn(
          'h-1.5 w-1.5 rounded-full shrink-0',
          signal.state === 'typing' && 'bg-live animate-pulse',
          signal.state === 'just-spoke' && 'bg-emerald-500',
          signal.state === 'waiting' && 'bg-muted-foreground/50',
        )}
      />
      <MetaSkillAvatar slug={signal.metaSkill} size="sm" />
      <span className="font-heading text-foreground/80">{signal.label}</span>
      <span className="font-mono text-[11px] text-muted-foreground/80">
        {signal.state === 'typing'
          ? 'typing…'
          : signal.state === 'just-spoke'
            ? signal.whenLabel ?? 'just now'
            : (signal.whenLabel ?? 'waiting')}
      </span>
    </span>
  )
}

function ToolPip({ signal }: { signal: ToolSignal }) {
  const running = signal.state === 'running'
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span
        aria-hidden
        className={cn(
          'h-1.5 w-1.5 rounded-full shrink-0',
          running ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500',
        )}
      />
      <Hammer
        size={11}
        weight="duotone"
        className={cn(
          'shrink-0',
          running ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground/70',
        )}
      />
      <span className="font-mono text-[11px] text-foreground/80">{signal.tool}</span>
      <span className="font-mono text-[11px] text-muted-foreground/80">
        {running
          ? signal.inputSummary !== undefined
            ? `${signal.inputSummary.slice(0, 32)}${signal.inputSummary.length > 32 ? '…' : ''}`
            : 'running…'
          : `returned ${signal.whenLabel ?? 'just now'}`}
      </span>
    </span>
  )
}

/** Derive a default signal set from the current stage's tracks. Tracks
 *  marked `inFlight` become 'typing'; others become 'just-spoke' with a
 *  fake editorial timestamp. */
export function deriveSignalsFromTracks(tracks: JourneyTrack[]): WorkingSignal[] {
  return tracks.map((t, i) => ({
    metaSkill: t.metaSkill,
    label: t.label,
    state: t.inFlight === true ? 'typing' : 'just-spoke',
    whenLabel: t.inFlight === true ? undefined : `${(i + 1) * 4}s ago`,
  }))
}

/** Adapter from live orchestration tool-call records to ToolSignal[].
 *  Recently-resolved calls linger as 'returned' so the user sees the
 *  result before they fade. Caller passes a cutoff (ms since resolved)
 *  to control fade behavior. */
export function deriveToolSignals(
  calls: ReadonlyArray<{
    tool: string
    taskId: string
    inputSummary?: string
    resultSummary?: string
    startedAt: number
    resolvedAt?: number
  }>,
  now: number = Date.now(),
  lingerMs: number = 8000,
): ToolSignal[] {
  return calls
    .filter((c) => c.resolvedAt === undefined || now - c.resolvedAt < lingerMs)
    .map((c) => {
      const running = c.resolvedAt === undefined
      const whenAgo = running ? undefined : `${Math.max(1, Math.floor((now - (c.resolvedAt ?? now)) / 1000))}s ago`
      return {
        id: c.taskId,
        tool: c.tool,
        inputSummary: c.inputSummary,
        state: running ? 'running' : 'returned',
        whenLabel: whenAgo,
      } as ToolSignal
    })
}
