// core/ui/canvas/src/design/__enforcement__/noExtensionLeakage.test.ts
//
// The UI sibling of tests/test_kernel_boundary.py. That Python test asserts the
// kernel never imports `extensions.*`; this one asserts the kernel CANVAS never
// imports from `extensions/` by a hard path. It is the TypeScript half of the
// open-core boundary (docs/architecture.md): the Apache-2.0 kernel canvas must
// build and run with ZERO extensions present — the naked-canvas posture.
//
// SCOPE — STRUCTURAL, NOT BRANDED
//   This guard enforces the IMPORT boundary only, and it does so without
//   naming any extension. Core code must reach extensions ONLY through the
//   registry seam (src/app/ext/registry.tsx → import.meta.glob), never by a
//   hard `import ... from 'extensions/...'` (or a relative climb into the
//   repo-root extensions/ tree, or a dynamic import() of one).
//
//   The extension wiring shims live at src/app/ext/<name>/ and legitimately
//   re-export their own extension's register module, so they are exempt — by
//   STRUCTURE (any subdirectory of src/app/ext/ other than the kernel-owned
//   `defaults`), not by an enumerated list of names. A leak anywhere ELSE in
//   src/ still trips. In the public tree the shims are subtracted at export, so
//   src/app/ext/ holds only the seam + defaults and the exemption matches
//   nothing — the canvas mounts kernel routes alone.
//
// WHY BRAND NAMES ARE NOT SCANNED HERE
//   The authoritative brand/secret gate is scripts/export/leak_scan.py — it
//   runs FAIL-CLOSED over the whole would-ship tree at export time, and it does
//   NOT ship. A guard that scanned for private brand terms would have to SPELL
//   them to detect them, which is self-defeating for a file that ships publicly.
//   So brand enforcement stays in the private export pipeline; this shipped test
//   enforces the structural import boundary that any contributor can reason about.
//
// This test runs inside the normal `npx vitest run` (it lives under
// __enforcement__/, which the kernel vitest globs already cover) AND in the
// naked-canvas posture — see package.json `build:naked` and the CI canvas job.
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC_ROOT = path.resolve(__dirname, '..', '..')

// The extension-wiring seam. A file is a wiring shim — and therefore allowed to
// import its own extension — iff it sits INSIDE a subdirectory of src/app/ext/
// other than the kernel-owned members below. The seam file (registry.tsx) and
// its defaults live directly under ext/ or in `defaults/`, so they are scanned
// like any other kernel source; they reach extensions only via import.meta.glob.
const EXT_SEAM = ['src', 'app', 'ext'].join('/')
const KERNEL_EXT_MEMBERS = new Set(['defaults'])

function isExtensionShim(relToCanvas: string): boolean {
  const rel = relToCanvas.split(path.sep).join('/')
  const prefix = `${EXT_SEAM}/`
  if (!rel.startsWith(prefix)) return false
  const rest = rel.slice(prefix.length)
  if (!rest.includes('/')) return false // a file directly under ext/ (e.g. registry.tsx) is kernel
  const sub = rest.split('/')[0]
  return !KERNEL_EXT_MEMBERS.has(sub)
}

