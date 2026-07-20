// core/ui/canvas/src/design/components/Icon.tsx
//
// Curated icon primitive wrapping a typed enum of Phosphor Icons.
// Distinct from <Glyph>:
//   - Glyph: discipline marker in a tinted circle (architecture, security,
//            etc.) — partnership-specific identity affordance
//   - Icon:  generic UI iconography (close, arrow, check, search) — chrome
//            that doesn't carry partnership meaning
//
// The icon set is intentionally narrow. Each new icon must be added to
// the ICONS map before it can be used; that gate means we don't end up
// with 50 visually inconsistent icons across the app.
//
// Why curated re-export instead of letting surfaces import from
// @phosphor-icons/react directly:
//   - Controls bundle size — only the curated set ships
//   - Single point of evolution — switching to a different icon library
//     in v2 only touches this file
//   - Enforcement-friendly — noPhosphorImports test fails on raw
//     @phosphor-icons imports outside this primitive
import {
  ArrowClockwise,
  ArrowLeft,
  ArrowRight,
  CaretDown,
  CaretUp,
  ChatCircle,
  Check,
  DotsThree,
  Eye,
  Gear,
  Info,
  MagnifyingGlass,
  Minus,
  Pause,
  Play,
  Plus,
  Question,
  SkipForward,
  WarningCircle,
  X,
  type Icon as PhosphorIconType,
} from '@phosphor-icons/react'

const ICONS = {
  'arrow-left': ArrowLeft,
  'arrow-right': ArrowRight,
  'caret-down': CaretDown,
  'caret-up': CaretUp,
  chat: ChatCircle,
  check: Check,
  close: X,
  eye: Eye,
  gear: Gear,
  info: Info,
  'menu-dots': DotsThree,
  minus: Minus,
  pause: Pause,
  play: Play,
  plus: Plus,
  question: Question,
  replay: ArrowClockwise,
  search: MagnifyingGlass,
  step: SkipForward,
  'warning-circle': WarningCircle,
} satisfies Record<string, PhosphorIconType>

export type IconName = keyof typeof ICONS
export type IconSize = 'sm' | 'md' | 'lg'
export type IconTone =
  | 'default'
  | 'soft'
  | 'muted'
  | 'accent'
  | 'success'
  | 'warning'
  | 'danger'
export type IconWeight = 'thin' | 'light' | 'regular' | 'bold'

export interface IconProps {
  name: IconName
  /** Pixel size — sm=14, md=16, lg=20. Default md. */
  size?: IconSize
  /** Color token. Default 'soft' (ink-soft) so icons sit quietly next
   *  to body text without competing. */
  tone?: IconTone
  /** Phosphor stroke weight. Default 'regular' for engineered-light. */
  weight?: IconWeight
  /** Required for non-decorative icons. Omit for decorative-only (gets aria-hidden). */
  ariaLabel?: string
  dataTest?: string
}

const SIZE_PX: Record<IconSize, number> = { sm: 14, md: 16, lg: 20 }

const TONE_COLOR: Record<IconTone, string> = {
  default: 'var(--ace-ink)',
  soft: 'var(--ace-ink-soft)',
  muted: 'var(--ace-ink-muted)',
  accent: 'var(--ace-accent)',
  success: 'var(--ace-success)',
  warning: 'var(--ace-warning)',
  danger: 'var(--ace-danger)',
}

export function Icon({
  name,
  size = 'md',
  tone = 'soft',
  weight = 'regular',
  ariaLabel,
  dataTest,
}: IconProps) {
  const Component = ICONS[name]
  return (
    <Component
      size={SIZE_PX[size]}
      weight={weight}
      color={TONE_COLOR[tone]}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel === undefined}
      data-test={dataTest}
    />
  )
}
