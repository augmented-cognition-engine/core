import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'

const PROFILE_CONTRACT = 'ace.intelligence.onboarding-profile/v1alpha1' as const
const LEGACY_PROFILE_CONTRACT = 'ace.domain-pack.intelligence-onboarding-profile/v1alpha1' as const

export interface IntelligenceOnboardingOutcome {
  readonly outcome_id: string
  readonly label: string
  readonly description: string
  readonly icon_hint: string
  readonly recommended_topic_labels: readonly string[]
  readonly recommended_intelligence_labels: readonly string[]
}

export interface IntelligenceOnboardingCadence {
  readonly cadence_id: string
  readonly label: string
  readonly description: string
}

export interface IntelligenceOnboardingProfile {
  readonly contract: typeof PROFILE_CONTRACT | typeof LEGACY_PROFILE_CONTRACT
  readonly display_name: string
  readonly prompt: string
  readonly description: string
  readonly outcomes: readonly IntelligenceOnboardingOutcome[]
  readonly cadences: readonly IntelligenceOnboardingCadence[]
  readonly default_cadence_id: string
  readonly completion_label: string
}

export type IntelligenceBuilderStage =
  | 'goal_selected'
  | 'sources_connecting'
  | 'sources_ready'
  | 'concept_model_proposed'
  | 'concept_model_approved'
  | 'intelligence_model_proposed'
  | 'intelligence_model_approved'
  | 'first_briefing_ready'
  | 'activation_pending'
  | 'active'
  | 'blocked'
  | 'retrying'

export interface IntelligenceBuilderArtifact {
  readonly artifact_kind: string
  readonly artifact_id: string
  readonly artifact_digest: string
}

export interface IntelligenceBuilderSession {
  readonly session_id: string
  readonly goal_ref: string
  readonly sequence: number
  readonly stage: IntelligenceBuilderStage
  readonly artifacts: readonly IntelligenceBuilderArtifact[]
  readonly block_reason: string | null
  readonly resume_stage: IntelligenceBuilderStage | null
  readonly safe_diagnostic: string | null
}

const FALLBACK_PROFILE: IntelligenceOnboardingProfile = {
  contract: PROFILE_CONTRACT,
  display_name: 'Your Intelligence',
  prompt: 'What do you need to stay ahead of?',
  description: 'Choose the decision context. ACE will recommend the evidence, concepts, watches, and briefing system.',
  outcomes: [
    {
      outcome_id: 'choice',
      label: 'Make a product or technology choice',
      description: 'Compare the options, trade-offs, evidence, and operating implications that matter.',
      icon_hint: 'choice',
      recommended_topic_labels: ['Options', 'Evidence', 'Cost', 'Performance', 'Risk'],
      recommended_intelligence_labels: ['Comparative movement', 'Claim versus evidence'],
    },
    {
      outcome_id: 'strategy',
      label: 'Set strategy or evaluate investments',
      description: 'Track the forces, commitments, and outcomes shaping durable advantage.',
      icon_hint: 'strategy',
      recommended_topic_labels: ['Market forces', 'Investment', 'Capabilities', 'Adoption', 'Outcomes'],
      recommended_intelligence_labels: ['Momentum', 'Constraints', 'Execution gaps'],
    },
    {
      outcome_id: 'frontier',
      label: 'Track emerging change',
      description: 'Follow early signals as they become material products, policies, or behavior.',
      icon_hint: 'research',
      recommended_topic_labels: ['Research', 'Products', 'Leading indicators', 'Adoption'],
      recommended_intelligence_labels: ['Diffusion', 'Material shifts'],
    },
    {
      outcome_id: 'risk',
      label: 'Manage policy and operational risk',
      description: 'Watch rules, incidents, dependencies, safeguards, and implementation gaps.',
      icon_hint: 'risk',
      recommended_topic_labels: ['Policy', 'Incidents', 'Reliability', 'Dependencies'],
      recommended_intelligence_labels: ['Implementation gaps', 'Risk movement'],
    },
    {
      outcome_id: 'competition',
      label: 'Understand the competitive landscape',
      description: 'Compare organizations through claims, investment, capability, and execution.',
      icon_hint: 'competition',
      recommended_topic_labels: ['Organizations', 'Offerings', 'Claims', 'Investment', 'Execution'],
      recommended_intelligence_labels: ['Position movement', 'Strategy before announcement'],
    },
    {
      outcome_id: 'custom',
      label: 'Build a custom picture',
      description: 'Choose the entities, questions, evidence, thresholds, and cadence that matter to you.',
      icon_hint: 'custom',
      recommended_topic_labels: [],
      recommended_intelligence_labels: [],
    },
  ],
  cadences: [
    { cadence_id: 'urgent', label: 'Urgent only', description: 'Only material thresholds, contradictions, and incidents.' },
    { cadence_id: 'daily', label: 'Daily pulse', description: 'A concise daily orientation plus urgent alerts.' },
    { cadence_id: 'weekly', label: 'Weekly briefing', description: "The week's movement, open questions, and next catalysts." },
  ],
  default_cadence_id: 'weekly',
  completion_label: 'Open my first briefing',
}

