// core/ui/canvas/src/app/ext/registry.test.ts
//
// Unit tests for the extension-UI seam's pure parts: discovery from a
// module record (the testable half of import.meta.glob), shape
// validation, deterministic ordering, and first-wins slot resolution.
// The master-posture test (a real extension registering through the
// seam) lives WITH the extension, next to its register module, so it
// ships and vanishes with the extension itself.
import { Component, createElement, forwardRef, lazy, memo } from 'react'
import { describe, expect, test } from 'vitest'

import {
  collectNavItems,
  collectRoutes,
  collectExtensions,
  installedSolutions,
  isExtensionUI,
  resolveSlot,
  type ExtensionUI,
} from './registry'

const NavA = () => null
const NavB = () => null
const IntelB = () => null
const Icon = () => null

function ext(name: string, rest: Partial<ExtensionUI> = {}): ExtensionUI {
  return { name, ...rest }
}

function withRoutePath(path: string) {
  return { name: 'x', routes: [{ path, element: createElement('div') }] }
}

function withNavHref(href: string) {
  return { name: 'x', navItems: [{ href, label: 'Bad', icon: Icon }] }
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
    expect(isExtensionUI({ name: 'x', routes: [null] })).toBe(false)
    expect(isExtensionUI({ name: 'x', routes: [{}] })).toBe(false)
    expect(isExtensionUI({
      name: 'x',
      routes: [{ path: 'relative', element: createElement('div') }],
    })).toBe(false)
    expect(isExtensionUI({
      name: 'x',
      routes: [{ path: '//host/path', element: createElement('div') }],
    })).toBe(false)
    expect(isExtensionUI({
      name: 'x',
      routes: [{ path: '/space ', element: createElement('div') }],
    })).toBe(false)
    expect(isExtensionUI({
      name: 'x',
      routes: [{ path: '/bad', element: {} }],
    })).toBe(false)
    expect(isExtensionUI({
      name: 'x',
      routes: [
        { path: '/same', element: createElement('div') },
        { path: '/same', element: createElement('span') },
      ],
    })).toBe(false)
    expect(isExtensionUI({ name: 'x', navItems: 'nope' })).toBe(false)
    expect(isExtensionUI({ name: 'x', navItems: [{ href: 'relative', label: 'Bad', icon: Icon }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', navItems: [{ href: '/space ', label: 'Bad', icon: Icon }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', navItems: [{ href: '/bad', label: '', icon: Icon }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', navItems: [{ href: '/bad', label: 'Bad' }] })).toBe(false)
    expect(isExtensionUI({
      name: 'x',
      navItems: [{ href: '/bad', label: 'Bad', icon: {} }],
    })).toBe(false)
    expect(isExtensionUI({
      name: 'x',
      navItems: [
        { href: '/same', label: 'One', icon: Icon },
        { href: '/same', label: 'Two', icon: Icon },
      ],
    })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: 'nope' })).toBe(false)
  })

  test('accepts ordinary, forwardRef, and memo component icons', () => {
    const ForwardIcon = forwardRef<SVGSVGElement>(() => createElement('svg'))
    const MemoIcon = memo(Icon)
    for (const icon of [Icon, ForwardIcon, MemoIcon]) {
      expect(isExtensionUI({
        name: 'x',
        navItems: [{ href: '/valid', label: 'Valid', icon }],
      })).toBe(true)
    }
  })

  test('accepts canonical bounded literal same-origin paths', () => {
    for (const path of ['/', '/atrium', '/atrium/code', '/a/b/c-d_e.f']) {
      expect(isExtensionUI(withRoutePath(path))).toBe(true)
      expect(isExtensionUI(withNavHref(path))).toBe(true)
    }
  })

  // A raw control character (codepoint 1) standing in for the whole C0/DEL
  // class -- built via fromCharCode rather than a literal escape, which this
  // file's toolchain has shown itself prone to mis-transcribing.
  const CONTROL_CHARACTER = String.fromCharCode(1)

  test.each([
    ['wildcard', '/atrium/*'],
    ['parameter', '/atrium/:id'],
    ['query string', '/atrium/code?x=1'],
    ['hash fragment', '/atrium/code#section'],
    ['backslash', '/atrium\\code'],
    ['dot-segment (parent)', '/atrium/../secret'],
    ['dot-segment (self)', '/atrium/./code'],
    ['bare dot-segment', '/..'],
    ['protocol-relative', '//evil.example.com/x'],
    ['embedded control character', `/atrium/${CONTROL_CHARACTER}code`],
    ['embedded space', '/atrium code'],
    ['trailing slash alias', '/atrium/code/'],
    ['empty string', ''],
    ['relative (no leading slash)', 'atrium/code'],
    ['over-length', `/${'a'.repeat(201)}`],
    ['repeated slash', '/atrium//code'],
    ['percent-encoded dot (lowercase)', '/atrium/%2e%2e/secret'],
    ['percent-encoded dot (uppercase)', '/atrium/%2E%2E/secret'],
    ['percent-encoded traversal segment', '/atrium/%2e%2e'],
    ['percent-encoded slash', '/atrium%2fcode'],
    ['percent-encoded backslash', '/atrium%5ccode'],
    ['percent-encoded query', '/atrium/code%3fx=1'],
    ['percent-encoded hash', '/atrium/code%23section'],
    ['percent-encoded control character', '/atrium/%00code'],
  ])('rejects a route path that is %s', (_label, path) => {
    expect(isExtensionUI(withRoutePath(path))).toBe(false)
  })

  test.each([
    ['wildcard', '/atrium/*'],
    ['parameter', '/atrium/:id'],
    ['query string', '/atrium/code?x=1'],
    ['hash fragment', '/atrium/code#section'],
    ['backslash', '/atrium\\code'],
    ['dot-segment (parent)', '/atrium/../secret'],
    ['protocol-relative', '//evil.example.com/x'],
    ['embedded control character', `/atrium/${CONTROL_CHARACTER}code`],
    ['trailing slash alias', '/atrium/code/'],
    ['repeated slash', '/atrium//code'],
    ['percent-encoded dot (lowercase)', '/atrium/%2e%2e/secret'],
    ['percent-encoded dot (uppercase)', '/atrium/%2E%2E/secret'],
    ['percent-encoded traversal segment', '/atrium/%2e%2e'],
    ['percent-encoded slash', '/atrium%2fcode'],
    ['percent-encoded backslash', '/atrium%5ccode'],
    ['percent-encoded query', '/atrium/code%3fx=1'],
    ['percent-encoded hash', '/atrium/code%23section'],
    ['percent-encoded control character', '/atrium/%00code'],
  ])('rejects a nav href that is %s', (_label, href) => {
    expect(isExtensionUI(withNavHref(href))).toBe(false)
  })
})

