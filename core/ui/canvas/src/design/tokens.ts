// core/ui/canvas/src/design/tokens.ts
//
// TypeScript-side mirror of design/tokens.css. Components that need to
// pass token values to non-CSS consumers (SVG `fill`, JS computed colors,
// inline `style` props for things React can't pass through CSS — like
// transforms with runtime values) use these named exports.
//
// THE RULE: in JSX/TSX, prefer `style={{ color: 'var(--ace-ink)' }}` over
// importing `INK` from here. Use these only when a CSS var won't reach
// the consumer.
//
// CONTRACT WITH tokens.css:
//   - Every Layer 1 primitive value here (WARM, COOL, SEMANTIC, RADIUS,
//     SPACE, TEXT_SIZE, LEADING, TRACK, WEIGHT) MUST equal the
//     corresponding --ace-* literal in tokens.css.
//   - Every Layer 2/3 role/semantic export here MUST be a `var(--ace-*)`
//     string referencing a CSS var that exists in tokens.css.
//   - When a CSS token changes value or is added/removed, this file
//     updates in the same commit. The tokens.css file is the source of
//     truth; this file is the JS-side mirror.
//
// VISUAL DIRECTION (current, not permanent): engineered-light. Bright
// neutral canvas, single electric-blue accent (#0070F3), hairline-shadow
// elevation, 8px buttons, 12px cards. See docs/design-system.md.

// ---------------------------------------------------------------------------
// Layer 0 — Foundations
// ---------------------------------------------------------------------------

export const FONT_SANS =
  '-apple-system, BlinkMacSystemFont, "Inter", "SF Pro Text", system-ui, "Segoe UI", Roboto, sans-serif'
export const FONT_SERIF =
  '"GT Alpina", "Tiempos Text", Georgia, "Times New Roman", serif'
export const FONT_MONO =
  'ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace'

export const BASE_UNIT = 4
export const RADIUS = {
  sm: 4,     // status badges, inline pips
  base: 8,   // buttons, inputs
  md: 10,    // tooltips, menus
  lg: 12,    // cards, popovers, dialogs, sections
  pill: 9999,
} as const

// ---------------------------------------------------------------------------
// Layer 1 — Primitive scales (raw hex; prefer CSS vars where possible)
// ---------------------------------------------------------------------------

export const WARM = {
  '50':  '#fbf9f4',
  '100': '#f4efe5',
  '150': '#ede6d3',
  '200': '#e2d8be',
  '300': '#c9bca0',
  '400': '#a99c80',
  '500': '#8a7e64',
  '600': '#645a47',
  '700': '#443e31',
  '800': '#2b2820',
  '850': '#1f1d17',
  '900': '#16140f',
  '950': '#0f0e0a',
} as const

export const COOL = {
  '50':  '#fafafa',
  '100': '#f1f1f2',
  '200': '#e2e2e4',
  '300': '#c5c5c9',
  '400': '#9a9aa0',
  '500': '#6f6f76',
  '600': '#4a4a50',
  '700': '#2f2f33',
  '800': '#1d1d20',
  '900': '#111114',
} as const

export const SEMANTIC = {
  success: '#16A34A',
  warning: '#D97706',
  danger:  '#DC2626',
  toneMedium: '#B07735',  // severity-tone middle stop (ochre) — WCAG 3:1 on canvas
  successSoft:    'rgba(22, 163, 74, 0.10)',
  warningSoft:    'rgba(217, 119, 6, 0.10)',
  dangerSoft:     'rgba(220, 38, 38, 0.10)',
  toneMediumSoft: 'rgba(176, 119, 53, 0.10)',
} as const

// Single chromatic accent — Vercel electric blue. The only chromatic
// chrome in the engineered-light direction; everything else is
// neutral. Theme `voice-accent` defaults to this and is the override
// surface for branded extension themes (each retints it to its own accent).
export const ACCENT = {
  base:   '#0070F3',
  hover:  '#0061D5',
  soft:   '#E8F2FF',
  tint:   'rgba(0, 112, 243, 0.10)',
  ink:    '#FFFFFF',
} as const

// Multi-hue color scales — Layer 1 primitives for decorative use.
// 8 hues × 6 weights (50/100/300/500/700/900). Tailwind-aligned values.
// Use pattern: pick a hue at -100 (background) + -700 (text) for
// soft pill / chip composition. Hits WCAG AA across all 8 hues.
//
// Not theme-overridable. Themes shift voice + brand; decorative
// categorization stays consistent across themes.
export const PALETTE = {
  blue:   { 50: '#EFF6FF', 100: '#DBEAFE', 300: '#93C5FD', 500: '#3B82F6', 700: '#1D4ED8', 900: '#1E3A8A' },
  amber:  { 50: '#FFFBEB', 100: '#FEF3C7', 300: '#FCD34D', 500: '#F59E0B', 700: '#B45309', 900: '#78350F' },
  red:    { 50: '#FEF2F2', 100: '#FEE2E2', 300: '#FCA5A5', 500: '#EF4444', 700: '#B91C1C', 900: '#7F1D1D' },
  green:  { 50: '#F0FDF4', 100: '#DCFCE7', 300: '#86EFAC', 500: '#22C55E', 700: '#15803D', 900: '#14532D' },
  purple: { 50: '#FAF5FF', 100: '#F3E8FF', 300: '#D8B4FE', 500: '#A855F7', 700: '#7E22CE', 900: '#581C87' },
  teal:   { 50: '#F0FDFA', 100: '#CCFBF1', 300: '#5EEAD4', 500: '#14B8A6', 700: '#0F766E', 900: '#134E4A' },
  pink:   { 50: '#FDF2F8', 100: '#FCE7F3', 300: '#F9A8D4', 500: '#EC4899', 700: '#BE185D', 900: '#831843' },
  slate:  { 50: '#F8FAFC', 100: '#F1F5F9', 300: '#CBD5E1', 500: '#64748B', 700: '#334155', 900: '#0F172A' },
} as const

