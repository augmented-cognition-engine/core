// frontend/src/design/components/Chip.tsx
//
// Shim over canonical shadcn Badge. Legacy variant + tone API mapped to
// the canonical Badge variants.
import { forwardRef, type ReactNode } from 'react'

import { Badge } from '@/design/shadcn/ui/badge'
import { cn } from '@/lib/utils'

export type ChipVariant = 'subtle' | 'strong' | 'ghost'

export interface ChipProps {
  children: ReactNode
  variant?: ChipVariant
  tone?: string
  title?: string
  onClick?: () => void
  asButton?: boolean
  className?: string
}

const VARIANT_MAP: Record<ChipVariant, 'default' | 'secondary' | 'outline'> = {
  subtle: 'secondary',
  strong: 'default',
  ghost: 'outline',
}

export const Chip = forwardRef<HTMLElement, ChipProps>(function Chip(
  {
    children,
    variant = 'subtle',
    tone,
    title,
    onClick,
    asButton = false,
    className,
  },
  ref,
) {
  const interactive = asButton || onClick !== undefined
  const toneStyle = tone !== undefined && variant === 'strong'
    ? { backgroundColor: tone, borderColor: tone }
    : tone !== undefined && variant === 'subtle'
    ? { borderColor: tone }
    : undefined

  const badgeProps = {
    variant: VARIANT_MAP[variant],
    title,
    style: toneStyle,
    className: cn(interactive && 'cursor-pointer hover:opacity-80', className),
  }

  if (interactive) {
    return (
      <button
        ref={ref as React.Ref<HTMLButtonElement>}
        type="button"
        onClick={onClick}
        title={title}
        className="inline-flex"
      >
        <Badge {...badgeProps}>{children}</Badge>
      </button>
    )
  }
  return (
    <Badge {...badgeProps} ref={ref as React.Ref<HTMLSpanElement>}>{children}</Badge>
  )
})
