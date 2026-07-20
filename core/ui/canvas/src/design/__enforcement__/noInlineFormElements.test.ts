// core/ui/canvas/src/design/__enforcement__/noInlineFormElements.test.ts
//
// Fails the build if any surface outside the design system uses inline
// lowercase JSX form elements (<input>, <textarea>, <select>, <button>).
// The design system ships typed primitives (Input, Textarea, Button,
// and pending Select / Tabs / Checkbox / Switch); surfaces compose
// those, never native HTML.
//
// Allowlist (none currently). New entries require a written justification
// in the comment above.
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { formatMatches, scanAllUiRoots } from './scanner'

const APP_ROOT = path.resolve(__dirname, '..', '..', 'app')

const ALLOWLIST: string[] = []

describe('design-system enforcement: no inline form elements outside design/', () => {
  it('finds no inline <input> in src/app/', () => {
    const pattern = /<input[\s>/]/
    const matches = scanAllUiRoots(APP_ROOT, pattern, { excludeFiles: ALLOWLIST })
    expect(
      matches,
      `Inline <input> found. Use <Input> from design/components/.\n${formatMatches(matches)}`,
    ).toEqual([])
  })

  it('finds no inline <textarea> in src/app/', () => {
    const pattern = /<textarea[\s>/]/
    const matches = scanAllUiRoots(APP_ROOT, pattern, { excludeFiles: ALLOWLIST })
    expect(
      matches,
      `Inline <textarea> found. Use <Textarea> from design/components/.\n${formatMatches(matches)}`,
    ).toEqual([])
  })

  it('finds no inline <select> in src/app/', () => {
    const pattern = /<select[\s>/]/
    const matches = scanAllUiRoots(APP_ROOT, pattern, { excludeFiles: ALLOWLIST })
    expect(
      matches,
      `Inline <select> found. Use <Select> from design/components/ (v1 pending Radix install).\n${formatMatches(matches)}`,
    ).toEqual([])
  })

  it('finds no inline <button> in src/app/', () => {
    const pattern = /<button[\s>/]/
    const matches = scanAllUiRoots(APP_ROOT, pattern, { excludeFiles: ALLOWLIST })
    expect(
      matches,
      `Inline <button> found. Use <Button> from design/components/.\n${formatMatches(matches)}`,
    ).toEqual([])
  })
})