const BUILDER_STAGES = new Set<IntelligenceBuilderStage>([
  'goal_selected',
  'sources_connecting',
  'sources_ready',
  'concept_model_proposed',
  'concept_model_approved',
  'intelligence_model_proposed',
  'intelligence_model_approved',
  'first_briefing_ready',
  'activation_pending',
  'active',
  'blocked',
  'retrying',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function canonicalPayload(value: unknown): unknown {
  if (!isRecord(value) || typeof value.value_json !== 'string') return value
  try {
    return JSON.parse(value.value_json) as unknown
  } catch {
    return null
  }
}

function strings(value: unknown): readonly string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === 'string') ? value : null
}

function parseOutcome(value: unknown): IntelligenceOnboardingOutcome | null {
  if (!isRecord(value)) return null
  const topics = strings(value.recommended_topic_labels)
  const intelligence = strings(value.recommended_intelligence_labels)
  if (
    typeof value.outcome_id !== 'string' || typeof value.label !== 'string' ||
    typeof value.description !== 'string' || typeof value.icon_hint !== 'string' ||
    topics === null || intelligence === null
  ) return null
  return {
    outcome_id: value.outcome_id,
    label: value.label,
    description: value.description,
    icon_hint: value.icon_hint,
    recommended_topic_labels: topics,
    recommended_intelligence_labels: intelligence,
  }
}

function parseCadence(value: unknown): IntelligenceOnboardingCadence | null {
  if (!isRecord(value)) return null
  if (typeof value.cadence_id !== 'string' || typeof value.label !== 'string' || typeof value.description !== 'string') return null
  return { cadence_id: value.cadence_id, label: value.label, description: value.description }
}

export function parseOnboardingProfile(value: unknown): IntelligenceOnboardingProfile | null {
  if (!isRecord(value) || (value.contract !== PROFILE_CONTRACT && value.contract !== LEGACY_PROFILE_CONTRACT)) return null
  if (
    typeof value.display_name !== 'string' || typeof value.prompt !== 'string' ||
    typeof value.description !== 'string' || typeof value.default_cadence_id !== 'string'
  ) return null
  const outcomes = Array.isArray(value.outcomes) ? value.outcomes.map(parseOutcome) : []
  const cadences = Array.isArray(value.cadences) ? value.cadences.map(parseCadence) : []
  if (outcomes.length === 0 || outcomes.some((item) => item === null) || cadences.length === 0 || cadences.some((item) => item === null)) return null
  const firstValue = isRecord(value.first_value) ? value.first_value : null
  const completionLabel = firstValue !== null && typeof firstValue.completion_label === 'string'
    ? firstValue.completion_label
    : 'Open my first briefing'
  return {
    contract: value.contract,
    display_name: value.display_name,
    prompt: value.prompt,
    description: value.description,
    outcomes: outcomes as IntelligenceOnboardingOutcome[],
    cadences: cadences as IntelligenceOnboardingCadence[],
    default_cadence_id: value.default_cadence_id,
    completion_label: completionLabel,
  }
}

