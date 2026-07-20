// app/journey/PhaseIcon.tsx
//
// Canonical phase icon — one mapping from cognitive phase to a phosphor
// glyph at consistent size + weight. Eliminates the random unicode
// (⌖ ◯ ◇ ◆) drift across stage surfaces.
import {
  Circle,
  Diamond,
  DiamondsFour,
  ShieldCheck,
  Target,
} from '@phosphor-icons/react'
import type { ComponentType } from 'react'

import { cn } from '@/lib/utils'

import type { StagePhase } from '../../types/canvas'

interface PhaseIconProps {
  phase: StagePhase
  /** Render at the canonical size: sm (16) / default (20) / lg (24). */
  size?: 'sm' | 'default' | 'lg'
  /** When true, render the converged / committed variant (fill weight). */
  filled?: boolean
  className?: string
}

interface PhosphorComponent {
  (props: {
    size?: number
    weight?: 'regular' | 'fill' | 'bold' | 'duotone'
    className?: string
  }): JSX.Element
}

const COMPONENTS: Record<StagePhase, ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>> = {
  prep: Target as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  frame: Circle as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  prioritize: DiamondsFour as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  choose: Diamond as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  validate: DiamondsFour as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  allocate: Diamond as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  critique: ShieldCheck as unknown as ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
}

const SIZE_PX: Record<NonNullable<PhaseIconProps['size']>, number> = {
  sm: 14,
  default: 18,
  lg: 22,
}

export function PhaseIcon({ phase, size = 'default', filled = false, className }: PhaseIconProps) {
  const Icon = COMPONENTS[phase]
  return (
    <Icon
      size={SIZE_PX[size]}
      weight={filled ? 'fill' : 'regular'}
      className={cn('shrink-0', className)}
    />
  )
}

// Re-export type for callers that infer it via PhaseIcon usage.
export type { PhosphorComponent }
