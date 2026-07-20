// frontend/src/design/components/StatusBadge.tsx
//
// Shim over canonical shadcn Badge with the uppercase status-pill
// treatment baked in. Tone (color) preserved via inline style override.
import { Badge } from '@/design/shadcn/ui/badge'

export interface StatusBadgeProps {
  label: string
  tone?: string
  dim?: boolean
}

export function StatusBadge({ label, tone, dim = false }: StatusBadgeProps) {
  const useTone = !dim && tone !== undefined
  const style = useTone
    ? { color: tone, backgroundColor: `color-mix(in oklab, ${tone} 14%, transparent)`, borderColor: 'transparent' }
    : undefined
  return (
    <Badge
      variant={dim || tone === undefined ? 'secondary' : 'outline'}
      style={style}
      className="uppercase tracking-wider font-bold text-[10px] tabular-nums"
    >
      {label}
    </Badge>
  )
}
