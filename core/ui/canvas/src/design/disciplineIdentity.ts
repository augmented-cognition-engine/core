// Discipline identity + canvas paper-card tokens.
//
// See: docs/superpowers/specs/2026-05-25-canvas-team-build-visual-design.md
// (§4.1 identity table · §4.3 color tokens · §7 client-side recipe derivation)
//
// Pure module: no React, no DOM. Safe to import from shape utils, hooks, tests.

export type DisciplineIdentity = {
  color: string;
  glyph: string;
  role: string;
};

// 14 entries: 13 named disciplines + the "voice" fallback.
// Hex codes, glyphs, and role labels match spec §4.1 exactly.
export const DISCIPLINES: Record<string, DisciplineIdentity> = {
  architecture:     { color: '#5B7A99', glyph: '⌂', role: 'The structuralist' },
  security:         { color: '#8C3A3A', glyph: '◉', role: 'The skeptic' },
  data:             { color: '#5F7A4F', glyph: '≈', role: 'The reader' },
  product_strategy: { color: '#C49348', glyph: '◆', role: 'The strategist' },
  ux:               { color: '#C26648', glyph: '◐', role: 'The empath' },
  performance:      { color: '#B07238', glyph: '→', role: 'The optimizer' },
  ai_ml:            { color: '#B47274', glyph: '✦', role: 'The pattern-watcher' },
  testing:          { color: '#4F6878', glyph: '✓', role: 'The doubter' },
  devops:           { color: '#967536', glyph: '⚙', role: 'The operator' },
  observability:    { color: '#857A6E', glyph: '◎', role: 'The witness' },
  scale:            { color: '#3D6E72', glyph: '↗', role: 'The forecaster' },
  compliance:       { color: '#A89055', glyph: '§', role: 'The custodian' },
  accessibility:    { color: '#789578', glyph: '❋', role: 'The advocate' },
  voice:            { color: '#8A8175', glyph: '·', role: 'The voice' },
};

/**
 * Case-insensitive, trim-tolerant lookup. Unknown lens names fall back to
 * the parchment "voice" identity so the surface never renders empty.
 */
export function disciplineIdentity(lensName: string): DisciplineIdentity {
  if (typeof lensName !== 'string') return DISCIPLINES.voice;
  const key = lensName.trim().toLowerCase();
  return DISCIPLINES[key] ?? DISCIPLINES.voice;
}

// Inline pretty-print for lens names. `ai_ml` is a special case because the
// generic title-cased "Ai Ml" reads as a typo; everything else just becomes
// underscores → spaces, with each word capitalized.
function prettyLensName(name: string): string {
  const key = name.trim().toLowerCase();
  if (key === 'ai_ml') return 'AI/ML';
  return key
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

/**
 * Client-side recipe label derivation. Spec §7 calls this out as a
 * defer-and-iterate move — backend payloads don't carry `recipe_name` yet,
 * so we synthesize from the lens name with a simple suffix table.
 *
 * Examples:
 *   recipeLabelFor('security')       → 'Security audit'
 *   recipeLabelFor('ux')             → 'UX assessment'      (special UX case → see prettyLensName)
 *   recipeLabelFor('architecture')   → 'Architecture review'
 *   recipeLabelFor('data')           → 'Data analysis'
 *   recipeLabelFor('ai_ml')          → 'AI/ML analysis'
 */
export function recipeLabelFor(lensName: string): string {
  const key = (typeof lensName === 'string' ? lensName : '').trim().toLowerCase();
  const pretty = prettyLensName(key);

  let suffix: string;
  if (key === 'security' || key === 'compliance') {
    suffix = ' audit';
  } else if (key === 'ux' || key === 'accessibility') {
    suffix = ' assessment';
  } else if (key === 'architecture' || key === 'testing') {
    suffix = ' review';
  } else {
    suffix = ' analysis';
  }

  return `${pretty}${suffix}`;
}

/**
 * Deterministic per-card rotation jitter, in degrees, within [-0.6, 0.6].
 * Seeded from `${buildRunId}:${lens}` via a small integer hash so re-renders
 * of the same card produce the same angle (no "wobbling on update").
 *
 * Pure: same inputs always return the same output.
 */
export function jitterFor(buildRunId: string, lens: string): number {
  const seed = `${buildRunId}:${lens}`;
  // FNV-1a 32-bit hash — small, well-distributed, no dependencies.
  let h = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    // 32-bit FNV prime multiplication
    h = Math.imul(h, 0x01000193);
  }
  // Normalize to unsigned 32-bit, then to [0, 1).
  const unit = (h >>> 0) / 0x100000000;
  // Map [0, 1) → [-0.6, 0.6].
  return unit * 1.2 - 0.6;
}

// Paper-card design tokens. Spec §4.3. Two complementary sets:
//
//   - dark canvas → light/cream paper cards (parchment on chalkboard)
//   - light canvas → dark/walnut paper cards (kraft on white desk)
//
// The discipline accent colors (in DISCIPLINES above) stay the same in both
// modes — they're mid-luminance jewel tones that read on either surface.
// Only the paper, ink, shadow, and arrow values flip.

