// core/ui/canvas/src/design/components/Stack.tsx
//
// Vertical or horizontal flex container. The most common layout
// primitive — anywhere a surface composes children with consistent
// spacing, Stack replaces `<div style={{ display: 'flex',
// flexDirection, gap }}>`.
//
// Aesthetic-agnostic: no colors, no borders, no shadows. Pure layout.
// Composes inside any surface (Card, Section, Panel, Modal).
//
// Defaults: vertical, gap 0, align stretch, justify start.
import type { ReactNode } from 'react'

import type { SpaceKey } from '../tokens'

export type StackDirection = 'vertical' | 'horizontal'
export type StackAlign = 'start' | 'center' | 'end' | 'stretch' | 'baseline'
export type StackJustify = 'start' | 'center' | 'end' | 'between' | 'around' | 'evenly'

export interface StackProps {
  children: ReactNode
  direction?: StackDirection
  gap?: SpaceKey
  align?: StackAlign
  justify?: StackJustify
  wrap?: boolean
  /** Render as inline-flex instead of flex. Useful for inline groupings. */
  inline?: boolean
  /** Forwarded as data attribute for testing. */
  dataTest?: string
}

const ALIGN_MAP: Record<StackAlign, string> = {
  start: 'flex-start',
  center: 'center',
  end: 'flex-end',
  stretch: 'stretch',
  baseline: 'baseline',
}

const JUSTIFY_MAP: Record<StackJustify, string> = {
  start: 'flex-start',
  center: 'center',
  end: 'flex-end',
  between: 'space-between',
  around: 'space-around',
  evenly: 'space-evenly',
}

export function Stack({
  children,
  direction = 'vertical',
  gap = 0,
  align = 'stretch',
  justify = 'start',
  wrap = false,
  inline = false,
  dataTest,
}: StackProps) {
  return (
    <div
      data-test={dataTest}
      style={{
        display: inline ? 'inline-flex' : 'flex',
        flexDirection: direction === 'vertical' ? 'column' : 'row',
        gap: `var(--ace-space-${gap})`,
        alignItems: ALIGN_MAP[align],
        justifyContent: JUSTIFY_MAP[justify],
        flexWrap: wrap ? 'wrap' : 'nowrap',
        minWidth: 0,
      }}
    >
      {children}
    </div>
  )
}
