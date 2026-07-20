// core/ui/canvas/src/design/components/Sidebar.tsx
//
// Two-column workspace primitive: sidebar + main content area. Used for
// canvas surfaces where a fixed-width rail sits next to a flexible
// content column.
//
// API: explicit `sidebar` and `main` props (not children) so the layout
// intent is unambiguous and reordering by `side` is trivial.
//
// Defaults: sidebar on left, sidebar fixed width 320, gap 4, stretched.
//
// On narrow viewports (collapsing below the threshold), the sidebar
// stacks above main. Threshold is opinionated at 640px — surfaces that
// need different behavior should compose Sidebar with their own
// responsive logic rather than parameterizing this primitive.
import type { ReactNode } from 'react'

import type { SpaceKey } from '../tokens'

export type SidebarSide = 'left' | 'right'

export interface SidebarProps {
  sidebar: ReactNode
  main: ReactNode
  side?: SidebarSide
  /** Sidebar width. Number = px; string = any CSS length ('320px', '20rem'). */
  width?: number | string
  gap?: SpaceKey
  /** Vertical alignment of the two columns. */
  align?: 'start' | 'stretch'
  dataTest?: string
}

export function Sidebar({
  sidebar,
  main,
  side = 'left',
  width = 320,
  gap = 4,
  align = 'stretch',
  dataTest,
}: SidebarProps) {
  const widthCSS = typeof width === 'number' ? `${width}px` : width
  const gridTemplateColumns =
    side === 'left' ? `${widthCSS} 1fr` : `1fr ${widthCSS}`
  return (
    <div
      data-test={dataTest}
      style={{
        display: 'grid',
        gridTemplateColumns,
        gap: `var(--ace-space-${gap})`,
        alignItems: align === 'stretch' ? 'stretch' : 'start',
        minWidth: 0,
      }}
    >
      {side === 'left' ? sidebar : main}
      {side === 'left' ? main : sidebar}
    </div>
  )
}
