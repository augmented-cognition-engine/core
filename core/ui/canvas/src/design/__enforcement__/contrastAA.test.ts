// core/ui/canvas/src/design/__enforcement__/contrastAA.test.ts
//
// Fails the build if any documented text-on-surface combination in the
// engineered-light direction falls below WCAG AA contrast thresholds.
// Currently checks the base direction's critical ink × surface pairs;
// future themes that override role tokens should add their own checks
// here (or extend this to walk themes via shared.ts).
//
// Thresholds (WCAG 2.1):
//   - 4.5:1 — 1.4.3 Contrast (Minimum) for body text < 18.66px
//   - 3.0:1 — 1.4.3 large text (≥ 18.66px or ≥ 14pt bold)
//             1.4.11 Non-text Contrast for UI components, focus states,
//             chips, badges, button surfaces, status pills
//
// `ink-faint` is excluded from the checks. Per WCAG 1.4.3 it's
// reserved for "incidental" text only — placeholder fadeouts, disabled
// icon hints. The token's job is to read as "not interactive"; making
// it AA-compliant would defeat that purpose. Surfaces using ink-faint
// for essential content are wrong by design.
//
// Accent / semantic colors (success, warning, danger, tone-medium) use
// the 3.0:1 threshold because in ACE they appear as:
//   - chip / badge backgrounds (UI components)
//   - the chip / badge tone color paired with ink-on-chip
//   - byline accent color (large-text labels in Eyebrow / RosterRow)
// They are NEVER used as long-form body prose color.
//
// WCAG-2.x contrast formula:
//   1. Convert sRGB hex → linear RGB (gamma-corrected)
//   2. Compute relative luminance: L = 0.2126·R + 0.7152·G + 0.0722·B
//   3. Contrast ratio: (Lₗ + 0.05) / (Lₛ + 0.05) where Lₗ ≥ Lₛ
//
// References: https://www.w3.org/TR/WCAG21/#contrast-minimum
import { describe, expect, it } from 'vitest'

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const r = parseInt(full.substring(0, 2), 16)
  const g = parseInt(full.substring(2, 4), 16)
  const b = parseInt(full.substring(4, 6), 16)
  return [r, g, b]
}

function sRgbChannelToLinear(c: number): number {
  const s = c / 255
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex)
  const [rl, gl, bl] = [r, g, b].map(sRgbChannelToLinear)
  return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl
}

export function contrastRatio(fg: string, bg: string): number {
  const lFg = relativeLuminance(fg)
  const lBg = relativeLuminance(bg)
  const lighter = Math.max(lFg, lBg)
  const darker = Math.min(lFg, lBg)
  return (lighter + 0.05) / (darker + 0.05)
}

/** Engineered-light direction Layer 2 role-token values, mirrored
 *  from tokens.css. Update here when the role tokens change. */
const COLORS = {
  surfaceCanvas: '#FAFAFA',
  surfaceRaised: '#FFFFFF',
  surfaceRecessed: '#F4F4F4',
  surfaceTint: '#E8F2FF',
  ink: '#171717',
  inkStrong: '#0A0A0A',
  inkSoft: '#525252',
  inkMuted: '#737373',
  inkFaint: '#A3A3A3',
  accent: '#0070F3',
  accentInk: '#FFFFFF',
  success: '#16A34A',
  warning: '#D97706',
  danger: '#DC2626',
  toneMedium: '#B07735',  // sync with tokens.css --ace-tone-medium
}

interface ContrastCheck {
  name: string
  fg: string
  bg: string
  /** Minimum contrast ratio required. 4.5 for body, 3.0 for large/UI. */
  min: number
}

const CHECKS: ContrastCheck[] = [
  // Body text on the three main surfaces
  { name: 'ink on surface-canvas', fg: COLORS.ink, bg: COLORS.surfaceCanvas, min: 4.5 },
  { name: 'ink on surface-raised', fg: COLORS.ink, bg: COLORS.surfaceRaised, min: 4.5 },
  { name: 'ink on surface-recessed', fg: COLORS.ink, bg: COLORS.surfaceRecessed, min: 4.5 },
  { name: 'ink on surface-tint', fg: COLORS.ink, bg: COLORS.surfaceTint, min: 4.5 },
  { name: 'ink-strong on surface-canvas', fg: COLORS.inkStrong, bg: COLORS.surfaceCanvas, min: 4.5 },
  { name: 'ink-strong on surface-raised', fg: COLORS.inkStrong, bg: COLORS.surfaceRaised, min: 4.5 },

  // Secondary body text
  { name: 'ink-soft on surface-canvas', fg: COLORS.inkSoft, bg: COLORS.surfaceCanvas, min: 4.5 },
  { name: 'ink-soft on surface-raised', fg: COLORS.inkSoft, bg: COLORS.surfaceRaised, min: 4.5 },
  { name: 'ink-soft on surface-recessed', fg: COLORS.inkSoft, bg: COLORS.surfaceRecessed, min: 4.5 },

  // Muted text — Eyebrows, microcopy at 10–11px. Still body-rated, must hit 4.5.
  { name: 'ink-muted on surface-canvas', fg: COLORS.inkMuted, bg: COLORS.surfaceCanvas, min: 4.5 },
  { name: 'ink-muted on surface-raised', fg: COLORS.inkMuted, bg: COLORS.surfaceRaised, min: 4.5 },

  // ink-faint excluded — see header comment. Reserved for incidental
  // UI shadow text per WCAG 1.4.3 exemption.

  // Accent — large-text labels and UI components (chips, focus rings,
  // byline accent). Uses WCAG 1.4.11 UI-component threshold (3.0).
  { name: 'accent on surface-canvas (UI)', fg: COLORS.accent, bg: COLORS.surfaceCanvas, min: 3.0 },
  { name: 'accent on surface-raised (UI)', fg: COLORS.accent, bg: COLORS.surfaceRaised, min: 3.0 },
  { name: 'accent-ink on accent (button)', fg: COLORS.accentInk, bg: COLORS.accent, min: 4.5 },

  // Semantic colors — used as chip/badge tone and large-text labels in
  // status pills, severity findings. UI-component threshold (3.0).
  { name: 'success on surface-canvas (UI)', fg: COLORS.success, bg: COLORS.surfaceCanvas, min: 3.0 },
  { name: 'warning on surface-canvas (UI)', fg: COLORS.warning, bg: COLORS.surfaceCanvas, min: 3.0 },
  { name: 'danger on surface-canvas (UI)', fg: COLORS.danger, bg: COLORS.surfaceCanvas, min: 4.5 },
  { name: 'tone-medium on surface-canvas (UI)', fg: COLORS.toneMedium, bg: COLORS.surfaceCanvas, min: 3.0 },
]

describe('design-system enforcement: WCAG AA contrast', () => {
  for (const check of CHECKS) {
    it(`${check.name} meets ${check.min}:1`, () => {
      const ratio = contrastRatio(check.fg, check.bg)
      expect(
        ratio,
        `${check.fg} on ${check.bg} = ${ratio.toFixed(2)}:1 (need ${check.min}:1)`,
      ).toBeGreaterThanOrEqual(check.min)
    })
  }

  it('contrast formula sanity check: black on white = 21:1', () => {
    expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21, 1)
  })

  it('contrast formula sanity check: white on white = 1:1', () => {
    expect(contrastRatio('#FFFFFF', '#FFFFFF')).toBeCloseTo(1, 2)
  })
})
