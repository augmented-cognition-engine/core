// core/ui/canvas/src/design/__enforcement__/noEmojiInJsx.test.ts
//
// Fails the build on emoji characters in src/app/. Per the design
// system principles (and the voice style guide), ACE never uses emoji
// — no ✨, no 🤖, no celebratory 🎉. Discipline identity comes from
// custom Glyph entries; informational marks come from semantic
// components, not emoji.
//
// Allowlist: tldraw shapes / fixtures (test data legitimately uses
// emoji to mock external user input). None currently.
//
// Detected: all color-emoji ranges (the slop attractors) plus specific
// known-bad symbols. Excludes typographic glyphs (◆ ◐ ✦ ✓ ✗ → ⌖) that
// ACE legitimately uses for diamonds, arrows, progress markers, etc.
// in surfaces like Topbar progress strip and ProactivePanel eyebrow.
// Those should arguably migrate to <Glyph>, but they're not "emoji
// slop" in the AI-program sense.
//
// Caught ranges:
//   U+1F300–U+1FAFF  Color emoji (🤖 🎉 🚀 💡 📊 🔥 ✨ ...)
//   U+2728           ✨ sparkle (the canonical AI tell, outside F-range)
//   U+2705           ✅ heavy white check (status slop tell)
//   U+274C           ❌ heavy cross (status slop tell)
//   U+26A0           ⚠  warning sign (status slop tell)
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { formatMatches, scanAllUiRoots } from './scanner'

const APP_ROOT = path.resolve(__dirname, '..', '..', 'app')

const ALLOWLIST: string[] = []

describe('design-system enforcement: no emoji in src/app/', () => {
  it('finds no emoji characters in app JSX/TS', () => {
    const pattern =
      /[\u{1F300}-\u{1FAFF}]|[\u{2728}\u{2705}\u{274C}\u{26A0}]/u
    const matches = scanAllUiRoots(APP_ROOT, pattern, { excludeFiles: ALLOWLIST })
    expect(
      matches,
      `Emoji character found in src/app/. Use a Glyph or a semantic primitive instead.\n${formatMatches(matches)}`,
    ).toEqual([])
  })
})