describe('isExtensionUI name and label bounds', () => {
  test('rejects an untrimmed or oversized registration name', () => {
    expect(isExtensionUI({ name: ' x' })).toBe(false)
    expect(isExtensionUI({ name: 'x ' })).toBe(false)
    expect(isExtensionUI({ name: ' x ' })).toBe(false)
    expect(isExtensionUI({ name: 'a'.repeat(101) })).toBe(false)
  })

  test('accepts a name at the length ceiling', () => {
    expect(isExtensionUI({ name: 'a'.repeat(100) })).toBe(true)
  })

  test('rejects an untrimmed or oversized nav label', () => {
    expect(isExtensionUI(withNavHref('/valid'))).toBe(true)
    expect(isExtensionUI({
      name: 'x',
      navItems: [{ href: '/valid', label: ' Bad', icon: Icon }],
    })).toBe(false)
    expect(isExtensionUI({
      name: 'x',
      navItems: [{ href: '/valid', label: 'Bad ', icon: Icon }],
    })).toBe(false)
    expect(isExtensionUI({
      name: 'x',
      navItems: [{ href: '/valid', label: 'a'.repeat(101), icon: Icon }],
    })).toBe(false)
  })

  test('rejects a route/nav/theme list past its explicit maximum', () => {
    const manyRoutes = Array.from({ length: 51 }, (_, i) => ({
      path: `/r${i}`,
      element: createElement('div'),
    }))
    expect(isExtensionUI({ name: 'x', routes: manyRoutes })).toBe(false)

    const manyNavItems = Array.from({ length: 51 }, (_, i) => ({
      href: `/n${i}`,
      label: `N${i}`,
      icon: Icon,
    }))
    expect(isExtensionUI({ name: 'x', navItems: manyNavItems })).toBe(false)

    const manyThemes = Array.from({ length: 21 }, (_, i) => ({
      id: `t${i}`,
      label: `T${i}`,
    }))
    expect(isExtensionUI({ name: 'x', themes: manyThemes })).toBe(false)
  })
})