function parseBuilderArtifact(value: unknown): IntelligenceBuilderArtifact | null {
  if (!isRecord(value)) return null
  if (typeof value.artifact_kind !== 'string' || typeof value.artifact_id !== 'string' || typeof value.artifact_digest !== 'string') return null
  return {
    artifact_kind: value.artifact_kind,
    artifact_id: value.artifact_id,
    artifact_digest: value.artifact_digest,
  }
}

export function parseBuilderSession(value: unknown): IntelligenceBuilderSession | null {
  if (!isRecord(value) || value.contract !== 'ace.application.intelligence-builder-session-revision/v1alpha1') return null
  if (
    typeof value.session_id !== 'string' || typeof value.goal_ref !== 'string' ||
    typeof value.sequence !== 'number' || typeof value.stage !== 'string' ||
    !BUILDER_STAGES.has(value.stage as IntelligenceBuilderStage)
  ) return null
  const artifacts = Array.isArray(value.artifacts) ? value.artifacts.map(parseBuilderArtifact) : []
  if (artifacts.some((item) => item === null)) return null
  const blockReason = value.block_reason === null || typeof value.block_reason === 'string' ? value.block_reason : null
  const resumeStage = value.resume_stage === null || value.resume_stage === undefined
    ? null
    : typeof value.resume_stage === 'string' && BUILDER_STAGES.has(value.resume_stage as IntelligenceBuilderStage)
      ? value.resume_stage as IntelligenceBuilderStage
      : null
  const diagnostic = value.safe_diagnostic === null || typeof value.safe_diagnostic === 'string' ? value.safe_diagnostic : null
  return {
    session_id: value.session_id,
    goal_ref: value.goal_ref,
    sequence: value.sequence,
    stage: value.stage as IntelligenceBuilderStage,
    artifacts: artifacts as IntelligenceBuilderArtifact[],
    block_reason: blockReason ?? null,
    resume_stage: resumeStage,
    safe_diagnostic: diagnostic ?? null,
  }
}

export function onboardingProfileFromResources(items: readonly IntelligenceResourceRecord[]): IntelligenceOnboardingProfile {
  for (const item of items) {
    const payload = canonicalPayload(item.payload)
    if (item.reference.resource_kind === 'builder_profile') {
      const profile = parseOnboardingProfile(payload)
      if (profile !== null) return profile
    }
    if (item.reference.resource_kind === 'context_manifest' && isRecord(payload)) {
      const profile = parseOnboardingProfile(payload.onboarding_profile)
      if (profile !== null) return profile
    }
  }
  return FALLBACK_PROFILE
}

export function onboardingSessionFromResources(items: readonly IntelligenceResourceRecord[]): IntelligenceBuilderSession | null {
  return items
    .filter((item) => item.reference.resource_kind === 'builder_session')
    .map((item) => ({ item, session: parseBuilderSession(canonicalPayload(item.payload)) }))
    .filter((entry): entry is { item: IntelligenceResourceRecord; session: IntelligenceBuilderSession } => entry.session !== null)
    .sort((left, right) => right.session.sequence - left.session.sequence || Date.parse(right.item.reference.available_at) - Date.parse(left.item.reference.available_at))[0]
    ?.session ?? null
}

export function hasOnboardingProfileResource(items: readonly IntelligenceResourceRecord[]): boolean {
  return items.some((item) => {
    const payload = canonicalPayload(item.payload)
    if (item.reference.resource_kind === 'builder_profile') return parseOnboardingProfile(payload) !== null
    return item.reference.resource_kind === 'context_manifest' && isRecord(payload) && parseOnboardingProfile(payload.onboarding_profile) !== null
  })
}
