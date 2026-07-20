// core/ui/canvas/src/design/__enforcement__/noRadixImports.test.ts
//
// Fails the build on any direct `@radix-ui/...` import outside the
// design system. The design system owns the Radix wrap layer (Tooltip,
// Popover, Dialog, Menu, Select, Tabs, Checkbox, Switch). Surfaces
// import from `design/components/` — never the underlying Radix
// package — so the ACE API stays the single point of evolution.
//
// Allowlist: none. If a new Radix primitive is needed, add the wrapper
// to design/components/ first, then import the wrapper from app code.
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { formatMatches, scanAllUiRoots } from './scanner'

const APP_ROOT = path.resolve(__dirname, '..', '..', 'app')

const ALLOWLIST: string[] = []

describe('design-system enforcement: no direct @radix-ui imports in src/app/', () => {
  it('finds no @radix-ui imports in app code', () => {
    // Match: `from '@radix-ui/...'` or `import '@radix-ui/...'`.
    const pattern = /from\s+['"`]@radix-ui\/|import\s+['"`]@radix-ui\//
    const matches = scanAllUiRoots(APP_ROOT, pattern, { excludeFiles: ALLOWLIST })
    expect(
      matches,
      `Direct @radix-ui import in src/app/. Import the wrapper from design/components/ instead.\n${formatMatches(matches)}`,
    ).toEqual([])
  })
})
