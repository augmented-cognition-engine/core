// frontend/src/design/components/Pip.tsx
//
// Tailwind-utility port — a small colored dot.
export interface PipProps {
  tone?: string
  size?: 'xs' | 'sm' | 'md'
  ring?: boolean
  title?: string
}

const SIZE_CLASS = {
  xs: 'size-[5px]',
  sm: 'size-[7px]',
  md: 'size-[10px]',
} as const

export function Pip({ tone, size = 'sm', ring = false, title }: PipProps) {
  return (
    <span
      title={title}
      style={{ background: tone ?? 'oklch(0.556 0 0)' }}
      className={`inline-block rounded-full shrink-0 ${SIZE_CLASS[size]} ${ring ? 'ring-2 ring-background shadow-sm' : ''}`}
    />
  )
}
