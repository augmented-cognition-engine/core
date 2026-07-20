// core/ui/canvas/src/design/__enforcement__/noLightTextOnLightCard.test.ts
//
// Fails the build if any element pairs a LIGHT-tinted surface with WHITE
// text on the same className — the recurring "invisible text" regression.
//
// The bug pattern: a card surface gets switched from a dark token
// (bg-primary) to a light tint (bg-brand/8, bg-anchor, bg-card …) but the
// text classes are left as `text-primary-foreground` (white). On the new
// light surface the text vanishes. It has bitten Roadmap, Brief Composer,
// Decisions, Tool Matrix, Personalization, and Frameworks.
//
// The rule: on a light surface, text must be dark (`text-foreground` /
// `text-muted-foreground` / `text-brand`). `text-primary-foreground`
// (white) is ONLY valid on `bg-primary` (the dark CTA surface).
//
// Scope/limitation: this catches the combo when both classes sit on the
// SAME element (the common direct authoring mistake). It cannot see white
// text that *inherits* a light background from a parent element across
// lines — that case is guarded by review + the visual screenshots. Keeping
// the two on one line is the cheap, reliable signal.
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { formatMatches, scanAllUiRoots } from './scanner'

const APP_ROOT = path.resolve(__dirname, '..', '..', 'app')

// A line that contains BOTH a light-tinted background AND a white-text
// token. Two lookaheads = unordered AND on one line.
//   light bg : bg-anchor | bg-card | bg-background | bg-brand/* | bg-success/* | bg-live/*
//   white tx : text-primary-foreground | text-white | text-background
// bg-primary is intentionally NOT a light surface — `bg-primary
// text-primary-foreground` (dark CTA) is the correct, allowed pairing.
const PATTERN =
  /(?=.*(?:bg-(?:anchor|card|background)\b|bg-(?:brand|success|live)\/))(?=.*\btext-(?:primary-foreground|white|background)\b)/

describe('design-system enforcement: no white text on a light card', () => {
  it('finds no light-surface + white-text combo in src/app/', () => {
    const matches = scanAllUiRoots(APP_ROOT, PATTERN)
    expect(
      matches,
      `White text on a light surface (invisible text). On a light card use ` +
        `text-foreground / text-muted-foreground / text-brand. ` +
        `text-primary-foreground is only valid on bg-primary.\n${formatMatches(matches)}`,
    ).toEqual([])
  })
})
