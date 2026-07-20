#!/usr/bin/env node
// core/ui/canvas/scripts/build-naked.mjs
//
// Naked-canvas build: prove the kernel canvas builds with ZERO extension
// wiring present — the UI equivalent of the `ACE_DISABLE_EXTENSIONS=1`
// naked-kernel lane. This is the posture the PUBLIC export ships: the extension
// wiring shims under `src/app/ext/<name>/` and their `public/<name>` asset
// symlinks are subtracted at export, so `import.meta.glob('./*/register.{ts,tsx}')`
// finds nothing and the canvas mounts kernel routes only.
//
// WHY A SCRIPT (not a vite mode flag): import.meta.glob resolves against the
// real filesystem at build time — a mode/env flag cannot make vite "not see" a
// directory that exists on disk. The honest way to prove the naked build is to
// make the artifacts genuinely ABSENT, run a real `tsc --noEmit` + `vite
// build`, then restore. We move them aside (rename, not delete) and restore in
// a `finally` so an interrupted/failed build never leaves the worktree dirty.
// `git checkout` would also restore them, but we don't rely on git here so the
// script is safe to run on a copy/checkout in CI.
//
// Usage: node scripts/build-naked.mjs   (wired as `npm run build:naked`)
import { execSync } from 'node:child_process'
import { renameSync, lstatSync, mkdirSync, rmSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const CANVAS_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

// Stash OUTSIDE src/ and public/ — under a dedicated dir at the canvas root —
// so the moved-aside artifacts are invisible to (a) the boundary test, which
// walks src/ only, and (b) the static-html plugin, which serves public/ only.
// A first attempt that stashed in-place failed because a shim's register.tsx
// stayed under src/ and tripped the boundary test. The stash dir is
// gitignored-adjacent and removed on exit.
const STASH_DIR = path.join(CANVAS_ROOT, '.naked-stash')

// The kernel-owned members of src/app/ext/ — every OTHER entry there is an
// extension wiring shim. Keep in lockstep with KERNEL_EXT_MEMBERS in
// noExtensionLeakage.test.ts.
const KERNEL_EXT_MEMBERS = new Set(['defaults'])

function safeReaddir(dir) {
  try {
    return readdirSync(dir, { withFileTypes: true })
  } catch {
    return []
  }
}

// Discover the master-posture artifacts that carry extension wiring, BY STRUCTURE
// (no extension is named here): every subdirectory of src/app/ext/ other than the
// kernel-owned members, plus every SYMLINK under public/ (extensions link their UI
// assets in; kernel assets are real files). Subtracting these reproduces the public
// tree — and stays correct as extensions are added or removed.
function discoverArtifacts() {
  const artifacts = []
  const extDir = path.join(CANVAS_ROOT, 'src', 'app', 'ext')
  for (const e of safeReaddir(extDir)) {
    if (e.isDirectory() && !KERNEL_EXT_MEMBERS.has(e.name)) {
      artifacts.push({ src: path.join(extDir, e.name), key: `ext-${e.name}` })
    }
  }
  const publicDir = path.join(CANVAS_ROOT, 'public')
  for (const e of safeReaddir(publicDir)) {
    if (e.isSymbolicLink()) {
      artifacts.push({ src: path.join(publicDir, e.name), key: `public-${e.name}` })
    }
  }
  return artifacts
}

// The master-posture artifacts that carry extension wiring. Deny-listed /
// subtracted at export; removing them here reproduces the public tree.
const ARTIFACTS = discoverArtifacts()

function present(p) {
  // lstat (not exists) so a symlink — even a dangling one — counts as present.
  try {
    lstatSync(p)
    return true
  } catch {
    return false
  }
}

function moveAside() {
  const moved = []
  if (present(STASH_DIR)) rmSync(STASH_DIR, { recursive: true, force: true })
  mkdirSync(STASH_DIR, { recursive: true })
  for (const { src, key } of ARTIFACTS) {
    if (present(src)) {
      renameSync(src, path.join(STASH_DIR, key))
      moved.push({ src, key })
    }
  }
  return moved
}

function restore(moved) {
  for (const { src, key } of moved) {
    const stashed = path.join(STASH_DIR, key)
    if (present(stashed)) renameSync(stashed, src)
  }
  if (present(STASH_DIR)) rmSync(STASH_DIR, { recursive: true, force: true })
}

const moved = moveAside()
let failed = false
try {
  console.log('[build:naked] extension wiring removed:', moved.map((m) => path.relative(CANVAS_ROOT, m.src)).join(', ') || '(none present)')
  console.log('[build:naked] tsc --noEmit')
  execSync('npx tsc --noEmit', { cwd: CANVAS_ROOT, stdio: 'inherit' })
  console.log('[build:naked] vite build')
  execSync('npx vite build', { cwd: CANVAS_ROOT, stdio: 'inherit' })
  // The boundary test must also hold in the naked posture: with the shim
  // absent, the sole sanctioned exception simply isn't present, and no other
  // src file may leak. Run it here so the naked lane proves both build AND
  // boundary, not just the build.
  console.log('[build:naked] boundary test (naked posture)')
  execSync(
    'npx vitest run src/design/__enforcement__/noExtensionLeakage.test.ts --reporter=basic',
    { cwd: CANVAS_ROOT, stdio: 'inherit' },
  )
  console.log('[build:naked] OK — kernel canvas builds + boundary holds with zero extensions')
} catch (err) {
  failed = true
  console.error('[build:naked] FAILED:', err.message)
} finally {
  restore(moved)
  console.log('[build:naked] extension wiring restored')
}

process.exit(failed ? 1 : 0)
