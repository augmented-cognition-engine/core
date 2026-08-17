import {
  Activity,
  Bell,
  Blocks,
  BookOpenCheck,
  Bot,
  Boxes,
  Cable,
  CircleCheck,
  CircleHelp,
  ClipboardList,
  Database,
  Eye,
  FileStack,
  FileText,
  Focus,
  GitBranch,
  GitCompareArrows,
  History,
  MessageCircleQuestion,
  MessageSquare,
  Newspaper,
  PanelsTopLeft,
  Radar,
  Radio,
  Scale,
  Search,
  SearchCheck,
  Share2,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  TrendingUp,
  TriangleAlert,
  Workflow,
  Zap,
  type LucideIcon,
} from 'lucide-react'

import type { IntelligenceResourceKind } from '@/api/intelligenceResourcesApi'

export const ATRIUM_SURFACE_ICONS = {
  overview: PanelsTopLeft,
  explore: Search,
  build: Blocks,
  operate: ShieldCheck,
  consumers: Share2,
} as const satisfies Record<string, LucideIcon>

export const ATRIUM_ACTION_ICONS = {
  ask: MessageCircleQuestion,
  build: Blocks,
  current: CircleCheck,
  governedEvidence: BookOpenCheck,
  evidenceLineage: GitBranch,
} as const satisfies Record<string, LucideIcon>

export const ATRIUM_DOWNSTREAM_ICONS = {
  investigationBoard: ClipboardList,
} as const satisfies Record<string, LucideIcon>

export const ATRIUM_INTELLIGENCE_ICONS = {
  signal: Radio,
  unknown: CircleHelp,
  attention: Focus,
} as const satisfies Record<string, LucideIcon>

const RESOURCE_ICONS: Partial<Record<IntelligenceResourceKind, LucideIcon>> = {
  connection: Cable,
  source: Database,
  source_health: Activity,
  entity: Boxes,
  observation: Eye,
  signal: Radio,
  shift: TrendingUp,
  case: SearchCheck,
  brief: Newspaper,
  monitor: Radar,
  subscription: Bell,
  agent: Bot,
  decision: Scale,
  action: Zap,
  outcome: Target,
  feedback: MessageSquare,
  evidence_lineage: GitBranch,
  uncertainty: CircleHelp,
  conflict: TriangleAlert,
  semantic_revision: GitCompareArrows,
  context_manifest: FileStack,
  memory_use: History,
  builder_profile: SlidersHorizontal,
  builder_session: Workflow,
}

export function atriumIconForResourceKind(kind: IntelligenceResourceKind): LucideIcon {
  return RESOURCE_ICONS[kind] ?? FileText
}
