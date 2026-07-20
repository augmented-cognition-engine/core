// core/ui/canvas/src/design/__enforcement__/noInlineStyleHex.test.ts
//
// Fails the build if any surface outside the design system uses hex
// color literals (`'#xxxxxx'`) or rgba() in inline JSX style props.
// Every color value should come from a token (`var(--ace-*)`) or a
// runtime-data accent passed in via props.
//
// What's allowed:
//   - `style={{ color: 'var(--ace-ink)' }}`     — token reference
//   - `style={{ background: accent }}`          — runtime data (variable)
// What's forbidden:
//   - `style={{ background: '#0070F3' }}`       — hex literal
//   - `style={{ borderColor: 'rgba(...)' }}`    — rgba literal
//
// Allowlist: surfaces that legitimately bridge to runtime per-shape
// color values via color-mix or template-string interpolation in
// design-system-approved patterns.
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { formatMatches, scanAllUiRoots } from './scanner'

const APP_ROOT = path.resolve(__dirname, '..', '..', 'app')

const ALLOWLIST: string[] = [
  // Fixtures are test/sample data, not UI surfaces. They legitimately
  // contain hex literals for discipline-accent contributions used to
  // exercise the canvas. The hex values themselves come from
  // disciplineIdentity.ts — ideally fixtures would import from there,
  // but inlining is acceptable for fixture data legibility.
  'fixtures/multiplayer.tsx',
]

// Extension roots are scanned too (scanAllUiRoots). Two sanctioned CLASSES of
// exception under any extension mount — pattern-based so the allowlist never
// names a specific extension:
//  - a theme DEFINITION is the token source — brand hexes live there by design;
//  - data-layer identity payloads (per-seat chip colors mirroring what the
//    shim serves at runtime — the runtime-injected-color precedent above).
//    TRACKED MIGRATION: the seat palette leans purple/violet; aligning it to
//    the chart tokens needs a >5-identity design decision first.
// Everything else in an extension's UI surface keeps full enforcement teeth.
const EXTENSION_ALLOWLIST_PATTERNS: RegExp[] = [
  /\/extensions\/[^/]+\/ui\/canvas\/theme\.ts$/,
  /\/extensions\/[^/]+\/ui\/canvas\/app\/data\/[^/]+\.ts$/,
]

describe('design-system enforcement: no inline color literals outside design/', () => {
  it('finds no hex color literals in src/app/', () => {
    // Match: a quoted hex literal of the form '#xxx' / '#xxxxxx' / '#xxxxxxxx'
    // (with possible whitespace before quotes) in JSX/TS files.
    const pattern = /['"`]#[0-9a-fA-F]{3,8}['"`]/
    const matches = scanAllUiRoots(APP_ROOT, pattern, { excludeFiles: ALLOWLIST, excludePatterns: EXTENSION_ALLOWLIST_PATTERNS })
    expect(
      matches,
      `Hex color literal found. Use a token (var(--ace-*)) or pass via prop.\n${formatMatches(matches)}`,
    ).toEqual([])
  })

  it('finds no rgba() literals in src/app/', () => {
    // Match: rgba(...) literal in JSX style. Allow data-driven runtime
    // template strings (e.g. `rgba(...${variable})`) via the allowlist.
    const pattern = /rgba\(\s*\d/
    const matches = scanAllUiRoots(APP_ROOT, pattern, { excludeFiles: ALLOWLIST, excludePatterns: EXTENSION_ALLOWLIST_PATTERNS })
    expect(
      matches,
      `rgba() literal found. Use a token or color-mix(in oklab, ...) with a token base.\n${formatMatches(matches)}`,
    ).toEqual([])
  })
})
