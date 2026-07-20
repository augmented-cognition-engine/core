// frontend/src/design/components/Tooltip.tsx
//
// Shim over canonical shadcn Tooltip. Preserves legacy content-prop API.
import type { ReactElement, ReactNode } from 'react'

import {
  Tooltip as ShadcnTooltip,
  TooltipContent,
  TooltipProvider as ShadcnTooltipProvider,
  TooltipTrigger,
} from '@/design/shadcn/ui/tooltip'

export interface TooltipProps {
  children: ReactElement
  content: ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  sideOffset?: number
  delayDuration?: number
}

export function Tooltip({
  children,
  content,
  side = 'top',
  sideOffset = 6,
  delayDuration = 500,
}: TooltipProps) {
  return (
    <ShadcnTooltip delayDuration={delayDuration}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side={side} sideOffset={sideOffset}>
        {content}
      </TooltipContent>
    </ShadcnTooltip>
  )
}

export function TooltipProvider({
  children,
  delayDuration = 500,
  skipDelayDuration = 200,
}: {
  children: ReactNode
  delayDuration?: number
  skipDelayDuration?: number
}) {
  return (
    <ShadcnTooltipProvider delayDuration={delayDuration} skipDelayDuration={skipDelayDuration}>
      {children}
    </ShadcnTooltipProvider>
  )
}
