// frontend/src/design/themes/index.ts
//
// Theme registry. A theme is a coherent override of Layer 2 + Layer 3
// tokens (and any custom semantic additions) on top of the base ACE
// design system. Branded extension surfaces are themes that ride on
// ACE's primitives. The kernel ships the base theme; extensions
// contribute their own themes through the ext seam
// (src/app/ext/registry.tsx → registerTheme below) — the kernel never
// imports an extension theme by path.
//
// Per [[feedback-theme-not-flavor]]: we call them "themes" / "extensions",
// never "flavors."
//
// Activation: a theme sets CSS custom properties on a host element
// (typically `<html data-theme-id="...">` or scoped to a subtree).
// Components keep referencing the same role / semantic tokens; the theme
// changes what those tokens resolve to.

export interface AceTheme {
  /** Stable identifier — drives the data-theme attribute. */
  id: string
  /** Human-readable label for diagnostics / showcase. */
  label: string
  /** Optional Layer 2/3 overrides keyed by token name (without --
   *  prefix). Applied when the theme is active. Empty = pure base. */
  tokens?: Record<string, string>
}

import { baseTheme } from './base'

export const THEMES: Record<string, AceTheme> = {
  base: baseTheme,
}

/**
 * Register a theme contributed at runtime — the extension-UI seam
 * (src/app/ext/registry.tsx) folds extension themes in through this at
 * module-load time, before first render. Registering an existing id
 * replaces it (an extension may deliberately re-skin a built-in).
 */
export function registerTheme(theme: AceTheme): void {
  THEMES[theme.id] = theme
}

/**
 * Apply a theme's token overrides to the document's <html> element. No-op
 * for the base theme. Calling this with a different id at runtime swaps
 * the theme atomically — components observe the change through CSS var
 * resolution, no re-render needed.
 */
export function applyTheme(themeId: string): void {
  if (typeof document === 'undefined') return
  const theme = THEMES[themeId] ?? baseTheme
  const root = document.documentElement
  root.setAttribute('data-theme-id', theme.id)
  // Clear any previously-set ace-* inline overrides before applying new ones
  // so theme switches don't leave stale values behind.
  for (const name of Array.from(root.style)) {
    if (typeof name === 'string' && name.startsWith('--ace-')) {
      root.style.removeProperty(name)
    }
  }
  if (theme.tokens !== undefined) {
    for (const [name, value] of Object.entries(theme.tokens)) {
      root.style.setProperty(`--${name.startsWith('ace-') ? name : `ace-${name}`}`, value)
    }
  }
}

export { baseTheme }
