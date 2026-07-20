// core/ui/canvas/src/design/components/SeverityFinding.tsx
//
// Tailwind-utility port. Severity-tinted left border + headline + meta.
import type { ReactNode } from 'react'

export type Severity = 'low' | 'medium' | 'high'

export interface SeverityFindingProps {
  severity: Severity
  headline: ReactNode
  detail?: ReactNode
  meta?: ReactNode
  dataTest?: string
}

const SEVERITY_BORDER: Record<Severity, string> = {
  low: 'border-l-chart-1',
  medium: 'border-l-chart-5',
  high: 'border-l-destructive',
}

const SEVERITY_TEXT: Record<Severity, string> = {
  low: 'text-chart-1',
  medium: 'text-chart-5',
  high: 'text-destructive',
}

export function SeverityFinding({ severity, headline, detail, meta, dataTest }: SeverityFindingProps) {
  return (
    <div
      data-test={dataTest}
      data-severity={severity}
      className={`pl-3 border-l-[3px] ${SEVERITY_BORDER[severity]} text-sm leading-normal`}
    >
      <div className="font-medium">{headline}</div>
      {detail !== undefined && (
        <div className="text-xs text-muted-foreground italic mt-1 leading-snug">{detail}</div>
      )}
      {meta !== undefined && (
        <div className={`text-[10px] uppercase tracking-wider font-semibold mt-1 ${SEVERITY_TEXT[severity]}`}>
          {meta}
        </div>
      )}
    </div>
  )
}
