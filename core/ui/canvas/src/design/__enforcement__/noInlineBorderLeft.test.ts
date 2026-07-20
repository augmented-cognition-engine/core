// core/ui/canvas/src/design/__enforcement__/noInlineBorderLeft.test.ts
//
// Fails the build if any surface outside the design system uses inline
// `borderLeft:` in a JSX style prop. The five distinct semantics of
// left-edge accent (discipline identity, voice-in-rail, voice-addressing-
// you, voice-in-motion, severity rank) each have a named primitive that
// owns them. Inline borderLeft is by definition a regression.
//
// Allowlist: tldraw shape utils that legitimately receive runtime
// per-shape colors via className + borderLeftColor injection.
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { formatMatches, scanAllUiRoots } from './scanner'

const APP_ROOT = path.resolve(__dirname, '..', '..', 'app')

const ALLOWLIST = [
  // tldraw shape utils — runtime per-shape color injection via CSS class
  // is correct. The shape owns the visual pattern via the class, the
  // accent color is per-shape data.
  'board/ContributionNoteShape.tsx',
]

describe('design-system enforcement: no inline borderLeft outside design/', () => {
  it('finds no inline borderLeft in src/app/', () => {
    // Match: `borderLeft:` or `borderLeftColor:` in a JSX style context.
    // Word boundary at the start; colon required (object syntax).
    const pattern = /\bborderLeft(Color|Style|Width)?\s*:/
    const matches = scanAllUiRoots(APP_ROOT, pattern, {
      excludeFiles: ALLOWLIST,
    })
    expect(
      matches,
      `Inline borderLeft found outside design/. Use a partnership primitive ` +
        `(ContributionLane / VoiceCallout / AgentPresenceRow / SeverityFinding) ` +
        `or Card.accent instead.\n${formatMatches(matches)}`,
    ).toEqual([])
  })
})
