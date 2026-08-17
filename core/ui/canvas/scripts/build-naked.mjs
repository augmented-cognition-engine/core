#!/usr/bin/env node
// core/ui/canvas/scripts/build-naked.mjs
//
// Naked-canvas build: prove the public Canvas builds with ZERO external-extension
// wiring present — the UI equivalent of the `ACE_DISABLE_EXTENSIONS=1` lane.
// This is the posture the PUBLIC export ships: extension wiring shims under
// `src/app/ext/<name>/` and their `public/<name>` asset symlinks are subtracted
// at export. Installed public solutions remain alongside kernel routes.
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
const STASH_REL = path.relative(CANVAS_ROOT, STASH_DIR)

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
//
// An extension's wiring shim under src/app/ext/<name>/ may itself be a real
// directory (checked in whole) or a symlink to one (a local dev workflow that
// links an extension's ui/canvas tree straight in) — Dirent.isDirectory() does
// NOT follow symlinks, so both must be checked or a symlinked shim silently
// survives the "naked" sweep. The same real-or-symlinked posture is already
// used for the repo-root extensions/ dir in devProxySeam.test.ts and
// vite.config.ts's collectExtensionProxies().
function discoverArtifacts() {
  const artifacts = []
  const extDir = path.join(CANVAS_ROOT, 'src', 'app', 'ext')
  for (const e of safeReaddir(extDir)) {
    if ((e.isDirectory() || e.isSymbolicLink()) && !KERNEL_EXT_MEMBERS.has(e.name)) {
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

// Moves are recorded into `moved` the instant each rename succeeds (not
// batched/returned at the end), so a later artifact's failed rename still
// leaves every prior successful move visible to `restore()` in the caller's
// `finally`. `moveAside` itself may throw partway through — that's fine, the
// artifacts already renamed are already recorded in `moved`.
function moveAside(moved) {
  mkdirSync(STASH_DIR, { recursive: true })
  for (const { src, key } of ARTIFACTS) {
    if (present(src)) {
      renameSync(src, path.join(STASH_DIR, key))
      moved.push({ src, key })
    }
  }
}

// Best-effort restore. An item that fails to move back is left IN the stash
// (never deleted) and reported so a human can recover it — restoring must
// never trade a missing extension shim for a silently lost one. The stash
// directory itself is only removed once every recorded move has been
// restored; on any failure it stays on disk untouched.
function restore(moved) {
  const failures = []
  for (const { src, key } of moved) {
    const stashed = path.join(STASH_DIR, key)
    if (!present(stashed)) continue // already restored (or never actually moved)
    try {
      renameSync(stashed, src)
    } catch (err) {
      failures.push({ src, key, message: err.message })
    }
  }
  if (failures.length > 0) {
    console.error(
      `[build:naked] RESTORE FAILED for ${failures.length} artifact(s) — recoverable material preserved at ${STASH_REL}, NOT deleted:`,
    )
    for (const f of failures) {
      console.error(`  ${STASH_REL}/${f.key} -> ${path.relative(CANVAS_ROOT, f.src)} (${f.message})`)
    }
    console.error('[build:naked] Restore manually, then remove the stash directory once empty.')
    return false
  }
  if (present(STASH_DIR)) rmSync(STASH_DIR, { recursive: true, force: true })
  console.log('[build:naked] extension wiring restored')
  return true
}

// REFUSE to run if a stash already exists — it means a previous run did not
// restore cleanly, and it may hold artifacts that were never put back. We
// never touch, let alone delete, a pre-existing stash; the operator must
// inspect and resolve it (restore by hand, or remove it once confirmed
// empty/stale) before build:naked can run again.
if (present(STASH_DIR)) {
  console.error(`[build:naked] REFUSING to run: ${STASH_REL} already exists.`)
  console.error(
    '[build:naked] A previous run left unrestored material there. Not touching it — inspect, restore by hand, and remove the directory once it is empty before retrying.',
  )
  process.exit(1)
}

const moved = []
let failed = false
try {
  moveAside(moved)
  console.log(
    '[build:naked] extension wiring removed:',
    moved.map((m) => path.relative(CANVAS_ROOT, m.src)).join(', ') || '(none present)',
  )
  console.log('[build:naked] tsc --noEmit')
  execSync('npx tsc --noEmit', { cwd: CANVAS_ROOT, stdio: 'inherit' })
  console.log('[build:naked] vite build')
  execSync('npx vite build', { cwd: CANVAS_ROOT, stdio: 'inherit' })
  // The boundary test, the installed Code solution's own registration test, and
  // the composition boundary between them must all hold in the naked posture:
  // with external extension wiring absent, the installed public solution (and
  // only the installed solution) still owns its route/nav contribution, and no
  // other src file leaks a hard extensions/ import. Run all three here so the
  // naked lane proves the build AND every boundary that posture depends on —
  // not just that vite succeeds.
  console.log('[build:naked] boundary + installed-solution tests (naked posture)')
  execSync(
    [
      'npx vitest run',
      'src/design/__enforcement__/noExtensionLeakage.test.ts',
      'src/app/solutions/code/register.test.tsx',
      'src/design/__enforcement__/codeSolutionComposition.test.ts',
      '--reporter=basic',
    ].join(' '),
    { cwd: CANVAS_ROOT, stdio: 'inherit' },
  )
  console.log('[build:naked] OK — public Canvas builds + boundary holds with zero external extensions')
} catch (err) {
  failed = true
  console.error('[build:naked] FAILED:', err.message)
} finally {
  if (!restore(moved)) failed = true
}

process.exit(failed ? 1 : 0)
