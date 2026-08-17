import type { IntelligenceBuildPlan } from '@/api/intelligenceBuildsApi'

import type {
  IntelligenceBuilderSession,
  IntelligenceBuilderStage,
  IntelligenceOnboardingProfile,
} from './onboardingModel'

export type AcceptedOnboardingChapter = 'Intent' | 'Evidence' | 'Review' | 'Activate'
export type SemanticStageState = 'complete' | 'current' | 'waiting' | 'blocked' | 'unsupported' | 'preview'

export interface SemanticOnboardingStage {
  readonly id:
    | 'define_goal'
    | 'generate_blueprint'
    | 'review_refine'
    | 'build_source_plan'
    | 'estimate_coverage'
    | 'initialize_domain'
    | 'validate_first_model'
    | 'activate_maintenance'
  readonly number: number
  readonly chapter: AcceptedOnboardingChapter
  readonly label: string
  readonly state: SemanticStageState
  readonly detail: string
}

export interface SourceBindingReadiness {
  readonly source_group_id: string
  readonly label: string
  readonly access_label: string
  readonly state: 'proposed' | 'unsupported'
  readonly detail: string
}

export interface ActivationReadiness {
  readonly state: 'plan_required' | 'proposal_only' | 'unbound' | 'legacy_unbindable'
  readonly capability_requirement_ids: readonly string[]
  readonly authority_request_ids: readonly string[]
  readonly detail: string
}

const STAGE_RANK: Record<IntelligenceBuilderStage, number> = {
  goal_selected: 0,
  sources_connecting: 1,
  sources_ready: 2,
  concept_model_proposed: 3,
  concept_model_approved: 4,
  intelligence_model_proposed: 5,
  intelligence_model_approved: 6,
  first_briefing_ready: 7,
  activation_pending: 8,
  active: 9,
  blocked: -1,
  retrying: -1,
}

function effectiveStage(session: IntelligenceBuilderSession | null): IntelligenceBuilderStage | null {
  if (session === null) return null
  if (session.stage === 'blocked' || session.stage === 'retrying') return session.resume_stage ?? 'goal_selected'
  return session.stage
}

function durableRank(session: IntelligenceBuilderSession | null): number {
  const stage = effectiveStage(session)
  return stage === null ? -1 : STAGE_RANK[stage]
}

function runtimeStageFor(stage: SemanticOnboardingStage['id'], session: IntelligenceBuilderSession | null): SemanticStageState | null {
  if (session === null || (session.stage !== 'blocked' && session.stage !== 'retrying')) return null
  const resumed = effectiveStage(session)
  const target = resumed === 'activation_pending'
    ? 'activate_maintenance'
    : resumed === 'first_briefing_ready'
      ? 'validate_first_model'
      : 'initialize_domain'
  if (stage !== target) return null
  return session.stage === 'blocked' ? 'blocked' : 'current'
}

function runtimeDetail(session: IntelligenceBuilderSession | null): string {
  if (session === null) return ''
  if (session.stage === 'blocked') {
    return session.safe_diagnostic ?? `ACE stopped safely: ${session.block_reason ?? 'review required'}.`
  }
  if (session.stage === 'retrying') return 'The retry is recorded against the exact durable stage; only a later revision can confirm that it resumed.'
  return ''
}

export function sourceBindingReadiness(
  profile: IntelligenceOnboardingProfile,
  selectedSourceGroupIds: readonly string[],
  plan: IntelligenceBuildPlan | null,
): readonly SourceBindingReadiness[] {
  const exactGroups = new Set(plan?.review_projection?.sources.map((source) => source.selection.source_group_id) ?? [])
  return profile.source_groups
    .filter((group) => selectedSourceGroupIds.includes(group.source_group_id))
    .map((group) => ({
      source_group_id: group.source_group_id,
      label: group.label,
      access_label: group.access_label,
      state: exactGroups.has(group.source_group_id) ? 'unsupported' : 'proposed',
      detail: exactGroups.has(group.source_group_id)
        ? 'Exact recorded material is selected; connection, permission, and runtime readiness are not projected.'
        : 'Source group selected for exact planning; no connection or permission state exists yet.',
    }))
}

export function activationReadiness(
  plan: IntelligenceBuildPlan | null,
  customPreview: boolean,
): ActivationReadiness {
  if (customPreview) {
    return {
      state: 'proposal_only',
      capability_requirement_ids: [],
      authority_request_ids: [],
      detail: 'Custom Intelligence is proposal-only Preview and has no activation or first-Brief executor in v1.',
    }
  }
  if (plan === null) {
    return {
      state: 'plan_required',
      capability_requirement_ids: [],
      authority_request_ids: [],
      detail: 'Prepare an exact plan before reviewing bindings or authority.',
    }
  }
  if (plan.contract !== 'ace.application.intelligence-build-plan/v1alpha3' || plan.activation_proposal === undefined) {
    return {
      state: 'legacy_unbindable',
      capability_requirement_ids: [],
      authority_request_ids: [],
      detail: 'This plan does not carry the activation-neutral v1alpha3 proposal required by the exact binding route.',
    }
  }
  return {
    state: 'unbound',
    capability_requirement_ids: plan.activation_proposal.capability_requirement_ids,
    authority_request_ids: plan.activation_proposal.authority_request_ids,
    detail: 'The exact requirements are named, but no implementation binding, grant binding, or approval receipt has been supplied.',
  }
}

