// app/journey/MetadataChip.tsx
//
// A classification/orchestra chip with a built-in tooltip so the
// classification banner explains itself on hover. Each chip = a Badge
// wrapped in a Tooltip — never a dead pill.
import type { ReactNode } from 'react'

import { Badge } from '@/design/shadcn/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/design/shadcn/ui/tooltip'
import { cn } from '@/lib/utils'

interface MetadataChipProps {
  /** Visible label inside the chip. */
  label: string
  /** Tooltip head — bold first line. */
  tooltipTitle: string
  /** Tooltip body — concise description. */
  tooltipDescription?: ReactNode
  /** Optional list of matched signals or sub-items to show on hover. */
  tooltipList?: string[]
  /** Optional matched-list label, defaults to "matched". */
  tooltipListLabel?: string
  variant?: 'outline' | 'secondary' | 'ghost' | 'default'
  className?: string
}

export function MetadataChip({
  label,
  tooltipTitle,
  tooltipDescription,
  tooltipList,
  tooltipListLabel = 'matched signals',
  variant = 'outline',
  className,
}: MetadataChipProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant={variant}
          className={cn(
            'cursor-help transition-colors duration-200 hover:bg-muted',
            className,
          )}
        >
          {label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-[300px]">
        <div className="flex flex-col gap-1.5">
          <span className="font-semibold">{tooltipTitle}</span>
          {tooltipDescription !== undefined && (
            <span className="text-muted-foreground">{tooltipDescription}</span>
          )}
          {tooltipList !== undefined && tooltipList.length > 0 && (
            <div className="flex flex-col gap-0.5 pt-1">
              <span className="text-xs uppercase tracking-wide text-muted-foreground">
                {tooltipListLabel}
              </span>
              <span className="font-mono text-xs">
                {tooltipList.slice(0, 6).join(' · ')}
                {tooltipList.length > 6 && ` · +${tooltipList.length - 6}`}
              </span>
            </div>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  )
}
