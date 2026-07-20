// core/ui/canvas/src/app/ext/registry.test.ts
//
// Unit tests for the extension-UI seam's pure parts: discovery from a
// module record (the testable half of import.meta.glob), shape
// validation, deterministic ordering, and first-wins slot resolution.
// The master-posture test (a real extension registering through the
// seam) lives WITH the extension, next to its register module, so it
// ships and vanishes with the extension itself.
import { describe, expect, test } from 'vitest'

import {
  collectExtensions,
  isExtensionUI,
  resolveSlot,
  type ExtensionUI,
} from './registry'

const NavA = () => null
const NavB = () => null
const IntelB = () => null

function ext(name: string, rest: Partial<ExtensionUI> = {}): ExtensionUI {
  return { name, ...rest }
}

describe('isExtensionUI', () => {
  test('accepts a minimal valid shape', () => {
    expect(isExtensionUI({ name: 'sample' })).toBe(true)
  })

  test('rejects non-objects, missing/empty name, malformed lists', () => {
    expect(isExtensionUI(null)).toBe(false)
    expect(isExtensionUI('sample')).toBe(false)
    expect(isExtensionUI({})).toBe(false)
    expect(isExtensionUI({ name: '' })).toBe(false)
    expect(isExtensionUI({ name: 'x', routes: 'nope' })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: 'nope' })).toBe(false)
  })
})

describe('collectExtensions', () => {
  test('empty module record (no extensions present) → no extensions', () => {
    // The naked-canvas posture: import.meta.glob over an empty ext/
    // directory yields {} and the kernel runs with defaults only.
    expect(collectExtensions({})).toEqual([])
  })

  test('valid default exports are collected in sorted-path order', () => {
    const collected = collectExtensions({
      './zeta/register.tsx': { default: ext('zeta') },
      './alpha/register.tsx': { default: ext('alpha') },
    })
    expect(collected.map((e) => e.name)).toEqual(['alpha', 'zeta'])
  })

  test('modules without a valid ExtensionUI default are skipped', () => {
    const collected = collectExtensions({
      './bad-none/register.ts': {},
      './bad-shape/register.ts': { default: { routes: [] } },
      './bad-mod/register.ts': undefined,
      './good/register.tsx': { default: ext('good') },
    })
    expect(collected.map((e) => e.name)).toEqual(['good'])
  })
})

describe('resolveSlot', () => {
  test('no extensions → undefined (kernel default applies)', () => {
    expect(resolveSlot([], 'nav')).toBeUndefined()
    expect(resolveSlot([ext('a')], 'intel')).toBeUndefined()
  })

  test('first extension filling the slot wins; others still resolve', () => {
    const exts = [
      ext('a', { slots: { nav: NavA } }),
      ext('b', { slots: { nav: NavB, intel: IntelB } }),
    ]
    expect(resolveSlot(exts, 'nav')).toBe(NavA)
    expect(resolveSlot(exts, 'intel')).toBe(IntelB)
    expect(resolveSlot(exts, 'voice')).toBeUndefined()
  })
})
