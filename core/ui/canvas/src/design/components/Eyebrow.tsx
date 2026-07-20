// frontend/src/design/components/Eyebrow.tsx
//
// Small-caps section label. Rewritten as a Tailwind-utility primitive
// so it matches the canonical preset's typographic rhythm.
import type { ReactNode } from 'react'

export interface EyebrowProps {
  children: ReactNode
  tone?: string
}

export function Eyebrow({ children, tone }: EyebrowProps) {
  const style = tone !== undefined ? { color: tone } : undefined
  return (
    <div
      style={style}
      className="text-[10px] uppercase tracking-widest font-semibold text-muted-foreground"
    >
      {children}
    </div>
  )
}
