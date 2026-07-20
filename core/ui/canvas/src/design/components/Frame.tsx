// core/ui/canvas/src/design/components/Frame.tsx
//
// Constrained content container — caps width, applies padding, optionally
// renders a named surface tone, optionally enforces an aspect ratio.
// Use it as the outermost container of a page or section to keep
// reading width comfortable.
//
// Surface tones map to the engineered-light role tokens:
//   - canvas    → --ace-surface-canvas   (#FAFAFA — page ground)
//   - raised    → --ace-surface-raised   (#FFFFFF — lifted card-like)
//   - recessed  → --ace-surface-recessed (#F4F4F4 — highlight band)
//   - tint      → --ace-surface-tint     (#E8F2FF — accent-tinted)
//   - none      → transparent
import type { ReactNode } from 'react'

import type { SpaceKey } from '../tokens'

export type FrameSurface = 'canvas' | 'raised' | 'recessed' | 'tint' | 'none'

export interface FrameProps {
  children: ReactNode
  /** Max content width. Number = px; string = any CSS length ('64ch', '1080px'). */
  maxWidth?: number | string
  padding?: SpaceKey
  surface?: FrameSurface
  /** Aspect ratio (e.g. '16/9', '1/1'). When set, the frame is sized by ratio. */
  aspect?: string
  /** Center horizontally within the parent. */
  center?: boolean
  dataTest?: string
}

const SURFACE_BG: Record<FrameSurface, string> = {
  canvas: 'var(--ace-surface-canvas)',
  raised: 'var(--ace-surface-raised)',
  recessed: 'var(--ace-surface-recessed)',
  tint: 'var(--ace-surface-tint)',
  none: 'transparent',
}

export function Frame({
  children,
  maxWidth,
  padding,
  surface = 'none',
  aspect,
  center = false,
  dataTest,
}: FrameProps) {
  const maxWidthCSS =
    maxWidth === undefined ? undefined : typeof maxWidth === 'number' ? `${maxWidth}px` : maxWidth
  return (
    <div
      data-test={dataTest}
      style={{
        background: SURFACE_BG[surface],
        padding: padding === undefined ? undefined : `var(--ace-space-${padding})`,
        maxWidth: maxWidthCSS,
        aspectRatio: aspect,
        margin: center ? '0 auto' : undefined,
        minWidth: 0,
      }}
    >
      {children}
    </div>
  )
}