export type CanvasMode = 'light' | 'dark';

export type CanvasTokens = {
  paperBg: string;
  paperBgGold: string;
  paperBgDim: string;
  paperInk: string;
  paperInkSoft: string;
  paperMuted: string;
  paperGoldMuted: string;
  cardShadow: string;
  cardShadowHover: string;
  cardShadowDim: string;
  synthesisShadow: string;
  cardRadius: string;
  paperDivider: string;
  paperDividerGold: string;
  paperFocusRing: string;
  arrowChalk: string;
  arrowChalkBright: string;
};

// DARK CANVAS variant — cream parchment cards on a dark canvas.
// Eye reads: polaroids pinned to a chalkboard / sticky-notes on a dark felt.
const TOKENS_DARK: CanvasTokens = {
  paperBg:            '#EDE3CC',
  paperBgGold:        '#F4ECD5',
  paperBgDim:         '#D9CDB4',

  paperInk:           '#1F1A14',
  paperInkSoft:       '#3F3830',
  paperMuted:         '#5A4F3F',
  paperGoldMuted:     '#6B5A35',

  cardShadow:         '0 8px 24px rgba(0, 0, 0, 0.45), 0 1px 0 rgba(0, 0, 0, 0.10) inset',
  cardShadowHover:    '0 12px 32px rgba(0, 0, 0, 0.52), 0 1px 0 rgba(0, 0, 0, 0.12) inset',
  cardShadowDim:      '0 4px 16px rgba(0, 0, 0, 0.32), 0 1px 0 rgba(0, 0, 0, 0.08) inset',
  synthesisShadow:    '0 14px 40px rgba(0, 0, 0, 0.55), 0 1px 0 rgba(0, 0, 0, 0.12) inset, 0 0 0 1px rgba(107, 90, 53, 0.18)',
  cardRadius:         '6px',

  paperDivider:       'rgba(31, 26, 20, 0.10)',
  paperDividerGold:   'rgba(31, 26, 20, 0.14)',
  paperFocusRing:     'rgba(31, 26, 20, 0.32)',

  arrowChalk:         'rgba(232, 220, 200, 0.55)',  // warm chalk on dark canvas
  arrowChalkBright:   'rgba(232, 220, 200, 0.85)',
};

// LIGHT CANVAS variant — walnut/kraft paper cards on a light canvas.
// Eye reads: dark-stained index cards on a white desk / inked cards.
// Surface inverts (dark paper, cream ink); discipline accents unchanged.
const TOKENS_LIGHT: CanvasTokens = {
  paperBg:            '#2A241D',  // walnut/coffee — strong contrast on white
  paperBgGold:        '#332918',  // synthesis: slightly warmer/gold-shifted dark
  paperBgDim:         '#1F1A14',  // aged: deeper still

  paperInk:           '#EDE3CC',  // cream text on dark card
  paperInkSoft:       '#D8CFC2',
  paperMuted:         '#9C9286',
  paperGoldMuted:     '#B59A6A',

  cardShadow:         '0 6px 18px rgba(0, 0, 0, 0.18), 0 1px 0 rgba(255, 255, 255, 0.06) inset',
  cardShadowHover:    '0 10px 26px rgba(0, 0, 0, 0.22), 0 1px 0 rgba(255, 255, 255, 0.06) inset',
  cardShadowDim:      '0 3px 12px rgba(0, 0, 0, 0.14), 0 1px 0 rgba(255, 255, 255, 0.04) inset',
  synthesisShadow:    '0 12px 32px rgba(0, 0, 0, 0.28), 0 1px 0 rgba(255, 255, 255, 0.06) inset, 0 0 0 1px rgba(181, 154, 106, 0.30)',
  cardRadius:         '6px',

  paperDivider:       'rgba(237, 227, 204, 0.10)',  // cream alpha on dark card
  paperDividerGold:   'rgba(237, 227, 204, 0.14)',
  paperFocusRing:     'rgba(237, 227, 204, 0.32)',

  arrowChalk:         'rgba(31, 26, 20, 0.45)',     // dark ink on light canvas
  arrowChalkBright:   'rgba(31, 26, 20, 0.75)',
};

/**
 * Return the token set for a given canvas color mode. The shape utils call
 * this at render time after reading tldraw's `colorScheme` user preference.
 */
export function canvasTokens(mode: CanvasMode): CanvasTokens {
  return mode === 'light' ? TOKENS_LIGHT : TOKENS_DARK;
}

/**
 * Backwards-compat alias. Pre-multi-mode callers imported `CANVAS_TOKENS`
 * directly; they get the dark variant. New callers should use
 * `canvasTokens(mode)` to respect the canvas color scheme.
 */
export const CANVAS_TOKENS: CanvasTokens = TOKENS_DARK;
