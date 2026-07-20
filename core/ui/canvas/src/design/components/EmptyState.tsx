// core/ui/canvas/src/design/components/EmptyState.tsx
//
// Tailwind-utility port — centered italic empty-state message.
import type { ReactNode } from 'react'

export interface EmptyStateProps {
  prompt?: string
  children?: ReactNode
  dataTest?: string
}

export function EmptyState({
  prompt = 'Tell me what we’re building together.',
  children,
  dataTest,
}: EmptyStateProps) {
  return (
    <div
      data-test={dataTest}
      className="flex flex-col items-center justify-center text-center py-12 px-6"
    >
      <p className="italic text-sm text-muted-foreground leading-snug max-w-md m-0">{prompt}</p>
      {children !== undefined && <div className="mt-3 text-xs text-muted-foreground">{children}</div>}
    </div>
  )
}
