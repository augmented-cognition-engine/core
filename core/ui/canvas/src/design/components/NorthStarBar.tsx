// frontend/src/design/components/NorthStarBar.tsx
//
// The gold-tinted "NORTH STAR · [goal] · OKR · [metric]" band that sits
// above the main deliberation scroll. Frames every turn in terms of the
// user's actual goal so the partner's work has gravity.
//
// Per the partnership thesis: if the user has no north-star set, the
// band shows a quiet placeholder rather than disappearing — context is
// always present even when empty.
import type { ReactNode } from 'react'

import { Eyebrow } from './Eyebrow'

export interface NorthStarBarProps {
  /** The user's north-star statement. Pass a placeholder string when
   *  unset; never null. */
  goal: ReactNode
  /** Optional OKR / metric line shown to the right of the goal. */
  okr?: ReactNode
}

export function NorthStarBar({ goal, okr }: NorthStarBarProps) {
  return (
    <div
      style={{
        padding: 'var(--ace-space-2) var(--ace-space-8)',
        background: 'var(--ace-north-star-bg)',
        borderBottom: '1px solid var(--ace-north-star-line)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--ace-space-3)',
        fontSize: 'var(--ace-text-base)',
        flex: '0 0 auto',
      }}
    >
      <Eyebrow tone="var(--ace-north-star-label)">North Star</Eyebrow>
      <span style={{ color: 'var(--ace-ink)', flex: '1 1 auto' }}>{goal}</span>
      {okr !== undefined && (
        <span style={{ color: 'var(--ace-ink-soft)', fontSize: 'var(--ace-text-sm)' }}>{okr}</span>
      )}
    </div>
  )
}
