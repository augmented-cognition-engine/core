// core/ui/canvas/src/design/components/AccentNote.tsx
//
// Shim over canonical shadcn Alert. Tone preserved via inline left
// border style; label rendered as AlertTitle.
import type { ReactNode } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/design/shadcn/ui/alert'

export type AccentNoteTone = 'neutral' | 'accent' | 'success' | 'warning' | 'voice-accent'

export interface AccentNoteProps {
  label?: ReactNode
  children: ReactNode
  tone?: AccentNoteTone
  dataTest?: string
}

const TONE_COLOR: Record<AccentNoteTone, string> = {
  neutral: 'hsl(0 0% 50%)',
  accent: 'oklch(0.457 0.24 277.023)',
  success: 'oklch(0.6 0.18 145)',
  warning: 'oklch(0.7 0.15 65)',
  'voice-accent': 'oklch(0.457 0.24 277.023)',
}

export function AccentNote({ label, children, tone = 'neutral', dataTest }: AccentNoteProps) {
  return (
    <Alert
      data-test={dataTest}
      style={{ borderLeftWidth: '3px', borderLeftColor: TONE_COLOR[tone] }}
    >
      {label !== undefined && <AlertTitle>{label}</AlertTitle>}
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  )
}
