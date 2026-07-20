// core/ui/canvas/src/design/__enforcement__/devProxySeam.test.ts
//
// The extension dev-proxy seam, held to its contract.
//
// This seam exists because an extension UI must reach its data plane SAME-ORIGIN. The
// two ways it can go wrong are both silent — an extension shadowing a kernel route, and
// two extensions sharing a prefix — so both are asserted, not commented.

import { readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  ProxyCollisionError,
  mergeExtensionProxies,
  type DeclaredProxy,
  type ExtensionProxyFile,
} from '../devProxy'

const KERNEL = {
  '/canvas': { target: 'http://localhost:3000' },
  '/health': { target: 'http://localhost:3000' },
}

const entry = (extension: string, prefix: string, target = 'http://127.0.0.1:9999'): DeclaredProxy => ({
  extension,
  prefix,
  entry: { target },
})

describe('extension dev-proxy seam', () => {
  it('forwards an extension prefix the kernel does not own', () => {
    const merged = mergeExtensionProxies(KERNEL, [entry('metrics', '/api/v2', 'http://127.0.0.1:8788')])
    expect(merged['/api/v2']).toMatchObject({ target: 'http://127.0.0.1:8788', changeOrigin: true })
    expect(merged['/canvas']).toBeDefined() // kernel routes survive the merge
  })

  it('REFUSES an extension that claims a kernel route', () => {
    // Otherwise a stray `/health` swallows the kernel's own health route and the canvas
    // starts asking a data service whether ACE is alive — 200 OK, wrong answer.
    expect(() => mergeExtensionProxies(KERNEL, [entry('rogue', '/health')])).toThrow(
      ProxyCollisionError,
    )
  })

  it('REFUSES two extensions claiming the same prefix', () => {
    // Last-wins would route one extension's traffic into another's data plane. Both
    // services answer 200; the numbers are simply someone else's. Nothing would ever
    // surface it.
    expect(() =>
      mergeExtensionProxies(KERNEL, [entry('metrics', '/api/v2'), entry('other', '/api/v2')]),
    ).toThrow(/both claim proxy prefix/)
  })

  it('REFUSES a prefix that is not a path', () => {
    expect(() => mergeExtensionProxies(KERNEL, [entry('metrics', 'api/v2')])).toThrow(
      ProxyCollisionError,
    )
  })

  it('lets an operator repoint a target by env without a commit', () => {
    const merged = mergeExtensionProxies(
      KERNEL,
      [{ extension: 'metrics', prefix: '/api/v2', entry: { target: 'http://127.0.0.1:8788', targetEnv: 'VITE_METRICS_DATA_URL' } }],
      { VITE_METRICS_DATA_URL: 'http://plane.internal:9000' },
    )
    expect(merged['/api/v2']).toMatchObject({ target: 'http://plane.internal:9000' })
  })

  it('ignores an empty env override rather than proxying to nowhere', () => {
    const merged = mergeExtensionProxies(
      KERNEL,
      [{ extension: 'metrics', prefix: '/api/v2', entry: { target: 'http://127.0.0.1:8788', targetEnv: 'VITE_METRICS_DATA_URL' } }],
      { VITE_METRICS_DATA_URL: '' }, // an unset var in a shell script is '' not undefined
    )
    expect(merged['/api/v2']).toMatchObject({ target: 'http://127.0.0.1:8788' })
  })
})

describe('the installed extensions', () => {
  // The unit tests above prove the merge rules. This one proves what is ACTUALLY on
  // disk satisfies them — a declaration file is only worth anything if it parses.
  const root = path.resolve(__dirname, '../../../../../../extensions')

  it('all declare parseable, non-colliding proxies', () => {
    let dirs: string[] = []
    try {
      dirs = readdirSync(root, { withFileTypes: true })
        .filter((d) => d.isDirectory() || d.isSymbolicLink())
        .map((d) => d.name)
    } catch {
      return // running without extensions installed is a valid configuration
    }
    const declared: DeclaredProxy[] = []
    for (const name of dirs) {
      let raw: string
      try {
        raw = readFileSync(path.join(root, name, 'ui', 'canvas', 'canvas_proxy.json'), 'utf-8')
      } catch {
        continue
      }
      const parsed = JSON.parse(raw) as ExtensionProxyFile
      for (const [prefix, e] of Object.entries(parsed)) {
        expect(e.target, `${name} declared "${prefix}" with no target`).toBeTruthy()
        declared.push({ extension: name, prefix, entry: e })
      }
    }
    expect(() => mergeExtensionProxies(KERNEL, declared)).not.toThrow()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// THE SAME CASES THE PRODUCTION HOST IS TESTED AGAINST.
//
// canvas_proxy.json is read TWICE: by vite.config.ts in dev, and by the ACE canvas host
// (core/engine/api/canvas_host.py) in production. One manifest, two servers, two languages.
//
// Two implementations of a FAIL-CLOSED merge is exactly the bug that ships. Dev refuses a
// collision, prod silently allows it, one extension's traffic is routed into another
// extension's data plane, both services answer 200, and the numbers are simply someone else's.
//
// So the rules are DATA — core/ui/canvas_proxy_cases.json — and both implementations run them.
// Change the behaviour in one language and the other language's test goes red. The Python half
// is tests/test_canvas_host.py.
describe('the seam agrees with its production twin', () => {
  const cases = JSON.parse(
    readFileSync(path.resolve(__dirname, '../../../../canvas_proxy_cases.json'), 'utf8'),
  ).cases as Array<{
    name: string
    kernel: string[]
    declared: Array<{ extension: string; prefix: string; entry: Record<string, unknown> }>
    env: Record<string, string>
    expect: { merged?: Record<string, string>; error?: string }
  }>

  it('has cases to run — an empty case file would make this suite vacuous', () => {
    expect(cases.length).toBeGreaterThan(4)
  })

  for (const c of cases) {
    it(c.name, () => {
      const kernel = Object.fromEntries(c.kernel.map((k) => [k, 'http://kernel']))
      const declared = c.declared as never

      if (c.expect.error) {
        expect(() => mergeExtensionProxies(kernel, declared, c.env)).toThrow(ProxyCollisionError)
        return
      }

      const merged = mergeExtensionProxies(kernel, declared, c.env)
      for (const [prefix, target] of Object.entries(c.expect.merged!)) {
        const got = merged[prefix]
        expect(typeof got === 'string' ? got : (got as { target: string }).target).toBe(target)
      }
    })
  }
})