export function semanticOnboardingStages({
  subject,
  plan,
  session,
  customPreview,
}: {
  readonly subject: string
  readonly plan: IntelligenceBuildPlan | null
  readonly session: IntelligenceBuilderSession | null
  readonly customPreview: boolean
}): readonly SemanticOnboardingStage[] {
  const hasGoal = subject.trim().length >= 8
  const review = plan?.review_projection ?? null
  const rank = durableRank(session)
  const activation = activationReadiness(plan, customPreview)
  const runtimeState = (id: SemanticOnboardingStage['id']) => runtimeStageFor(id, session)
  const runtimeMessage = runtimeDetail(session)

  const stages: SemanticOnboardingStage[] = [
    {
      id: 'define_goal',
      number: 1,
      chapter: 'Intent',
      label: 'Define the intelligence goal',
      state: hasGoal || rank >= 0 ? 'complete' : 'current',
      detail: hasGoal || rank >= 0 ? 'The intended subject and outcome are explicit.' : 'Describe what ACE should understand.',
    },
    {
      id: 'generate_blueprint',
      number: 2,
      chapter: 'Intent',
      label: 'Generate the domain blueprint',
      state: customPreview ? 'preview' : review !== null || rank >= 3 ? 'complete' : hasGoal ? 'current' : 'waiting',
      detail: customPreview
        ? 'ACE can draft a local proposal; blueprint rationale and confidence are not projected.'
        : review !== null
          ? 'The exact planner returned the model; the canonical projection explains Pack/profile rationale and leaves confidence unscored unless supported.'
          : 'An exact installed planner must return the proposed model.',
    },
    {
      id: 'review_refine',
      number: 3,
      chapter: 'Review',
      label: 'Review and refine',
      state: customPreview ? 'preview' : rank >= 4 ? 'complete' : review !== null ? 'current' : 'waiting',
      detail: rank >= 4
        ? 'A durable approved concept-model stage exists.'
        : review !== null
          ? 'The exact proposal is reviewable; no material change acceptance is inferred.'
          : 'Review begins only after exact proposal material exists.',
    },
    {
      id: 'build_source_plan',
      number: 4,
      chapter: 'Evidence',
      label: 'Build the source plan',
      state: customPreview ? 'preview' : review !== null ? 'complete' : 'waiting',
      detail: review !== null
        ? 'Exact recorded-source selections exist; connection, credential, permission, and readiness state remain separate.'
        : 'Selected source groups are proposals until the exact planner returns recorded material.',
    },
    {
      id: 'estimate_coverage',
      number: 5,
      chapter: 'Evidence',
      label: 'Estimate coverage before ingestion',
      state: customPreview ? 'preview' : 'unsupported',
      detail: 'Coverage remains explicit by entity, event, and signal; no governed predicted score is available until an estimator is bound.',
    },
    {
      id: 'initialize_domain',
      number: 6,
      chapter: 'Activate',
      label: 'Initialize the domain',
      state: customPreview
        ? 'unsupported'
        : runtimeState('initialize_domain') ?? (rank >= 7 ? 'complete' : rank >= 0 ? 'current' : 'waiting'),
      detail: runtimeState('initialize_domain') !== null
        ? runtimeMessage
        : customPreview
          ? 'Custom Preview never calls initialization.'
          : rank >= 7
            ? 'Durable session revisions reached first-Brief validation.'
            : rank >= 0
              ? 'Progress comes from the append-only Builder session, not a timer.'
              : activation.detail,
    },
    {
      id: 'validate_first_model',
      number: 7,
      chapter: 'Activate',
      label: 'Validate the first model',
      state: customPreview
        ? 'unsupported'
        : runtimeState('validate_first_model') ?? (rank >= 7 ? 'complete' : rank >= 0 ? 'waiting' : 'waiting'),
      detail: runtimeState('validate_first_model') !== null
        ? runtimeMessage
        : customPreview
          ? 'Custom Preview has no first-Brief executor.'
          : rank >= 7
            ? 'A durable first-briefing-ready revision exists; the cited Brief can open in Overview.'
            : 'Validation requires a durable first-Brief result and its evidence, conflicts, and unknowns.',
    },
    {
      id: 'activate_maintenance',
      number: 8,
      chapter: 'Activate',
      label: 'Activate continuous maintenance',
      state: customPreview
        ? 'unsupported'
        : runtimeState('activate_maintenance') ?? (rank >= 9 ? 'complete' : rank >= 8 ? 'current' : 'waiting'),
      detail: runtimeState('activate_maintenance') !== null
        ? runtimeMessage
        : rank >= 9
          ? 'The durable Builder session is active.'
          : rank >= 8
            ? 'Activation is pending exact Core admission.'
            : activation.detail,
    },
  ]
  return stages
}
