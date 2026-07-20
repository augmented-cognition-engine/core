// frontend/src/design/components/Avatar.tsx
//
// Shim over canonical shadcn Avatar. Discipline identity (color + glyph)
// preserved via inline style for tint.
import { forwardRef } from 'react'

import { Avatar as ShadcnAvatar, AvatarFallback } from '@/design/shadcn/ui/avatar'
import { disciplineIdentity } from '../disciplineIdentity'

export interface AvatarProps {
  lens: string
  size?: 'sm' | 'md' | 'lg'
  withRing?: boolean
  title?: string
}

const SIZE_CLASS = {
  sm: 'size-[22px] text-[12px]',
  md: 'size-[26px] text-[14px]',
  lg: 'size-8 text-base',
} as const

export const Avatar = forwardRef<HTMLSpanElement, AvatarProps>(function Avatar(
  { lens, size = 'md', withRing = true, title },
  ref,
) {
  const id = disciplineIdentity(lens)
  return (
    <ShadcnAvatar
      ref={ref as React.Ref<HTMLSpanElement>}
      title={title ?? `${lens} — ${id.role}`}
      className={SIZE_CLASS[size]}
    >
      <AvatarFallback
        style={{
          background: `color-mix(in oklab, ${id.color} 20%, transparent)`,
          color: id.color,
          border: withRing ? `1px solid color-mix(in oklab, ${id.color} 50%, transparent)` : 'none',
        }}
        className="font-medium"
      >
        {id.glyph}
      </AvatarFallback>
    </ShadcnAvatar>
  )
})
