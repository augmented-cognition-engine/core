// core/ui/canvas/src/app/ext/registry.tsx
/// <reference types="vite/client" />
//
// The Canvas contribution seam. Installed first-party solutions publish a
// register module under `app/solutions/<name>/`; external extensions publish
// one under `app/ext/<name>/`. Both reuse the same small `ExtensionUI`
// contract and are discovered at build time via `import.meta.glob`, so the
// application entry point never imports a solution or extension by name.
// External extension shims may re-export an implementation from
// `extensions/<name>/ui/canvas/`; installed solution registrations remain in
// the public/package build and in the extension-disabled naked posture.
//
// With no external extensions present, installed solutions and kernel routes
// remain available with the base theme and neutral chrome defaults — the UI
// equivalent of the Python side's ACE_DISABLE_EXTENSIONS=1 posture.
//
// Mechanism notes (chosen where the plan under-specified):
//   - Glob patterns: `../solutions/*/register.{ts,tsx}` for installed
//     solutions and `./*/register.{ts,tsx}` for extensions, eager. Installed
//     solutions compose first; each group is sorted by path.
//   - A register module DEFAULT-exports an `ExtensionUI`. Malformed
//     modules are skipped (the kernel must never crash because an
//     extension misregistered).
//   - Slots are first-wins in sorted order: the kernel renders its own
//     neutral default when no extension fills a slot.
//   - Themes are contributed as `AceTheme` objects and folded into the
//     design-system theme registry at load time (see design/themes).
//   - Contributed paths (route `path`, nav `href`) must be canonical,
//     bounded, literal, same-origin paths — see `isCanonicalSameOriginPath`.
//     Anything that looks like a route pattern (`:id`, `*`), a cross-origin
//     or protocol-relative target, or an alias of an already-canonical path
//     (trailing slash, dot-segment) is rejected outright rather than merely
//     deduplicated, so the kernel router never has to resolve an ambiguity.
import {
  isValidElement,
  type ComponentType,
  type ReactElement,
  type ReactNode,
} from 'react'

import { registerTheme, type AceTheme } from '../../design/themes'

/** A route contributed by an installed solution or extension. */
export interface ExtensionRoute {
  path: string
  element: ReactElement
}

/** An additive sidebar entry contributed through the Canvas seam. */
export interface ExtensionNavItem {
  href: string
  icon: ComponentType<{ className?: string }>
  label: string
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

/** What a Canvas solution/extension `register` module default-exports. */
export interface ExtensionUI {
  /** Stable contribution name (snake-ish slug, e.g. the directory name). */
  name: string
  routes?: ExtensionRoute[]
  navItems?: ExtensionNavItem[]
  themes?: AceTheme[]
  slots?: ExtensionSlots
}

// A contributed path must be a bounded literal same-origin path: it can
// never be mistaken for a route pattern, a cross-origin target, or an alias
// of some other canonical path. Every rejection below corresponds to one
// concrete evasion:
//   - not a string / empty / over-length     → not bounded
//   - leading/trailing/embedded whitespace    → not literal
//   - control characters                      → not literal
//   - missing leading '/'                     → not a same-origin path
//   - '//' anywhere (leading or embedded)     → protocol-relative / repeated-slash alias
//   - trailing '/' (except the bare root)     → alias of the non-slash form
//   - '\\'                                     → not a URL path separator
//   - '?' / '#'                                → carries query/fragment
//   - '*'                                      → wildcard route pattern
//   - ':'                                      → route param syntax (":id")
//   - '%'                                      → percent-encoding (decodes to any of the above)
//   - a literal '.' or '..' path segment       → dot-segment alias
const MAX_CANVAS_PATH_LENGTH = 200
const MAX_NAME_LENGTH = 100
const MAX_LABEL_LENGTH = 100
const MAX_ROUTES_PER_REGISTRATION = 50
const MAX_NAV_ITEMS_PER_REGISTRATION = 50
const MAX_THEMES_PER_REGISTRATION = 20
const MAX_THEME_ID_LENGTH = 100
const MAX_THEME_LABEL_LENGTH = 100
const MAX_THEME_TOKENS = 200
const MAX_TOKEN_KEY_LENGTH = 100
const MAX_TOKEN_VALUE_LENGTH = 500
const DOT_SEGMENT_PATTERN = /(^|\/)\.\.?(\/|$)/

// Object-property names that would let a contributed id reach the prototype
// chain instead of an own data property when used as a bracket-assignment
// key (e.g. `THEMES[id] = theme`).
const UNSAFE_OBJECT_KEYS = new Set(['__proto__', 'prototype', 'constructor'])

/** True if any character is a C0/DEL control code (codepoints 0-31 or 127).
 *  Written as a codepoint scan rather than a regex control-char class, which
 *  is easy to mis-render or mis-escape. */
function hasControlCharacter(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i)
    if (code <= 31 || code === 127) return true
  }
  return false
}

