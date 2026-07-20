// core/ui/canvas/src/design/components/ClosingBand.tsx
//
// Tailwind-utility port — full-width creed band, dark or light.
import type { ReactNode } from 'react'

import { Card, CardContent } from '@/design/shadcn/ui/card'

export interface ClosingBandProps {
  creed: ReactNode
  sub?: ReactNode
  actions?: ReactNode
  variant?: 'dark' | 'light'
  dataTest?: string
}

export function ClosingBand({ creed, sub, actions, variant = 'dark', dataTest }: ClosingBandProps) {
  const dark = variant === 'dark'
  return (
    <Card
      data-test={dataTest}
      className={dark ? 'bg-foreground text-background border-foreground' : 'bg-muted/30'}
    >
      <CardContent className="py-10 text-center space-y-3">
        <p className="text-2xl font-bold tracking-tight">{creed}</p>
        {sub !== undefined && (
          <p className={`text-sm max-w-2xl mx-auto ${dark ? 'text-background/70' : 'text-muted-foreground'}`}>
            {sub}
          </p>
        )}
        {actions !== undefined && (
          <div className="inline-flex items-center gap-3 pt-2">{actions}</div>
        )}
      </CardContent>
    </Card>
  )
}
