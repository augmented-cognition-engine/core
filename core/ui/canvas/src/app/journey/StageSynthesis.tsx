// app/journey/StageSynthesis.tsx
//
// L6 synthesis at the bottom of a stage. The cross-track implication
// chain — surfaces tensions and the leverage point per
// orchestrator/synthesizer.py.
//
// Tension and leverage rows render as quiet tinted callouts with icon
// prefixes so the partner's editorial overlay reads visually distinct
// from the bare track contributions above.
import { Lightning, Target } from '@phosphor-icons/react'

import { Separator } from '@/design/shadcn/ui/separator'
import { cn } from '@/lib/utils'

import type { JourneySynthesis } from '../../types/canvas'

interface StageSynthesisProps {
  synthesis: JourneySynthesis
  quiet?: boolean
}

export function StageSynthesis({ synthesis, quiet = false }: StageSynthesisProps) {
  return (
    <div className={cn('flex flex-col gap-2 px-5 py-4', quiet && 'opacity-70')}>
      <Separator />
      <span className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
        synthesis · L6
      </span>
      <p className="font-heading italic text-sm leading-snug text-foreground">
        {synthesis.implication}
      </p>

      {synthesis.tension !== undefined && (
        <div className="flex items-start gap-2.5 rounded-xl bg-amber-50/60 dark:bg-amber-950/30 px-3 py-2 border border-amber-200/60 dark:border-amber-900/40">
          <Lightning
            size={16}
            weight="duotone"
            className="shrink-0 mt-0.5 text-amber-600 dark:text-amber-400"
          />
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="font-sans text-[10px] uppercase tracking-widest font-semibold text-amber-700 dark:text-amber-400">
              tension
            </span>
            <p className="font-heading text-sm leading-snug text-foreground">
              {synthesis.tension}
            </p>
          </div>
        </div>
      )}

      {synthesis.leveragePoint !== undefined && (
        <div className="flex items-start gap-2.5 rounded-xl bg-foreground/[0.04] dark:bg-foreground/[0.05] px-3 py-2 border border-foreground/15">
          <Target
            size={16}
            weight="duotone"
            className="shrink-0 mt-0.5 text-brand"
          />
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="font-sans text-[10px] uppercase tracking-widest font-semibold text-brand">
              leverage
            </span>
            <p className="font-heading text-sm leading-snug text-foreground">
              {synthesis.leveragePoint}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