// --- Import-boundary patterns ------------------------------------------------
// The Python sibling (tests/test_kernel_boundary.py) matches WHOLE statements
// with re.MULTILINE so a parenthesized `from extensions.x import (...)` spanning
// lines is caught. We mirror that posture: instead of scanning physical lines,
// we JOIN each import/export-from statement into one logical line (see
// `logicalImportLines`) and match the joined form. This closes the multi-line
// evasion — `}\n from 'extensions/reference/foo'` — where the bare specifier
// sits alone on its own physical line with no keyword to backstop it.
//
// `from '<anything>extensions/...'` on a joined import/export statement. The
// specifier may be a bare package path (`extensions/...`) or any relative climb
// (`../../extensions/...`) — both resolve into the repo-root extensions/ tree.
// The wiring shims' `../../../../../../../extensions/...` is exempt by structure
// (isExtensionShim), handled before this runs.
const IMPORT_FROM_EXTENSIONS =
  /\b(?:import|export)\b[^'"`]*?\bfrom\s*['"`][^'"`]*?extensions\//s
// Any dynamic import() whose specifier mentions `extensions/` ANYWHERE — string
// literal, template literal (`${base}/extensions/...`), or concatenation. A
// dynamic import reaching extensions/ is a coupling regardless of how the
// string is assembled, so we do NOT anchor `extensions/` to the string start.
const IMPORT_DYNAMIC_EXTENSIONS = /\bimport\s*\([^)]*?extensions\//s

interface Leak {
  file: string
  line: number
  pattern: string
  text: string
}

/** A logical import/export-from statement: the joined text plus the 1-indexed
 *  physical line where it began (for reporting). */
interface LogicalStatement {
  line: number
  text: string
}

/** Join physical lines into logical import/export statements so a multi-line
 *  `import { ... } from '...'` (or `export { ... } from '...'`) is seen whole.
 *
 *  A statement starts on a line beginning with `import`/`export` (ignoring
 *  leading whitespace) and continues until the line that closes it — the first
 *  line carrying a `from '...'`/`from "..."` clause, OR a bare-side-effect
 *  `import '...'`, OR (defensively) a `;`. We cap the join at a small window so
 *  a malformed file can't run away. Non-import lines are emitted as-is (so the
 *  dynamic-import and any future single-line checks still see every line). */
function logicalImportLines(lines: string[]): LogicalStatement[] {
  const out: LogicalStatement[] = []
  const startsStatement = (l: string) => /^\s*(?:import|export)\b/.test(l)
  // A line that closes an import/export-from statement: it carries the module
  // specifier (`from '...'` / `from "..."`) or is a bare `import '...'`.
  const closesStatement = (l: string) => /\bfrom\s*['"`]/.test(l) || /^\s*import\s*['"`]/.test(l)
  const MAX_JOIN = 40

  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (startsStatement(line) && !closesStatement(line)) {
      // Open statement — join forward until it closes (or window/EOF).
      let joined = line
      let j = i + 1
      let closed = false
      while (j < lines.length && j - i <= MAX_JOIN) {
        joined += ' ' + lines[j].trim()
        if (closesStatement(lines[j]) || /;\s*$/.test(lines[j])) {
          closed = true
          j++
          break
        }
        j++
      }
      out.push({ line: i + 1, text: joined })
      i = closed ? j : i + 1
      continue
    }
    out.push({ line: i + 1, text: line })
    i++
  }
  return out
}

function walk(dir: string, acc: string[]): string[] {
  let entries: fs.Dirent[]
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return acc
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      // Skip build output and the enforcement scanners themselves — these test
      // files necessarily SPELL the `extensions/` specifier to detect it.
      // INVARIANT: __enforcement__/ holds ONLY *.test.ts scanners + their
      // helpers — no runtime/app code may live here, or it would escape this
      // boundary guard.
      if (
        entry.name === 'node_modules' ||
        entry.name === 'dist' ||
        entry.name === '__enforcement__'
      ) {
        continue
      }
      walk(full, acc)
      continue
    }
    if (!entry.isFile()) continue
    if (!/\.(ts|tsx)$/.test(entry.name)) continue
    acc.push(full)
  }
  return acc
}

/** Pure scan of one file's relative path + content. Separated from disk I/O so
 *  the regression tests can feed synthetic content directly. */
function scanContent(relToCanvas: string, content: string): Leak[] {
  if (isExtensionShim(relToCanvas)) return []

  const leaks: Leak[] = []
  const lines = content.split('\n')

  // Import-boundary check on JOINED statements — closes the multi-line bare
  // `extensions/...` evasion. Each statement reports its starting physical line.
  for (const stmt of logicalImportLines(lines)) {
    if (IMPORT_FROM_EXTENSIONS.test(stmt.text) || IMPORT_DYNAMIC_EXTENSIONS.test(stmt.text)) {
      leaks.push({
        file: relToCanvas,
        line: stmt.line,
        pattern: 'import:extensions',
        text: stmt.text.trim().slice(0, 160),
      })
    }
  }
  return leaks
}

const CANVAS_ROOT = path.resolve(SRC_ROOT, '..')

function scanFile(absFile: string): Leak[] {
  const relToCanvas = path.relative(CANVAS_ROOT, absFile)
  return scanContent(relToCanvas, fs.readFileSync(absFile, 'utf-8'))
}

