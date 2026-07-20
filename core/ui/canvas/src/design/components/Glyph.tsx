// frontend/src/design/components/Glyph.tsx
//
// Tailwind-utility port — discipline glyph in a tinted circle.
import { disciplineIdentity } from '../disciplineIdentity'

export interface GlyphProps {
  lens?: string
  glyph?: string
  tone?: string
  size?: 'sm' | 'md' | 'lg'
  title?: string
}

const SIZE_CLASS = {
  sm: 'size-[18px] text-[12px]',
  md: 'size-[22px] text-[14px]',
  lg: 'size-7 text-base',
} as const

export function Glyph({ lens, glyph, tone, size = 'md', title }: GlyphProps) {
  const identity = lens !== undefined ? disciplineIdentity(lens) : null
  const resolvedGlyph = glyph ?? identity?.glyph ?? '·'
  const resolvedTone = tone ?? identity?.color ?? 'oklch(0.556 0 0)'
  return (
    <span
      title={title ?? identity?.role}
      style={{
        background: `color-mix(in oklab, ${resolvedTone} 16%, transparent)`,
        color: resolvedTone,
      }}
      className={`inline-flex items-center justify-center rounded-full font-medium shrink-0 ${SIZE_CLASS[size]}`}
    >
      {resolvedGlyph}
    </span>
  )
}
