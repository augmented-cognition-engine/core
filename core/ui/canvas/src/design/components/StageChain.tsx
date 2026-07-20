// core/ui/canvas/src/design/components/StageChain.tsx
//
// Tailwind-utility port — horizontal numbered stages with arrow connectors.
import { Fragment, type KeyboardEvent, type ReactNode } from 'react'

export interface StageChainItem {
  id: string
  num: ReactNode
  name: ReactNode
  phase?: ReactNode
}

export interface StageChainProps {
  items: readonly StageChainItem[]
  activeId?: string
  openIds?: readonly string[]
  onPick?: (id: string) => void
  label?: ReactNode
  dataTest?: string
}

function StageNode({
  item, active, done, onPick,
}: {
  item: StageChainItem
  active: boolean
  done: boolean
  onPick?: (id: string) => void
}) {
  const interactive = onPick !== undefined
  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!interactive) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onPick!(item.id)
    }
  }
  const cls = done
    ? 'border-chart-1 bg-chart-1/10 text-foreground'
    : active
    ? 'border-primary bg-primary/10 text-foreground'
    : 'border-border bg-background text-muted-foreground'
  return (
    <div
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? () => onPick!(item.id) : undefined}
      onKeyDown={handleKeyDown}
      className={`inline-flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${cls} ${interactive ? 'cursor-pointer hover:shadow-sm transition-shadow' : ''}`}
    >
      <span className="inline-flex items-center justify-center size-5 rounded-full bg-background border text-[10px] font-bold">
        {done ? '✓' : item.num}
      </span>
      <span className="font-medium">{item.name}</span>
      {item.phase !== undefined && (
        <span className="text-muted-foreground text-[10px] uppercase tracking-wide">· {item.phase}</span>
      )}
    </div>
  )
}

export function StageChain({ items, activeId, openIds, onPick, label, dataTest }: StageChainProps) {
  const openSet = new Set(openIds ?? [])
  return (
    <div data-test={dataTest} className="flex items-center gap-2 flex-wrap">
      {label !== undefined && (
        <span className="text-[10px] uppercase tracking-widest font-semibold text-muted-foreground mr-2">
          {label}
        </span>
      )}
      {items.map((item, i) => (
        <Fragment key={item.id}>
          {i > 0 && <span aria-hidden className="text-muted-foreground">→</span>}
          <StageNode
            item={item}
            active={activeId === item.id}
            done={openSet.has(item.id)}
            onPick={onPick}
          />
        </Fragment>
      ))}
    </div>
  )
}