/** A non-empty string, already trimmed, within a bounded length. Used for
 *  every human-authored string this seam accepts (names, labels, theme ids,
 *  token keys/values) so none can smuggle padding or grow unbounded. */
function isBoundedTrimmedString(value: unknown, maxLength: number): value is string {
  return (
    typeof value === 'string' &&
    value.length > 0 &&
    value.length <= maxLength &&
    value === value.trim() &&
    !hasControlCharacter(value)
  )
}

function isCanonicalSameOriginPath(value: unknown): value is string {
  if (typeof value !== 'string') return false
  if (value.length === 0 || value.length > MAX_CANVAS_PATH_LENGTH) return false
  if (value !== value.trim()) return false
  if (/\s/.test(value)) return false
  if (hasControlCharacter(value)) return false
  if (!value.startsWith('/')) return false
  if (value.includes('//')) return false
  if (value.length > 1 && value.endsWith('/')) return false
  if (value.includes('\\')) return false
  if (value.includes('?')) return false
  if (value.includes('#')) return false
  if (value.includes('*')) return false
  if (value.includes(':')) return false
  if (value.includes('%')) return false
  if (DOT_SEGMENT_PATTERN.test(value)) return false
  return true
}

function isExtensionNavItem(value: unknown): value is ExtensionNavItem {
  if (typeof value !== 'object' || value === null) return false
  const item = value as Record<string, unknown>
  return (
    isCanonicalSameOriginPath(item.href) &&
    isBoundedTrimmedString(item.label, MAX_LABEL_LENGTH) &&
    isRenderableComponentType(item.icon)
  )
}

/** A plain (non-null, non-array) object — the shape every record-like
 *  contribution (slots, a theme, a theme's tokens) must have. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

const REACT_COMPONENT_TYPE_TAGS = new Set([
  Symbol.for('react.forward_ref'),
  Symbol.for('react.lazy'),
  Symbol.for('react.memo'),
])

/** Component types accepted by this seam: ordinary function/class components
 *  plus React's renderable wrapper objects. Arbitrary objects are not valid JSX
 *  element types and must be rejected before KernelNav tries to render them. */
function isRenderableComponentType(value: unknown): value is ComponentType {
  if (typeof value === 'function') return true
  if (typeof value !== 'object' || value === null) return false
  const tag = (value as { $$typeof?: unknown }).$$typeof
  return typeof tag === 'symbol' && REACT_COMPONENT_TYPE_TAGS.has(tag)
}

function isExtensionRoute(value: unknown): value is ExtensionRoute {
  if (typeof value !== 'object' || value === null) return false
  const route = value as Record<string, unknown>
  return isCanonicalSameOriginPath(route.path) && isValidElement(route.element)
}

// The exact set of chrome slot keys this seam understands. A slots object
// with any other key, or a non-plain-object slots value, is rejected
// outright rather than silently ignoring the unknown key.
const SUPPORTED_SLOT_KEYS = new Set<keyof ExtensionSlots>(['nav', 'intel', 'voice'])

function isExtensionSlots(value: unknown): value is ExtensionSlots {
  if (!isPlainObject(value)) return false
  for (const key of Object.keys(value)) {
    if (!SUPPORTED_SLOT_KEYS.has(key as keyof ExtensionSlots)) return false
    const component = value[key]
    if (component !== undefined && !isRenderableComponentType(component)) return false
  }
  return true
}

/** A contributed theme's `tokens` map: a plain object of bounded, non-empty,
 *  trimmed string keys to bounded, non-empty, trimmed string values, with no
 *  key that could reach an object's prototype chain. */
function isSafeThemeTokens(value: unknown): value is Record<string, string> {
  if (!isPlainObject(value)) return false
  const entries = Object.entries(value)
  if (entries.length > MAX_THEME_TOKENS) return false
  for (const [key, tokenValue] of entries) {
    if (UNSAFE_OBJECT_KEYS.has(key)) return false
    if (!isBoundedTrimmedString(key, MAX_TOKEN_KEY_LENGTH)) return false
    if (!isBoundedTrimmedString(tokenValue, MAX_TOKEN_VALUE_LENGTH)) return false
  }
  return true
}

/** Runtime shape-check for one entry of a register module's `themes` list,
 *  applied before the theme ever reaches `registerTheme`. */
