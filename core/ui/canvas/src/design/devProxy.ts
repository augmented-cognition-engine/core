// core/ui/canvas/src/design/devProxy.ts
//
// The extension PROXY seam — read in dev by vite, and in production by the ACE canvas host.
//
// WHY THIS EXISTS. An extension's UI usually has to reach a data plane the kernel
// knows nothing about (an extension might federate with a data service on
// another port). Fetching that origin directly from the browser is a cross-origin
// request, and the browser blocks it unless the data plane opens CORS. Opening CORS
// is the wrong answer twice over: it puts a zero-auth service on the open internet,
// and it means the failure is invisible in every environment where a permissive
// middleware happens to be installed — the request only fails in a REAL browser
// against the REAL plane, which is precisely the environment nobody tests in.
//
// So the canvas proxies instead. The page fetches a SAME-ORIGIN relative path and the
// dev server forwards it. No CORS, no exposed origin, and the failure mode is a 502
// the developer can actually see.
//
// WHY IT'S A SEAM AND NOT A HARDCODED ENTRY. vite.config.ts is kernel. The kernel does
// not name extensions (tests/design/__enforcement__/noExtensionLeakage.test.ts). So an
// extension DECLARES its proxies in `ui/canvas/canvas_proxy.json` and the kernel merges
// them without ever learning what they are for.
//
// The merge FAILS CLOSED, and both refusals are load-bearing:
//
//   - An extension may not claim a prefix the kernel already routes. Otherwise a
//     stray `/health` entry silently swallows the kernel's own health route and the
//     canvas starts asking a market-data service whether ACE is alive.
//   - Two extensions may not claim the same prefix. Last-wins would route one
//     extension's traffic into another's data plane — the worst kind of bug, because
//     both services answer 200 and the numbers are simply someone else's.

import type { ProxyOptions } from 'vite'

/** What an extension is allowed to declare in `ui/canvas/canvas_proxy.json`. */
export interface ExtensionProxyEntry {
  /** Where the dev server forwards to, e.g. `http://127.0.0.1:8788`. */
  target: string
  /** Env var that overrides `target` when set — lets an operator repoint without a commit. */
  targetEnv?: string
  changeOrigin?: boolean
  ws?: boolean
}

export type ExtensionProxyFile = Record<string, ExtensionProxyEntry>

export interface DeclaredProxy {
  /** Extension directory name — used only to name the offender in a collision error. */
  extension: string
  prefix: string
  entry: ExtensionProxyEntry
}

export class ProxyCollisionError extends Error {}

/**
 * Merge extension-declared proxies onto the kernel's own.
 *
 * `env` is passed in rather than read from `process` so this is testable without
 * mutating global state.
 */
export function mergeExtensionProxies(
  kernelProxy: Record<string, ProxyOptions | string>,
  declared: DeclaredProxy[],
  env: Record<string, string | undefined> = {},
): Record<string, ProxyOptions | string> {
  const merged: Record<string, ProxyOptions | string> = { ...kernelProxy }
  const claimedBy = new Map<string, string>()

  for (const { extension, prefix, entry } of declared) {
    if (!prefix.startsWith('/')) {
      throw new ProxyCollisionError(
        `extension "${extension}" declared proxy prefix "${prefix}", which is not a path`,
      )
    }
    if (Object.prototype.hasOwnProperty.call(kernelProxy, prefix)) {
      throw new ProxyCollisionError(
        `extension "${extension}" tried to claim "${prefix}", which the kernel already routes. ` +
          `An extension cannot shadow a kernel route — pick a prefix the kernel does not own.`,
      )
    }
    const incumbent = claimedBy.get(prefix)
    if (incumbent !== undefined) {
      throw new ProxyCollisionError(
        `extensions "${incumbent}" and "${extension}" both claim proxy prefix "${prefix}". ` +
          `Two data planes behind one path route each other's traffic silently — refusing.`,
      )
    }
    claimedBy.set(prefix, extension)

    const override = entry.targetEnv ? env[entry.targetEnv] : undefined
    merged[prefix] = {
      target: override && override.length > 0 ? override : entry.target,
      changeOrigin: entry.changeOrigin ?? true,
      ...(entry.ws === true ? { ws: true } : {}),
    }
  }
  return merged
}
