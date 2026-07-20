// core/ui/canvas/src/design/__enforcement__/tokensContract.test.ts
//
// Enforces the contract documented in tokens.ts:
//
//   "Every Layer 2/3 role/semantic export here MUST be a `var(--ace-*)`
//    string referencing a CSS var that exists in tokens.css."
//
// Parses tokens.ts and tokens.css, extracts every --ace-* name referenced
// from each, and asserts that tokens.ts uses no names that aren't
// defined in tokens.css. Catches future drift the same day it lands.
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const DESIGN_ROOT = path.resolve(__dirname, '..')
const TOKENS_TS = path.join(DESIGN_ROOT, 'tokens.ts')
const TOKENS_CSS = path.join(DESIGN_ROOT, 'tokens.css')

function extractCssVarNames(css: string): Set<string> {
  // Match `--ace-foo-bar:` at the start of a definition.
  const defined = new Set<string>()
  const re = /(--ace-[a-z0-9-]+)\s*:/g
  let m: RegExpExecArray | null
  while ((m = re.exec(css)) !== null) {
    defined.add(m[1])
  }
  return defined
}

function extractTsVarReferences(ts: string): Set<string> {
  // Match `var(--ace-foo-bar)` references inside strings.
  const referenced = new Set<string>()
  const re = /var\(\s*(--ace-[a-z0-9-]+)\s*\)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(ts)) !== null) {
    referenced.add(m[1])
  }
  return referenced
}

describe('design-system enforcement: tokens.ts ↔ tokens.css contract', () => {
  it('every var(--ace-*) referenced in tokens.ts is defined in tokens.css', () => {
    const tsContent = fs.readFileSync(TOKENS_TS, 'utf-8')
    const cssContent = fs.readFileSync(TOKENS_CSS, 'utf-8')

    const defined = extractCssVarNames(cssContent)
    const referenced = extractTsVarReferences(tsContent)

    const undefinedRefs: string[] = []
    for (const ref of referenced) {
      if (!defined.has(ref)) undefinedRefs.push(ref)
    }

    expect(
      undefinedRefs.sort(),
      `tokens.ts references CSS variables that don't exist in tokens.css. ` +
        `Either add the definition to tokens.css or update tokens.ts. ` +
        `Missing: ${undefinedRefs.join(', ')}`,
    ).toEqual([])
  })

  it('tokens.css defines at least one --ace-* variable (sanity)', () => {
    const cssContent = fs.readFileSync(TOKENS_CSS, 'utf-8')
    const defined = extractCssVarNames(cssContent)
    expect(defined.size).toBeGreaterThan(50)
  })

  it('tokens.ts references at least one --ace-* variable (sanity)', () => {
    const tsContent = fs.readFileSync(TOKENS_TS, 'utf-8')
    const referenced = extractTsVarReferences(tsContent)
    expect(referenced.size).toBeGreaterThan(10)
  })
})
