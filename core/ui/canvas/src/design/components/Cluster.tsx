// core/ui/canvas/src/design/components/Cluster.tsx
//
// Horizontal flex with wrap — for chips, tags, action rows, byline
// elements, anything that should sit on one line if it fits and wrap
// cleanly when it doesn't. The Every-Layout "cluster" primitive.
//
// Distinct from Stack(direction="horizontal"): Cluster always wraps,
// always center-baselines by default, and is opinionated about reading
// like a continuous row of small things rather than a structural
// horizontal layout.
import type { ReactNode } from 'react'

import type { SpaceKey } from '../tokens'

export type ClusterAlign = 'start' | 'center' | 'end' | 'baseline'
export type ClusterJustify = 'start' | 'center' | 'end' | 'between'

export interface ClusterProps {
  children: ReactNode
  gap?: SpaceKey
  align?: ClusterAlign
  justify?: ClusterJustify
  dataTest?: string
}

const ALIGN_MAP: Record<ClusterAlign, string> = {
  start: 'flex-start',
  center: 'center',
  end: 'flex-end',
  baseline: 'baseline',
}

const JUSTIFY_MAP: Record<ClusterJustify, string> = {
  start: 'flex-start',
  center: 'center',
  end: 'flex-end',
  between: 'space-between',
}

export function Cluster({
  children,
  gap = 2,
  align = 'center',
  justify = 'start',
  dataTest,
}: ClusterProps) {
  return (
    <div
      data-test={dataTest}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: `var(--ace-space-${gap})`,
        alignItems: ALIGN_MAP[align],
        justifyContent: JUSTIFY_MAP[justify],
      }}
    >
      {children}
    </div>
  )
}