describe('isExtensionUI slot validation', () => {
  test('rejects a slots value that is not a plain exact-key object', () => {
    expect(isExtensionUI({ name: 'x', slots: null })).toBe(false)
    expect(isExtensionUI({ name: 'x', slots: [] })).toBe(false)
    expect(isExtensionUI({ name: 'x', slots: 'nav' })).toBe(false)
    expect(isExtensionUI({ name: 'x', slots: 42 })).toBe(false)
    expect(isExtensionUI({ name: 'x', slots: { unknownSlot: NavA } })).toBe(false)
  })

  test('rejects a supported slot filled with a non-component value', () => {
    expect(isExtensionUI({ name: 'x', slots: { nav: {} } })).toBe(false)
    expect(isExtensionUI({ name: 'x', slots: { nav: 'NavComponent' } })).toBe(false)
    expect(isExtensionUI({ name: 'x', slots: { nav: 42 } })).toBe(false)
    expect(isExtensionUI({ name: 'x', slots: { nav: null } })).toBe(false)
  })

  test('accepts function, class, forwardRef, memo, and lazy components in every supported slot', () => {
    class ClassNav extends Component {
      render() {
        return null
      }
    }
    const ForwardNav = forwardRef<HTMLDivElement>(() => createElement('div'))
    const MemoNav = memo(NavA)
    const LazyNav = lazy(async () => ({ default: NavA }))

    for (const component of [NavA, ClassNav, ForwardNav, MemoNav, LazyNav]) {
      for (const slot of ['nav', 'intel', 'voice'] as const) {
        expect(isExtensionUI({ name: 'x', slots: { [slot]: component } })).toBe(true)
      }
    }
  })

  test('preserves first-owner slot resolution', () => {
    const exts = [
      ext('a', { slots: { nav: NavA } }),
      ext('b', { slots: { nav: NavB, intel: IntelB } }),
    ]
    expect(resolveSlot(exts, 'nav')).toBe(NavA)
    expect(resolveSlot(exts, 'intel')).toBe(IntelB)
  })
})

