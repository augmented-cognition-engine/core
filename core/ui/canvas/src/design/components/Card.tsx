// frontend/src/design/components/Card.tsx
//
// Shim over canonical shadcn Card. Legacy variant + accent + interactive
// API preserved; canonical Card from @/design/shadcn/ui/card provides
// the surface treatment.
import type { ReactNode } from 'react'

import { Card as ShadcnCard } from '@/design/shadcn/ui/card'
import { cn } from '@/lib/utils'

export type CardVariant = 'default' | 'strong' | 'dim' | 'subtle'
export type CardPadding = 'none' | 'sm' | 'md' | 'lg'

export interface CardProps {
  children: ReactNode
  variant?: CardVariant
  padding?: CardPadding
  accent?: string
  elevated?: boolean
  interactive?: boolean
  className?: string
  dataTest?: string
}

const VARIANT_CLASS: Record<CardVariant, string> = {
  default: '',
  strong: 'bg-muted/40',
  dim: 'bg-muted/60',
  subtle: 'bg-muted/20',
}

const PADDING_CLASS: Record<CardPadding, string> = {
  none: 'p-0 py-0 gap-0',
  sm: 'p-3 py-3 gap-3',
  md: 'p-4 py-4 gap-4',
  lg: 'p-6 py-6 gap-6',
}

export function Card({
  children,
  variant = 'default',
  padding = 'md',
  accent,
  elevated = false,
  interactive = false,
  className,
  dataTest,
}: CardProps) {
  const accentStyle = accent !== undefined ? { borderLeftColor: accent, borderLeftWidth: '3px', borderLeftStyle: 'solid' as const } : undefined
  return (
    <ShadcnCard
      data-test={dataTest}
      style={accentStyle}
      className={cn(
        VARIANT_CLASS[variant],
        PADDING_CLASS[padding],
        elevated && 'shadow-md',
        interactive && 'transition-shadow hover:shadow-md cursor-pointer',
        className,
      )}
    >
      {children}
    </ShadcnCard>
  )
}