export type PaletteHue = keyof typeof PALETTE
export type PaletteWeight = keyof (typeof PALETTE)['blue']

export const SPACE = {
  0: 0, 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48, 16: 64,
} as const

export const TEXT_SIZE = {
  xs: 10, sm: 11, base: 12, md: 13, lg: 15, xl: 17, '2xl': 22, '3xl': 28, '4xl': 36,
} as const

export const LEADING = {
  tight: 1.2, snug: 1.35, normal: 1.5, relaxed: 1.7,
} as const

export const TRACK = {
  tight: '-0.01em',
  normal: '0',
  wide: '0.06em',
  wider: '0.12em',
  widest: '0.16em',
} as const

export const WEIGHT = {
  regular: 400, medium: 500, semibold: 600, bold: 700,
} as const

// ---------------------------------------------------------------------------
// Layer 2 — Role tokens, expressed as CSS var() refs.
// Use these in component style props so theme switching at the :root
// level propagates automatically.
// ---------------------------------------------------------------------------

export const SURFACE = {
  canvas:    'var(--ace-surface-canvas)',     // page / canvas ground
  raised:    'var(--ace-surface-raised)',     // cards, popovers
  recessed:  'var(--ace-surface-recessed)',   // highlight bands, captured-this-turn chips
  tint:      'var(--ace-surface-tint)',       // accent-tinted bg (convergence beat)
  // Legacy aliases — kept so older components keep resolving.
  card:       'var(--ace-surface-card)',
  cardStrong: 'var(--ace-surface-card-strong)',
  cardDim:    'var(--ace-surface-card-dim)',
  elevated:   'var(--ace-surface-elevated)',
} as const

export const INK = {
  default: 'var(--ace-ink)',
  strong:  'var(--ace-ink-strong)',
  soft:    'var(--ace-ink-soft)',
  muted:   'var(--ace-ink-muted)',
  faint:   'var(--ace-ink-faint)',
} as const

export const LINE = {
  default: 'var(--ace-line)',
  soft: 'var(--ace-line-soft)',
  strong: 'var(--ace-line-strong)',
} as const

export const SHADOW = {
  sm:        'var(--ace-shadow-sm)',
  card:      'var(--ace-shadow-card)',         // hairline-ring + soft drop (engineered-light signature)
  cardHover: 'var(--ace-shadow-card-hover)',   // ring strengthens + drop grows on hover
  popover:   'var(--ace-shadow-popover)',
  banner:    'var(--ace-shadow-banner)',
  // Legacy aliases.
  md:   'var(--ace-shadow-md)',
  lg:   'var(--ace-shadow-lg)',
  aged: 'var(--ace-shadow-aged)',
} as const

export const FOCUS_RING = 'var(--ace-focus-ring)'

// ---------------------------------------------------------------------------
// Layer 3 — Semantic tokens
// ---------------------------------------------------------------------------

export const SEMANTIC_TOKENS = {
  decisionZoneBg:    'var(--ace-decision-zone-bg)',
  predictionTileBg:  'var(--ace-prediction-tile-bg)',
  captureSummaryBg:  'var(--ace-capture-summary-bg)',
  northStarBg:       'var(--ace-north-star-bg)',
  northStarLine:     'var(--ace-north-star-line)',
  northStarLabel:    'var(--ace-north-star-label)',
  synthesisPaper:    'var(--ace-synthesis-paper)',
  synthesisDivider:  'var(--ace-synthesis-divider)',
  sketchChalkDim:    'var(--ace-sketch-chalk-dim)',
  sketchChalkBright: 'var(--ace-sketch-chalk-bright)',
} as const

// ---------------------------------------------------------------------------
// Motion
// ---------------------------------------------------------------------------

export const MOTION = {
  snap:  'var(--ace-motion-snap)',   //  90ms  focus rings, small reveals
  micro: 'var(--ace-motion-micro)',  // 120ms  hover state colors/borders
  lift:  'var(--ace-motion-lift)',   // 180ms  card hover, popover open
  base:  'var(--ace-motion-base)',   // 220ms  legacy alias
  flow:  'var(--ace-motion-flow)',   // 420ms  contribution arrival, brief-me-back lede
  land:  'var(--ace-motion-land)',   // 680ms  convergence beat lock-in (theatrical, once)
  pulse: 'var(--ace-motion-pulse)',  //2400ms  sentinel/calibration loop (ambient breathing)
  easeOut:     'var(--ace-ease-out)',
  easeOrganic: 'var(--ace-ease-organic)',
  easeStage:   'var(--ace-ease-stage)',
  easeSnap:    'var(--ace-ease-snap)',  // legacy alias for easeStage
} as const

// ---------------------------------------------------------------------------
// Convenience type — for primitives that take a typography role.
// ---------------------------------------------------------------------------

export type TextSizeKey = keyof typeof TEXT_SIZE
export type SpaceKey = keyof typeof SPACE
