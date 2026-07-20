// core/ui/canvas/src/app/board/shapes.ts
//
// Custom tldraw shape types for the ACE board. Each lens contribution is
// a positioned shape on the 2D canvas; agents (Phase 4+) write into the
// same Yjs doc as participants, so a "contribution-note" is the same
// primitive whether a human or an agent dropped it.
//
// Two shape types:
//
//   contribution-note         landed or in-flight voice contribution
//   contribution-placeholder  ghosted lane for a voice that hasn't fired
//
// Both extend tldraw's TLBaseBoxShape so they get drag/resize/select
// for free. The custom shape utils live in ContributionNoteShape.tsx
// and ContributionPlaceholderShape.tsx.
import type { TLBaseShape } from 'tldraw'

export type ContributionNoteShape = TLBaseShape<
  'contribution-note',
  {
    w: number
    h: number
    lens: string
    speaker: string
    accent: string
    framing: string
    landedAt?: string
    inFlight?: boolean
    thinkingAbout?: string
  }
>

export type ContributionPlaceholderShape = TLBaseShape<
  'contribution-placeholder',
  {
    w: number
    h: number
    lens: string
    speaker: string
    accent: string
    hint: string
  }
>
