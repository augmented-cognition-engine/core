// core/ui/canvas/src/app/journey/ReasoningForkSurface.tsx
//
// Forkable foresight — "paths not taken". When ACE branched a reasoning checkpoint and re-reasoned
// the tail under alternative lenses, this surfaces a proactive line that expands INLINE on the stage
// timeline into a branch comparison — each path's score + conclusion, the recommended one highlighted.
// The partnership thesis made literal: see how ACE reasoned, and how it might have. Design-system only.
import { useState } from 'react'
import { GitFork } from '@phosphor-icons/react'

import { AccentNote, Chip, Eyebrow, ProactiveLine, StatusBadge } from '@/design/components'
import { Separator } from '@/design/shadcn/ui/separator'

import type { JourneyForkBranch, JourneyForkTrace } from '@/types/canvas'

interface ReasoningForkSurfaceProps {
  /** Pre-computed comparison (demo / a cached run). Renders immediately when present. */
  trace?: JourneyForkTrace
  /** Live, on-demand compute — invoked on first expand (the fork runs N executor passes, so it fires
   *  only when the partner clicks 'compare'). Returns null when the run can't be reconstructed. */
  fetchTrace?: () => Promise<JourneyForkTrace | null>
}

function pct(score: number): string {
  return `${Math.round(Math.max(0, Math.min(1, score)) * 100)}`
}

/** One reasoning path — the baseline ('original') or a re-reasoned fork, the recommended one accented. */
function BranchRow({ branch, isBest }: { branch: JourneyForkBranch; isBest: boolean }) {
  const isOriginal = branch.label === 'original'
  const inner = (
    <div className="flex flex-col gap-1.5" data-test={`fork-branch-${branch.label}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Chip
          variant={isOriginal ? 'subtle' : 'strong'}
          title={isOriginal ? 'the path ACE took' : `re-reasoned under the ${branch.lens} lens`}
        >
          {isOriginal ? 'original' : branch.lens}
        </Chip>
        <StatusBadge label={`${pct(branch.score)} / 100`} dim={!isBest} />
        {isBest && <Eyebrow>recommended</Eyebrow>}
        {branch.capabilityDeltaScore !== undefined && (
          <span className="font-mono text-[10px] text-muted-foreground">
            capability {pct(branch.capabilityDeltaScore)}
          </span>
        )}
      </div>
      <p className="font-heading text-sm leading-snug text-muted-foreground">{branch.conclusion}</p>
    </div>
  )
  return isBest ? <AccentNote tone="success">{inner}</AccentNote> : <div className="px-1">{inner}</div>
}

/**
 * The fork surface attached to a stage. The proactive line is always visible (ACE volunteering that it
 * explored alternatives); the branch comparison expands inline on demand. One continuous artifact — no
 * panel swap (the "living/breathing whiteboard" direction).
 */
export function ReasoningForkSurface({ trace, fetchTrace }: ReasoningForkSurfaceProps) {
  const [open, setOpen] = useState(false)
  const [fetched, setFetched] = useState<JourneyForkTrace | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)

  const effective = trace ?? fetched

  const handleToggle = () => {
    const next = !open
    setOpen(next)
    // First expand with no pre-computed trace → compute on demand.
    if (next && trace === undefined && fetched === null && fetchTrace !== undefined && !loading) {
      setLoading(true)
      setFailed(false)
      void fetchTrace()
        .then((result) => {
          setFetched(result)
          if (result === null) setFailed(true)
        })
        .catch(() => setFailed(true))
        .finally(() => setLoading(false))
    }
  }

  // Before the fork is computed the count is unknown, so the proactive line only invites.
  const observation =
    effective != null
      ? `I branched my reasoning here and explored ${effective.forks.length} alternative path${effective.forks.length === 1 ? '' : 's'}.`
      : 'I could re-reason this from here under a different lens.'
  const offer =
    effective != null
      ? effective.recommendation === 'fork'
        ? 'one scores higher than the path I took.'
        : 'the path I took still ranks best.'
      : loading
        ? 'comparing the paths…'
        : 'compare the paths not taken.'

  const branches: JourneyForkBranch[] = effective != null ? [effective.original, ...effective.forks] : []

  return (
    <div className="flex flex-col gap-2 px-5 py-4" data-test="reasoning-fork-surface">
      <Separator />
      <div className="flex items-baseline justify-between gap-2 pt-2">
        <span className="inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide text-muted-foreground">
          <GitFork size={14} weight="duotone" />
          paths not taken
        </span>
        <Chip asButton onClick={handleToggle} title="compare the reasoning paths">
          {open ? 'hide' : 'compare →'}
        </Chip>
      </div>
      <ProactiveLine tone="offer" observation={observation} offer={offer}>
        {open ? (
          loading ? (
            <p className="font-mono text-xs text-muted-foreground" data-test="fork-loading">
              re-reasoning under alternative lenses…
            </p>
          ) : failed || effective == null ? (
            <p className="font-mono text-xs text-muted-foreground" data-test="fork-empty">
              no forkable checkpoint here.
            </p>
          ) : (
            <div className="flex flex-col gap-2" data-test="fork-comparison">
              {branches.map((b) => (
                <BranchRow key={b.label} branch={b} isBest={b.label === effective.best.label} />
              ))}
            </div>
          )
        ) : undefined}
      </ProactiveLine>
    </div>
  )
}
