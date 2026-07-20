// core/ui/canvas/src/design/components/Grid.tsx
//
// CSS grid container. Three modes:
//   - `columns={N}`         → equal columns: repeat(N, 1fr)
//   - `columns="200px 1fr"` → raw grid-template-columns string
//   - `minColumnWidth={240}` → auto-fit responsive: repeat(auto-fit, minmax(240px, 1fr))
//
// Aesthetic-agnostic. No styling beyond layout. Use inside any surface.
import type { ReactNode } from 'react'

import type { SpaceKey } from '../tokens'

export interface GridProps {
  children: ReactNode
  /** Either a number (equal columns), a raw grid-template-columns string,
   *  or omitted in favor of `minColumnWidth`. */
  columns?: number | string
  /** If set, overrides `columns` with auto-fit + minmax for responsive
   *  card grids that reflow as the container resizes. */
  minColumnWidth?: number
  gap?: SpaceKey
  /** Vertical alignment of items in their grid cells. */
  align?: 'start' | 'center' | 'end' | 'stretch'
  dataTest?: string
}

export function Grid({
  children,
  columns,
  minColumnWidth,
  gap = 4,
  align = 'stretch',
  dataTest,
}: GridProps) {
  const gridTemplateColumns =
    minColumnWidth !== undefined
      ? `repeat(auto-fit, minmax(${minColumnWidth}px, 1fr))`
      : typeof columns === 'number'
        ? `repeat(${columns}, 1fr)`
        : typeof columns === 'string'
          ? columns
          : '1fr'
  return (
    <div
      data-test={dataTest}
      style={{
        display: 'grid',
        gridTemplateColumns,
        gap: `var(--ace-space-${gap})`,
        alignItems: align === 'stretch' ? 'stretch' : align === 'start' ? 'start' : align === 'end' ? 'end' : 'center',
        minWidth: 0,
      }}
    >
      {children}
    </div>
  )
}
