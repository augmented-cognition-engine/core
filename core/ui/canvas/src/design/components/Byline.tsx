// frontend/src/design/components/Byline.tsx
//
// Italic role label rewritten as Tailwind utilities to match canonical
// preset typography.
export interface BylineProps {
  children: React.ReactNode
  size?: 'sm' | 'md' | 'lg'
}

const SIZE_CLASS = {
  sm: 'text-xs',
  md: 'text-sm',
  lg: 'text-base',
} as const

export function Byline({ children, size = 'md' }: BylineProps) {
  return (
    <span className={`italic text-muted-foreground leading-snug ${SIZE_CLASS[size]}`}>
      {children}
    </span>
  )
}
