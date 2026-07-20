import path from 'node:path'

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Mirror the `@` → src alias from vite.config.ts so component tests can
  // import via the same path alias the app uses.
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  // Extension canvas-UI files live outside this package dir; let the
  // vite-node server read from the repo root.
  server: {
    fs: {
      allow: [path.resolve(__dirname, '../../..')],
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    // Scan from the repo root so extension canvas-UI suites (wired in
    // through the ext seam, src/app/ext/) run alongside the kernel's.
    // The globs are generic — no extension is named — and match nothing
    // when no extensions are present.
    dir: path.resolve(__dirname, '../../..'),
    include: [
      'core/ui/canvas/src/**/*.{test,spec}.{ts,tsx}',
      'extensions/*/ui/canvas/**/*.{test,spec}.{ts,tsx}',
    ],
    exclude: ['**/node_modules/**', '**/tests/e2e/**', '**/dist/**'],
  },
})
