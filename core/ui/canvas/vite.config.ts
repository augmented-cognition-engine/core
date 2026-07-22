// core/ui/canvas/vite.config.ts
import { promises as fs, readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

import { defineConfig, type Plugin, type ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

import {
  mergeExtensionProxies,
  type DeclaredProxy,
  type ExtensionProxyFile,
} from './src/design/devProxy'

/**
 * Collect `extensions/<name>/ui/canvas/canvas_proxy.json` declarations.
 *
 * An extension UI that talks to its own data plane must reach it same-origin —
 * a direct cross-origin fetch is blocked by the browser, and the alternative
 * (opening CORS on the plane) exposes a zero-auth service. See src/design/devProxy.ts.
 *
 * The kernel discovers these by SHAPE, never by name: nothing here knows which
 * extensions exist, and with no extensions installed the list is empty.
 */
function collectExtensionProxies(): DeclaredProxy[] {
  const root = path.resolve(__dirname, '../../../extensions')
  const found: DeclaredProxy[] = []
  let dirs: string[]
  try {
    dirs = readdirSync(root, { withFileTypes: true })
      .filter((d) => d.isDirectory() || d.isSymbolicLink())
      .map((d) => d.name)
  } catch {
    return found // no extensions installed — the kernel runs bare
  }
  for (const name of dirs.sort()) {
    const file = path.join(root, name, 'ui', 'canvas', 'canvas_proxy.json')
    let raw: string
    try {
      raw = readFileSync(file, 'utf-8')
    } catch {
      continue // this extension publishes no UI proxies
    }
    // A malformed declaration is NOT skipped: an extension that meant to route its
    // data plane and silently didn't would present as "plane down" forever.
    const parsed = JSON.parse(raw) as ExtensionProxyFile
    for (const [prefix, entry] of Object.entries(parsed)) {
      found.push({ extension: name, prefix, entry })
    }
  }
  return found
}

/**
 * Serve static extension .html files from `public/<dir>/*.html` BEFORE
 * Vite's SPA fallback rewrites them to index.html.
 *
 * Vite defaults to `appType: 'spa'`, whose htmlFallbackMiddleware claims
 * every .html request and rewrites it to index.html so client-side
 * routing can pick it up. That's correct for SPA routes, but it shadows
 * static legacy pages an extension may publish under public/<dir>/
 * (extensions symlink their static UI into public/; the kernel names no
 * extension here). Without this plugin a `/<dir>/page.html` request
 * returns the React shell instead of the actual file on disk.
 *
 * Scope is intentionally narrow: only nested `*.html` paths that resolve
 * to a real file under public/. Anything else (canvas SPA, design system
 * showcase, assets) falls through to Vite's normal middleware — with no
 * extension static pages present, every request falls through.
 */
function serveExtensionStaticHtml(): Plugin {
  const publicDir = path.resolve(__dirname, 'public')
  return {
    name: 'ace:serve-extension-static-html',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = req.url ?? ''
        // Strip query string for path matching but preserve for downstream.
        const [pathname] = url.split('?')
        // Nested .html only (/<dir>/.../page.html) — never the SPA root
        // index.html or a top-level html route.
        const isNestedHtml =
          /^\/[^/]+\/.+\.html$/.test(pathname ?? '') === true
        if (!isNestedHtml || pathname === undefined) {
          return next()
        }
        const filePath = path.join(publicDir, pathname)
        // Defense in depth — ensure the resolved path stays under publicDir.
        const resolved = path.resolve(filePath)
        if (!resolved.startsWith(publicDir + path.sep)) return next()
        try {
          const content = await fs.readFile(resolved, 'utf-8')
          res.setHeader('Content-Type', 'text/html; charset=utf-8')
          res.setHeader('Cache-Control', 'no-cache')
          res.statusCode = 200
          res.end(content)
        } catch {
          next()
        }
      })
    },
  }
}

/** The kernel's own routes. An extension may not claim any of these (fail-closed). */
const kernelProxy: Record<string, ProxyOptions | string> = Object.fromEntries(
  (
    [
      ['/canvas', true],
      ['/proactive', true],
      ['/briefings', false],
      ['/portal', false],
      ['/product', false],
      ['/auth', false],
      ['/recommendations', false],
      ['/decisions', false],
      ['/foresight', false],
      ['/atc', false],
      ['/health', false],
      ['/sentinels', false],
    ] as const
  ).map(([route, ws]) => [
    route,
    {
      target: process.env.VITE_API_BASE_URL ?? 'http://localhost:3000',
      changeOrigin: true,
      ...(ws ? { ws: true } : {}),
    },
  ]),
)

export default defineConfig({
  plugins: [react(), tailwindcss(), serveExtensionStaticHtml()],
  // Yjs constructor checks break if two copies of the module end up in the
  // bundle (one from `import * as Y from 'yjs'`, one from `y-websocket`
  // pulling its own pre-bundled copy). Force a single resolved instance.
  resolve: {
    dedupe: ['yjs'],
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  optimizeDeps: { include: ['yjs', 'y-indexeddb', 'y-websocket'] },
  server: {
    proxy: mergeExtensionProxies(kernelProxy, collectExtensionProxies(), process.env),
  },
})
