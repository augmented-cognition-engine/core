// app/journey/MetaSkillAvatar.tsx
//
// Small letter-avatar identifying which meta-intelligence is speaking on a
// track. Built on shadcn Avatar. Color is derived from the meta-skill slug
// so the same intelligence always renders the same hue across stages.
// Optional tooltip surfaces the intelligence's name + activation signals
// that matched the current task — making L3 self-nomination legible.
import { Avatar, AvatarFallback } from '@/design/shadcn/ui/avatar'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/design/shadcn/ui/tooltip'
import { cn } from '@/lib/utils'

interface MetaSkillAvatarProps {
  /** Full slug (e.g. 'creative_intelligence') or short label ('creative'). */
  slug: string
  size?: 'sm' | 'default' | 'lg'
  className?: string
  /** Optional: long-form display name for the tooltip. */
  fullName?: string
  /** Optional: activation signals that matched this task. */
  matchedSignals?: string[]
  /** Optional: tooltip-only description. */
  description?: string
}

const TONE_BY_SHORT: Record<string, string> = {
  strategic: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200',
  risk: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200',
  planning: 'bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200',
  communication: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  creative: 'bg-pink-100 text-pink-800 dark:bg-pink-950 dark:text-pink-200',
  coding: 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200',
  systems: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-950 dark:text-cyan-200',
  data: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200',
  research: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  evaluation: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200',
  memory: 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-200',
  gap: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-200',
  verification: 'bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-200',
  classifier: 'bg-muted text-muted-foreground',
}

export function MetaSkillAvatar({
  slug,
  size = 'sm',
  className,
  fullName,
  matchedSignals,
  description,
}: MetaSkillAvatarProps) {
  const short = slug.replace('_intelligence', '')
  const tone = TONE_BY_SHORT[short] ?? 'bg-muted text-muted-foreground'
  const initial = (short[0] ?? '?').toUpperCase()

  const avatar = (
    <Avatar size={size} className={className}>
      <AvatarFallback className={cn('font-mono text-xs font-semibold', tone)}>
        {initial}
      </AvatarFallback>
    </Avatar>
  )

  // Render tooltip only when we have something to show.
  const hasTooltip =
    fullName !== undefined ||
    description !== undefined ||
    (matchedSignals !== undefined && matchedSignals.length > 0)
  if (!hasTooltip) return avatar

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">{avatar}</span>
      </TooltipTrigger>
      <TooltipContent className="max-w-[280px]">
        <div className="flex flex-col gap-1.5">
          <span className="font-semibold">{fullName ?? short.replace(/_/g, ' ')}</span>
          {description !== undefined && (
            <span className="text-muted-foreground">{description}</span>
          )}
          {matchedSignals !== undefined && matchedSignals.length > 0 && (
            <div className="flex flex-col gap-0.5 pt-1">
              <span className="text-xs uppercase tracking-wide text-muted-foreground">
                matched signals
              </span>
              <span className="font-mono text-xs">
                {matchedSignals.slice(0, 6).join(' · ')}
                {matchedSignals.length > 6 && ` · +${matchedSignals.length - 6}`}
              </span>
            </div>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  )
}
