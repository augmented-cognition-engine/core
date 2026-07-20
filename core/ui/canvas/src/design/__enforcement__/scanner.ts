// core/ui/canvas/src/design/__enforcement__/scanner.ts
//
// Shared file-scanning utility for the design-system enforcement
// tests. Each test calls `scanForPattern` with a regex + the scope to
// scan + the allowlist of intentional exceptions, and asserts the
// returned matches list is empty.
//
// The tests run via vitest. cwd is the canvas package root
// (core/ui/canvas/), so all paths are resolved relative to that.
import fs from 'node:fs'
import path from 'node:path'

export interface Match {
  /** Absolute file path. */
  file: string
  /** 1-indexed line number where the pattern matched. */
  line: number
  /** Trimmed line content for error reporting. */
  text: string
}

export interface ScanOptions {
  /** Extensions to scan. Default: ['.tsx', '.ts']. */
  extensions?: string[]
  /** Directory names to skip during walk. Default skips node_modules,
   *  dist, build, __enforcement__ (so the scanner doesn't scan itself). */
  excludeDirs?: string[]
  /** Specific files to exclude (path suffix match). Used for explicit
   *  allowlist entries — files that have legitimate uses of the
   *  pattern (e.g. tldraw shape utils with runtime-injected colors). */
  excludeFiles?: string[]
  /** Regex-based exclusions, tested against the full absolute path.
   *  Used for allowlist rules that describe a CLASS of path (e.g.
   *  "any extension mount's theme file") rather than one exact file —
   *  keeps the allowlist generic instead of enumerating every
   *  extension by name. */
  excludePatterns?: RegExp[]
}

const DEFAULT_EXCLUDE_DIRS = [
  'node_modules',
  'dist',
  'build',
  '__enforcement__',
  '__tests__',
]

export function scanForPattern(
  rootDir: string,
  pattern: RegExp,
  options: ScanOptions = {},
): Match[] {
  const {
    extensions = ['.tsx', '.ts'],
    excludeDirs = DEFAULT_EXCLUDE_DIRS,
    excludeFiles = [],
    excludePatterns = [],
  } = options
  const matches: Match[] = []

  function walk(dir: string): void {
    let entries: fs.Dirent[]
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        if (excludeDirs.includes(entry.name)) continue
        walk(full)
        continue
      }
      if (!entry.isFile()) continue
      const ext = path.extname(entry.name)
      if (!extensions.includes(ext)) continue
      if (excludeFiles.some((f) => full.endsWith(f))) continue
      if (excludePatterns.some((p) => p.test(full))) continue

      const content = fs.readFileSync(full, 'utf-8')
      const lines = content.split('\n')
      for (let i = 0; i < lines.length; i++) {
        // Reset regex state for each line — important when pattern
        // has the global flag.
        pattern.lastIndex = 0
        if (pattern.test(lines[i])) {
          matches.push({
            file: full,
            line: i + 1,
            text: lines[i].trim(),
          })
        }
      }
    }
  }

  walk(rootDir)
  return matches
}

/** Discover extension canvas-UI roots so the design rules police extensions
 *  the same as the kernel. GENERIC by construction (no extension is named —
 *  the open-core boundary holds): any `<repo>/extensions/<name>/ui/canvas`
 *  directory is a scan root. Returns [] outside the monorepo (e.g. a
 *  standalone kernel checkout), so kernel-only runs are unaffected. */
export function extensionUiRoots(): string[] {
  // __enforcement__ → design → src → canvas → ui → core → <repo>
  const repoRoot = path.resolve(__dirname, '..', '..', '..', '..', '..', '..')
  const extensionsDir = path.join(repoRoot, 'extensions')
  let entries: fs.Dirent[]
  try {
    entries = fs.readdirSync(extensionsDir, { withFileTypes: true })
  } catch {
    return []
  }
  const roots: string[] = []
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const candidate = path.join(extensionsDir, entry.name, 'ui', 'canvas')
    if (fs.existsSync(candidate)) roots.push(candidate)
  }
  return roots
}

/** Scan the kernel app root AND every discovered extension UI root. */
export function scanAllUiRoots(
  appRoot: string,
  pattern: RegExp,
  options: ScanOptions = {},
): Match[] {
  const matches = scanForPattern(appRoot, pattern, options)
  for (const root of extensionUiRoots()) {
    matches.push(...scanForPattern(root, pattern, options))
  }
  return matches
}

/** Format a list of matches into a multi-line error string suitable
 *  for the assertion failure message. */
export function formatMatches(matches: Match[]): string {
  return matches
    .map((m) => `  ${path.relative(process.cwd(), m.file)}:${m.line} → ${m.text}`)
    .join('\n')
}
