// frontend/src/design/components/Divider.tsx
//
// Shim over canonical shadcn Separator with legacy spacing API.
import { Separator } from '@/design/shadcn/ui/separator'

export interface DividerProps {
  variant?: 'default' | 'gold' | 'strong'
  spacingTop?: 'none' | 'sm' | 'md' | 'lg'
  spacingBottom?: 'none' | 'sm' | 'md' | 'lg'
}

const SPACE_CLASS = {
  none: '',
  sm: '2',
  md: '3',
  lg: '5',
} as const

export function Divider({
  variant = 'default',
  spacingTop = 'sm',
  spacingBottom = 'sm',
}: DividerProps) {
  const topClass = spacingTop === 'none' ? '' : `mt-${SPACE_CLASS[spacingTop]}`
  const bottomClass = spacingBottom === 'none' ? '' : `mb-${SPACE_CLASS[spacingBottom]}`
  return (
    <Separator
      className={`${topClass} ${bottomClass} ${variant === 'strong' ? 'bg-border' : ''}`}
    />
  )
}