describe('isExtensionUI theme validation', () => {
  test('accepts a minimal valid theme and one with bounded tokens', () => {
    expect(isExtensionUI({ name: 'x', themes: [{ id: 'brand', label: 'Brand' }] })).toBe(true)
    expect(isExtensionUI({
      name: 'x',
      themes: [{ id: 'brand', label: 'Brand', tokens: { 'brand-bg': 'white' } }],
    })).toBe(true)
  })

  test('rejects a malformed theme entry', () => {
    expect(isExtensionUI({ name: 'x', themes: [null] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [[]] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: ['brand'] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [{ id: '', label: 'Brand' }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [{ id: ' brand ', label: 'Brand' }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [{ id: 'brand', label: '' }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [{ id: 'brand' }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [{ id: 'a'.repeat(101), label: 'Brand' }] })).toBe(false)
  })

  test.each(['__proto__', 'prototype', 'constructor'])(
    'rejects an unsafe object-property theme id: %s',
    (id) => {
      expect(isExtensionUI({ name: 'x', themes: [{ id, label: 'Brand' }] })).toBe(false)
    },
  )

  test('rejects malformed theme tokens', () => {
    expect(isExtensionUI({ name: 'x', themes: [{ id: 'a', label: 'A', tokens: null }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [{ id: 'a', label: 'A', tokens: [] }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [{ id: 'a', label: 'A', tokens: { bg: 1 } }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [{ id: 'a', label: 'A', tokens: { bg: '' } }] })).toBe(false)
    expect(isExtensionUI({ name: 'x', themes: [{ id: 'a', label: 'A', tokens: { ' bg': 'white' } }] })).toBe(false)
    // A computed key is required here: `{ __proto__: v }` in an object literal
    // sets the prototype rather than creating an own "__proto__" property.
    expect(isExtensionUI({
      name: 'x',
      themes: [{ id: 'a', label: 'A', tokens: { ['__proto__']: 'white' } }],
    })).toBe(false)
  })

  test('rejects duplicate theme ids and an excessive theme count', () => {
    expect(isExtensionUI({
      name: 'x',
      themes: [{ id: 'a', label: 'A' }, { id: 'a', label: 'A2' }],
    })).toBe(false)
    const many = Array.from({ length: 21 }, (_, i) => ({ id: `t${i}`, label: `T${i}` }))
    expect(isExtensionUI({ name: 'x', themes: many })).toBe(false)
  })

  test('a malformed registration is skipped while a later valid registration still collects', () => {
    const collected = collectExtensions({
      './bad-theme/register.ts': {
        default: ext('bad-theme', { themes: [{ id: '__proto__', label: 'Evil' }] }),
      },
      './good-theme/register.ts': {
        default: ext('good-theme', { themes: [{ id: 'good', label: 'Good' }] }),
      },
    })
    expect(collected.map((e) => e.name)).toEqual(['good-theme'])
  })
})

describe('collectExtensions', () => {
  test('empty module record (no extensions present) → no extensions', () => {
    // The naked-canvas posture: import.meta.glob over an empty ext/
    // directory yields no external extensions. Installed public solutions are
    // discovered by the separate solutions glob.
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

describe('collectRoutes', () => {
  test('keeps deterministic contribution order and rejects later duplicate paths', () => {
    const first = { path: '/first', element: createElement('div', { id: 'first' }) }
    const owned = { path: '/owned', element: createElement('div', { id: 'owner' }) }
    const duplicate = { path: '/owned', element: createElement('div', { id: 'shadow' }) }
    const last = { path: '/last', element: createElement('div', { id: 'last' }) }

    expect(collectRoutes([
      ext('installed', { routes: [first, owned] }),
      ext('external', { routes: [duplicate, last] }),
    ])).toEqual([first, owned, last])
  })

  test('rejects contribution paths reserved by the kernel host', () => {
    const homeCollision = { path: '/atrium', element: createElement('div') }
    const boardCollision = { path: '/board', element: createElement('div') }
    const valid = { path: '/solution', element: createElement('div') }

    expect(collectRoutes([
      ext('installed', { routes: [homeCollision, boardCollision, valid] }),
    ], ['/atrium', '/board'])).toEqual([valid])
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

describe('collectNavItems', () => {
  test('keeps deterministic contribution order and rejects later duplicate hrefs', () => {
    const first = { href: '/first', label: 'First', icon: Icon }
    const owned = { href: '/owned', label: 'Owner', icon: Icon }
    const duplicate = { href: '/owned', label: 'Shadow', icon: Icon }
    const last = { href: '/last', label: 'Last', icon: Icon }

    expect(collectNavItems([
      ext('installed', { navItems: [first, owned] }),
      ext('external', { navItems: [duplicate, last] }),
    ])).toEqual([first, owned, last])
  })

  test('rejects contributions that collide with kernel-owned navigation', () => {
    const surfaceCollision = { href: '/atrium', label: 'Shadow', icon: Icon }
    const downstreamCollision = { href: '/board', label: 'Shadow board', icon: Icon }
    const valid = { href: '/solution', label: 'Solution', icon: Icon }

    expect(collectNavItems([
      ext('installed', { navItems: [surfaceCollision, downstreamCollision, valid] }),
    ], ['/atrium', '/board'])).toEqual([valid])
  })
})

describe('host route/nav reservation is exact-match only', () => {
  // Reservation is a literal Set.has check (see collectRoutes/collectNavItems
  // above), never a prefix or glob match. A host that reserves the generic
  // '/atrium' surface — or even writes a glob-looking '/atrium/*' literal —
  // must not shadow an installed solution's more specific '/atrium/code'.
  test('installed /atrium/code route survives generic "/atrium" and "/atrium/*" reservations', () => {
    expect(collectRoutes(installedSolutions, ['/atrium']).map((r) => r.path))
      .toContain('/atrium/code')
    expect(collectRoutes(installedSolutions, ['/atrium/*']).map((r) => r.path))
      .toContain('/atrium/code')
  })

  test('installed /atrium/code nav item survives generic "/atrium" and "/atrium/*" reservations', () => {
    expect(collectNavItems(installedSolutions, ['/atrium']).map((i) => i.href))
      .toContain('/atrium/code')
    expect(collectNavItems(installedSolutions, ['/atrium/*']).map((i) => i.href))
      .toContain('/atrium/code')
  })

  test('an exact kernel-reserved collision on /atrium/code loses deterministically', () => {
    expect(collectRoutes(installedSolutions, ['/atrium/code']).map((r) => r.path))
      .not.toContain('/atrium/code')
    expect(collectNavItems(installedSolutions, ['/atrium/code']).map((i) => i.href))
      .not.toContain('/atrium/code')
  })
})