function isValidContributedTheme(value: unknown): value is AceTheme {
  if (!isPlainObject(value)) return false
  const theme = value as Record<string, unknown>
  if (!isBoundedTrimmedString(theme.id, MAX_THEME_ID_LENGTH)) return false
  if (UNSAFE_OBJECT_KEYS.has(theme.id)) return false
  if (!isBoundedTrimmedString(theme.label, MAX_THEME_LABEL_LENGTH)) return false
  if (theme.tokens !== undefined && !isSafeThemeTokens(theme.tokens)) return false
  return true
}

/** Runtime shape-check for a register module's default export. */
export function isExtensionUI(value: unknown): value is ExtensionUI {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  if (!isBoundedTrimmedString(v.name, MAX_NAME_LENGTH)) return false
  if (v.routes !== undefined) {
    if (!Array.isArray(v.routes)) return false
    if (v.routes.length > MAX_ROUTES_PER_REGISTRATION) return false
    if (!v.routes.every(isExtensionRoute)) return false
    const paths = v.routes.map((route) => route.path)
    if (new Set(paths).size !== paths.length) return false
  }
  if (v.navItems !== undefined) {
    if (!Array.isArray(v.navItems)) return false
    if (v.navItems.length > MAX_NAV_ITEMS_PER_REGISTRATION) return false
    if (!v.navItems.every(isExtensionNavItem)) return false
    const hrefs = v.navItems.map((item) => item.href)
    if (new Set(hrefs).size !== hrefs.length) return false
  }
  if (v.themes !== undefined) {
    if (!Array.isArray(v.themes)) return false
    if (v.themes.length > MAX_THEMES_PER_REGISTRATION) return false
    if (!v.themes.every(isValidContributedTheme)) return false
    const ids = v.themes.map((theme) => theme.id)
    if (new Set(ids).size !== ids.length) return false
  }
  if (v.slots !== undefined && !isExtensionSlots(v.slots)) return false
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

/** Pure slot resolution — first contribution (composition order) that fills the
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

const installedSolutionModules = import.meta.glob(
  '../solutions/*/register.{ts,tsx}',
  { eager: true },
) as Record<string, unknown>

/** All registered external extension UIs, in deterministic order. */
export const extensions: readonly ExtensionUI[] =
  collectExtensions(registerModules)

/** Installed first-party solution UIs, composed before external extensions. */
export const installedSolutions: readonly ExtensionUI[] =
  collectExtensions(installedSolutionModules)

/** All Canvas contributions in deterministic precedence order. */
export const canvasContributions: readonly ExtensionUI[] = [
  ...installedSolutions,
  ...extensions,
]

// Fold contributed themes into the design-system theme registry once, at
// module load — main.tsx imports this module before first render, so
// themes are available wherever THEMES/applyTheme is consumed.
for (const ext of canvasContributions) {
  for (const theme of ext.themes ?? []) registerTheme(theme)
}

/** Deterministic first-owner route collection. Kernel paths can be reserved by
 *  the host before contribution routes are rendered. */
export function collectRoutes(
  contributions: readonly ExtensionUI[],
  reservedPaths: Iterable<string> = [],
): ExtensionRoute[] {
  const seen = new Set(reservedPaths)
  const routes: ExtensionRoute[] = []
  for (const contribution of contributions) {
    for (const route of contribution.routes ?? []) {
      if (seen.has(route.path)) continue
      seen.add(route.path)
      routes.push(route)
    }
  }
  return routes
}

/** All valid solution/extension routes in deterministic precedence order. */
export function canvasRoutes(
  reservedPaths: Iterable<string> = [],
): ExtensionRoute[] {
  return collectRoutes(canvasContributions, reservedPaths)
}

/** Additive navigation with duplicate hrefs rejected after first ownership. */
export function collectNavItems(
  contributions: readonly ExtensionUI[],
  reservedHrefs: Iterable<string> = [],
): ExtensionNavItem[] {
  const seen = new Set(reservedHrefs)
  const items: ExtensionNavItem[] = []
  for (const contribution of contributions) {
    for (const item of contribution.navItems ?? []) {
      if (seen.has(item.href)) continue
      seen.add(item.href)
      items.push(item)
    }
  }
  return items
}

/** All valid additive navigation contributions in deterministic order. */
export function canvasNavItems(
  reservedHrefs: Iterable<string> = [],
): ExtensionNavItem[] {
  return collectNavItems(canvasContributions, reservedHrefs)
}

/** The component registered for a chrome slot, or undefined (kernel
 *  default applies). */
export function extensionSlot<K extends keyof ExtensionSlots>(
  slot: K,
): ExtensionSlots[K] | undefined {
  return resolveSlot(canvasContributions, slot)
}