function format(leaks: Leak[]): string {
  return leaks
    .map((l) => `  ${l.file}:${l.line} [${l.pattern}] ${l.text}`)
    .join('\n')
}

describe('open-core boundary: kernel canvas never imports an extension by path', () => {
  it('no src file (except the ext/ wiring shims) imports from extensions/', () => {
    const files = walk(SRC_ROOT, [])
    const leaks = files.flatMap(scanFile)
    expect(
      leaks,
      'Kernel canvas imports an extension by a hard path — the open-core UI\n' +
        'boundary is broken. Core canvas must reach extensions ONLY through the\n' +
        'registry seam (src/app/ext/registry.tsx → import.meta.glob), never by a\n' +
        'hard path. The only exempt files are the ext/<name>/ wiring shims\n' +
        '(subtracted at export). Offending lines:\n' +
        format(leaks),
    ).toEqual([])
  })
})

// A non-shim kernel-src path so the structural exemption never fires.
const VICTIM = path.join('src', 'app', 'feature.ts')
const patternsOf = (leaks: Leak[]) => leaks.map((l) => l.pattern)

describe('boundary detection: extension imports must trip regardless of form', () => {
  // `extensions/reference` (and any `extensions/<name>`) carry no brand term, so
  // the import-boundary check is the ONLY thing that catches them. Each form
  // below must yield import:extensions.

  it('multi-line bare specifier on its own line (no keyword) trips', () => {
    const src = ["import {", "  foo,", "} from 'extensions/reference/foo'", "export const x = foo"].join('\n')
    expect(patternsOf(scanContent(VICTIM, src))).toContain('import:extensions')
  })

  it('multi-line export-from bare specifier trips', () => {
    const src = ["export {", "  bar,", "} from 'extensions/reference/bar'"].join('\n')
    expect(patternsOf(scanContent(VICTIM, src))).toContain('import:extensions')
  })

  it('dynamic import with a template-literal specifier trips (and this form BUILDS)', () => {
    const src = ['const base = ".."', 'export const load = () => import(`${base}/extensions/reference/foo`)'].join('\n')
    expect(patternsOf(scanContent(VICTIM, src))).toContain('import:extensions')
  })

  it('dynamic import with string concatenation trips', () => {
    const src = ['const seg = "reference"', 'const load = () => import("extensions/" + seg + "/foo")'].join('\n')
    expect(patternsOf(scanContent(VICTIM, src))).toContain('import:extensions')
  })

  it('single-line bare and relative-climb specifiers still trip (no regression)', () => {
    expect(patternsOf(scanContent(VICTIM, "import x from 'extensions/reference/foo'"))).toContain('import:extensions')
    expect(patternsOf(scanContent(VICTIM, "export { y } from '../../../extensions/reference/foo'"))).toContain(
      'import:extensions',
    )
  })

  it('clean kernel imports do NOT trip import:extensions', () => {
    const clean = [
      "import {",
      "  registerTheme,",
      "} from '../../design/themes'",
      "import { extensions } from './ext/registry'", // local seam, not a leak
      "const note = 'no extensions/ path here'",
    ].join('\n')
    expect(patternsOf(scanContent(VICTIM, clean))).not.toContain('import:extensions')
  })
})

describe('the wiring-shim exemption is structural, not by name', () => {
  const shimImport = "export { register } from '../../../../../../extensions/sample/register'"

  it('an ext/<name>/ shim may import its own extension', () => {
    const shim = path.join('src', 'app', 'ext', 'sample', 'register.tsx')
    expect(scanContent(shim, shimImport)).toEqual([])
  })

  it('the kernel-owned ext/ members (defaults, registry) are NOT exempt', () => {
    // A file under ext/defaults/ or the registry itself importing extensions/ is
    // a real leak — the exemption must not cover them.
    const inDefaults = path.join('src', 'app', 'ext', 'defaults', 'Leak.tsx')
    const theRegistry = path.join('src', 'app', 'ext', 'registry.tsx')
    expect(patternsOf(scanContent(inDefaults, shimImport))).toContain('import:extensions')
    expect(patternsOf(scanContent(theRegistry, shimImport))).toContain('import:extensions')
  })
})
