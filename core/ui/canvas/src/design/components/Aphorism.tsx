// frontend/src/design/components/Aphorism.tsx
//
// Tailwind-utility port — italic synthesis lead.
export interface AphorismProps {
  children: React.ReactNode
  size?: 'md' | 'lg' | 'xl'
}

const SIZE_CLASS = {
  md: 'text-base leading-snug',
  lg: 'text-lg leading-snug',
  xl: 'text-2xl leading-tight',
} as const

export function Aphorism({ children, size = 'lg' }: AphorismProps) {
  return (
    <p className={`italic text-foreground m-0 ${SIZE_CLASS[size]}`}>{children}</p>
  )
}
