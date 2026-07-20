// frontend/src/design/components/Popover.tsx
//
// Shim over canonical shadcn Popover. Legacy `content`-prop API
// preserved; canonical primitives at @/design/shadcn/ui/popover.
import type { ReactElement, ReactNode } from 'react'

import {
  Popover as ShadcnPopover,
  PopoverContent,
  PopoverTrigger,
} from '@/design/shadcn/ui/popover'

export interface PopoverProps {
  children: ReactElement
  content: ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  align?: 'start' | 'center' | 'end'
  sideOffset?: number
  open?: boolean
  onOpenChange?: (open: boolean) => void
  width?: number | string
}

export function Popover({
  children,
  content,
  side = 'bottom',
  align = 'start',
  sideOffset = 6,
  open,
  onOpenChange,
  width,
}: PopoverProps) {
  const widthStyle = width !== undefined
    ? { width: typeof width === 'number' ? `${width}px` : width }
    : undefined
  return (
    <ShadcnPopover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent side={side} align={align} sideOffset={sideOffset} style={widthStyle}>
        {content}
      </PopoverContent>
    </ShadcnPopover>
  )
}
