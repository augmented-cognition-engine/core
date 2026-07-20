// core/ui/canvas/src/app/ext/registry.tsx
/// <reference types="vite/client" />
//
// The extension-UI seam. ACE core never imports extension code by path.
// Instead, an extension drops a `<name>/register.{ts,tsx}` module into
// THIS directory and the kernel discovers it at build time via
// `import.meta.glob`. In the private monorepo that module is a one-line
// shim re-exporting the extension's real register module (which lives
// under `extensions/<name>/ui/canvas/`); the shim itself is deny-listed
// at export, so the public tree ships with an empty `ext/` directory.
//
// With no extensions present the glob resolves to `{}` and the canvas
// builds and runs with kernel routes, the base theme, and neutral chrome
// defaults — the UI equivalent of the Python side's ACE_DISABLE_EXTENSIONS=1
// naked-kernel posture.
//
// Mechanism notes (chosen where the plan under-specified):
//   - Glob pattern: `./*/register.{ts,tsx}`, eager. One register module
//     per extension directory; modules are loaded in sorted path order so
//     discovery is deterministic.
//   - A register module DEFAULT-exports an `ExtensionUI`. Malformed
//     modules are skipped (the kernel must never crash because an
//     extension misregistered).
//   - Slots are first-wins in sorted order: the kernel renders its own
//     neutral default when no extension fills a slot.
//   - Themes are contributed as `AceTheme` objects and folded into the
//     design-system theme registry at load time (see design/themes).
import type { ComponentType, ReactElement, ReactNode } from 'react'

import { registerTheme, type AceTheme } from '../../design/themes'

/** A route contributed by an extension, mounted under the kernel router. */
export interface ExtensionRoute {
  path: string
  element: ReactElement
}

/** Props contract for the partner-voice line slot (the always-on line at
 *  the bottom of deliberation surfaces). Extensions may register a branded
 *  implementation; the kernel default is a quiet, unbranded line. */
export interface PartnerVoiceProps {
  children: ReactNode
  speaker?: string
  instant?: boolean
}

/** Named chrome slots an extension can fill. Each is optional; the kernel
 *  renders a neutral default for any slot left empty. */
export interface ExtensionSlots {
  /** App sidebar navigation (rendered inside SidebarProvider). */
  nav?: ComponentType
  /** Intel panel content for the room's notifications dropdown. */
  intel?: ComponentType
  /** Partner-voice line component. */
  voice?: ComponentType<PartnerVoiceProps>
}

/** What an extension's `register` module default-exports. */
export interface ExtensionUI {
  /** Stable extension name (snake-ish slug, e.g. the directory name). */
  name: string
  routes?: ExtensionRoute[]
  themes?: AceTheme[]
  slots?: ExtensionSlots
}

/** Runtime shape-check for a register module's default export. */
export function isExtensionUI(value: unknown): value is ExtensionUI {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  if (typeof v.name !== 'string' || v.name.length === 0) return false
  if (v.routes !== undefined && !Array.isArray(v.routes)) return false
  if (v.themes !== undefined && !Array.isArray(v.themes)) return false
  return true
}

/** Pure discovery step — separated from the glob so it is unit-testable.
 *  Takes the raw module record (path → module) and returns the valid
 *  ExtensionUI objects in deterministic (sorted-path) order. */
export function collectExtensions(
  modules: Record<string, unknown>,
): ExtensionUI[] {
  return Object.keys(modules)
    .sort()
    .map((key) => {
      const mod = modules[key]
      if (typeof mod !== 'object' || mod === null) return undefined
      return (mod as { default?: unknown }).default
    })
    .filter(isExtensionUI)
}

/** Pure slot resolution — first extension (sorted order) that fills the
 *  slot wins; undefined means "render the kernel default". */
export function resolveSlot<K extends keyof ExtensionSlots>(
  exts: readonly ExtensionUI[],
  slot: K,
): ExtensionSlots[K] | undefined {
  for (const ext of exts) {
    const component = ext.slots?.[slot]
    if (component !== undefined) return component
  }
  return undefined
}

// ---------------------------------------------------------------------------
// Build-time discovery. With an empty/absent ext directory this yields {}.
// ---------------------------------------------------------------------------

const registerModules = import.meta.glob('./*/register.{ts,tsx}', {
  eager: true,
}) as Record<string, unknown>

/** All registered extension UIs, in deterministic order. */
export const extensions: readonly ExtensionUI[] =
  collectExtensions(registerModules)

// Fold contributed themes into the design-system theme registry once, at
// module load — main.tsx imports this module before first render, so
// themes are available wherever THEMES/applyTheme is consumed.
for (const ext of extensions) {
  for (const theme of ext.themes ?? []) registerTheme(theme)
}

/** All extension-contributed routes, flattened in registration order. */
export function extensionRoutes(): ExtensionRoute[] {
  return extensions.flatMap((ext) => ext.routes ?? [])
}

/** The component registered for a chrome slot, or undefined (kernel
 *  default applies). */
export function extensionSlot<K extends keyof ExtensionSlots>(
  slot: K,
): ExtensionSlots[K] | undefined {
  return resolveSlot(extensions, slot)
}
