// frontend/src/design/components/index.ts
//
// Barrel export for the ACE design system component library. Surfaces
// import from here:
//
//   import { Card, Section, Chip, Pip, Glyph, AskInput } from '../design/components'
//
// Every UI primitive lives in this directory. No surface should define
// its own card/chip/button/etc; if a needed primitive doesn't exist, add
// it here first, then use it.

export { AskInput } from './AskInput'
export type { AskInputProps } from './AskInput'

export { Aphorism } from './Aphorism'
export type { AphorismProps } from './Aphorism'

export { Button } from './Button'
export type { ButtonProps, ButtonSize, ButtonVariant } from './Button'

export { Byline } from './Byline'
export type { BylineProps } from './Byline'

export { Card } from './Card'
export type { CardProps, CardVariant, CardPadding } from './Card'

export { Chip } from './Chip'
export type { ChipProps, ChipVariant } from './Chip'

export { Divider } from './Divider'
export type { DividerProps } from './Divider'

export { Eyebrow } from './Eyebrow'
export type { EyebrowProps } from './Eyebrow'

export { Glyph } from './Glyph'
export type { GlyphProps } from './Glyph'

export { Input } from './Input'
export type { InputProps, InputSize, InputVariant } from './Input'

export { LinkButton } from './LinkButton'
export type { LinkButtonProps } from './LinkButton'

export { Textarea } from './Textarea'
export type { TextareaProps, TextareaSize, TextareaVariant } from './Textarea'

export { Pip } from './Pip'
export type { PipProps } from './Pip'

export { Section } from './Section'
export type { SectionProps, SectionStatus } from './Section'

// ---- Wave 2 primitives ----------------------------------------------

export { Avatar } from './Avatar'
export type { AvatarProps } from './Avatar'

export { NorthStarBar } from './NorthStarBar'
export type { NorthStarBarProps } from './NorthStarBar'

export { RosterRow } from './RosterRow'
export type { RosterRowProps } from './RosterRow'

export { Sparkline } from './Sparkline'
export type { SparklineProps } from './Sparkline'

export { StatusBadge } from './StatusBadge'
export type { StatusBadgeProps } from './StatusBadge'

// ---- Wave 3 — Layer 4 behavioral wrappers (Radix UI) ---------------

export { Tooltip, TooltipProvider } from './Tooltip'
export type { TooltipProps } from './Tooltip'

export { Popover } from './Popover'
export type { PopoverProps } from './Popover'

export { Dialog, DialogClose } from './Dialog'
export type { DialogProps } from './Dialog'

export { Menu } from './Menu'
export type { MenuProps, MenuItem } from './Menu'

export { Select } from './Select'
export { Slider } from './Slider'
export type { SliderProps } from './Slider'
export type { SelectProps, SelectOption, SelectSize, SelectVariant } from './Select'

export { Tabs } from './Tabs'
export type { TabsProps, TabsVariant, TabConfig } from './Tabs'

export { Checkbox } from './Checkbox'
export type { CheckboxProps, CheckboxVariant } from './Checkbox'

export { Switch } from './Switch'
export type { SwitchProps } from './Switch'

export { AcknowledgmentProvider, useAcknowledgment } from './Acknowledgment'
export type { AcknowledgmentInput, AcknowledgmentTone } from './Acknowledgment'

export { Icon } from './Icon'
export type { IconProps, IconName, IconSize, IconTone, IconWeight } from './Icon'

// ---- Wave 4 — Layout primitives (v1) -------------------------------

export { Stack } from './Stack'
export type { StackProps, StackDirection, StackAlign, StackJustify } from './Stack'

export { Cluster } from './Cluster'
export type { ClusterProps, ClusterAlign, ClusterJustify } from './Cluster'

export { Grid } from './Grid'
export type { GridProps } from './Grid'

export { Sidebar } from './Sidebar'
export type { SidebarProps, SidebarSide } from './Sidebar'

export { Frame } from './Frame'
export type { FrameProps, FrameSurface } from './Frame'

// ---- Wave 5 — Partnership primitives (v1) --------------------------
// The ACE-native vocabulary. These don't exist in any other design
// system — they're the executable form of the partnership thesis.

export { ContributionLane } from './ContributionLane'
export type {
  ContributionLaneProps,
  ContributionLaneState,
  ContributionLaneVoice,
} from './ContributionLane'

export { VoiceCallout } from './VoiceCallout'
export type {
  VoiceCalloutProps,
  VoiceCalloutTone,
  VoiceCalloutFrom,
} from './VoiceCallout'

export { AgentPresenceRow } from './AgentPresenceRow'
export type { AgentPresenceRowProps, AgentPresenceTone } from './AgentPresenceRow'

export { SeverityFinding } from './SeverityFinding'
export type { SeverityFindingProps, Severity } from './SeverityFinding'

// ---- Wave 6 — Content-pattern primitives (v1) ----------------------
// Voice rules from voice-style-guide.md codified as executable
// components. Surfaces compose these instead of inlining the voice
// shape; voice correctness is then a primitive concern, not a
// per-call-site concern.

export { Pushback } from './Pushback'
export type { PushbackProps } from './Pushback'

export { ProactiveLine } from './ProactiveLine'
export type { ProactiveLineProps, ProactiveLineTone } from './ProactiveLine'

export { EmptyState } from './EmptyState'
export type { EmptyStateProps } from './EmptyState'

export { Briefing } from './Briefing'
export type { BriefingProps } from './Briefing'

export { HandOff } from './HandOff'
export type { HandOffProps, HandOffPhase } from './HandOff'

export { AmbientWorking } from './AmbientWorking'
export type { AmbientWorkingProps } from './AmbientWorking'

export { DecisionCapture } from './DecisionCapture'
export type { DecisionCaptureProps, DecisionSource } from './DecisionCapture'

// ---- Wave 7 — Universal editorial primitives (v1) ------------------
// Cross-page patterns extracted from the static extension demos that
// have no theme-specific shape — every product surface uses them.
// Extension themes restyle them via existing design tokens (no
// extension-prefixed variants).

export { AccentNote } from './AccentNote'
export type { AccentNoteProps, AccentNoteTone } from './AccentNote'

export { ClosingBand } from './ClosingBand'
export type { ClosingBandProps } from './ClosingBand'

export { ScoreHero } from './ScoreHero'
export type { ScoreHeroProps, ScoreHeroTrend } from './ScoreHero'

export { StageChain } from './StageChain'
export type { StageChainProps, StageChainItem } from './StageChain'
