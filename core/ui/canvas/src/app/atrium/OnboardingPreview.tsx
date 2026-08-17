import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  Check,
  CircleDot,
  Compass,
  Database,
  Eye,
  FileCheck2,
  FlaskConical,
  Gauge,
  GitFork,
  Landmark,
  LineChart,
  LoaderCircle,
  LockKeyhole,
  Megaphone,
  PlugZap,
  Radar,
  RefreshCw,
  Scale,
  ShieldAlert,
  TriangleAlert,
} from 'lucide-react'

import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/design/shadcn/ui/dialog'
import { Textarea } from '@/design/shadcn/ui/textarea'
import {
  createDomainActivationPlanApproveInput,
  createDomainActivationPlanPrepareInput,
  createIntelligenceBuildPlanBindInput,
  createIntelligenceBuildPlanPrepareInput,
  createIntelligenceBuildResourceStateInput,
  createIntelligenceBuilderPlanActivateInput,
  IntelligenceBuildApiError,
  type BoundIntelligenceBuildPlan,
  type DomainActivationPlanApproveInput,
  type DomainActivationPlanPrepareInput,
  type DomainActivationCommitReference,
  type IntelligenceActivationPlan,
  type IntelligenceBuildApprovalResult,
  type IntelligenceBuildActivationSetup,
  type IntelligenceBuildPlan,
  type IntelligenceBuildPlanPrepareInput,
  type IntelligenceBuildPlanReviewEffect,
  type IntelligenceBuildResourceStateInput,
  type IntelligenceBuildResult,
  type IntelligenceBuildSessionAssociationResult,
  type IntelligenceBuildPlanBindInput,
  type IntelligenceBuildStartInput,
  type IntelligenceBuilderActivationResult,
  type IntelligenceBuilderPlanActivateInput,
  type IntelligenceProjectionSupport,
  type IntelligenceSystemProjection,
} from '@/api/intelligenceBuildsApi'
import { ATRIUM_ACTION_ICONS } from './atriumIcons'
import type {
  IntelligenceBuilderSession,
  IntelligenceBuilderStage,
  IntelligenceOnboardingOutcome,
  IntelligenceOnboardingProfile,
  IntelligenceOnboardingSourceGroup,
} from './onboardingModel'
import { isCustomPreviewProfile, onboardingSessionFromResources, parseBuilderSession } from './onboardingModel'
import { semanticOnboardingStages, type SemanticOnboardingStage } from './onboardingJourney'

const BuildIcon = ATRIUM_ACTION_ICONS.build

const ICONS: Record<string, typeof Compass> = {
  choice: Gauge,
  strategy: BarChart3,
  research: FlaskConical,
  risk: ShieldAlert,
  competition: Radar,
  custom: Compass,
}

const SOURCE_ICONS: Record<string, typeof Database> = {
  authoritative_record: Landmark,
  first_party_claim: Megaphone,
  independent_measurement: LineChart,
  operational_telemetry: Database,
  leading_indicator: GitFork,
  private_organizational: LockKeyhole,
}

const STEP_LABELS = ['Choose', 'Intent', 'Evidence', 'Review', 'Activate'] as const
const CUSTOM_PREVIEW_STEP_LABELS = ['Choose', 'Intent', 'Evidence', 'Review', 'Preview'] as const

type BuildState = 'complete' | 'active' | 'blocked' | 'waiting' | 'proposed' | 'preview' | 'unsupported'

interface BuildLane {
  readonly label: string
  readonly result: string
  readonly state: BuildState
}

interface PlanErrorState {
  readonly status: number
  readonly title: string
  readonly detail: string
}

function planErrorState(reason: unknown): PlanErrorState {
  const status = reason instanceof IntelligenceBuildApiError ? reason.status : 0
  const detail = reason instanceof Error ? reason.message : 'ACE could not prepare exact review material.'
  if (status === 404) {
    return {
      status,
      title: 'This starting point is no longer installed.',
      detail: `${detail} Choose another installed intelligence starting point or refresh the catalog.`,
    }
  }
  if (status === 409) {
    return {
      status,
      title: 'This proposed plan is out of date.',
      detail: `${detail} Go back and review the current profile and evidence selection before preparing again.`,
    }
  }
  if (status === 503) {
    return {
      status,
      title: 'Exact planning is not available yet.',
      detail: `${detail} Nothing was connected, activated, or changed.`,
    }
  }
  return {
    status,
    title: 'ACE stopped before preparing the plan.',
    detail: `${detail} Nothing was connected, activated, or changed.`,
  }
}

function activationErrorState(reason: unknown): PlanErrorState {
  const status = reason instanceof IntelligenceBuildApiError ? reason.status : 0
  const detail = reason instanceof Error ? reason.message : 'ACE could not validate and initialize this exact plan.'
  if (status === 403) {
    return {
      status,
      title: 'Current permission does not authorize activation.',
      detail: `${detail} No source, watch, first Brief, or maintenance loop was started.`,
    }
  }
  if (status === 409) {
    return {
      status,
      title: 'The reviewed bindings no longer match this plan.',
      detail: `${detail} Review the current capability and authority bindings before trying again.`,
    }
  }
  if (status === 503) {
    return {
      status,
      title: 'The activation runtime is not connected.',
      detail: `${detail} The exact plan remains available for review; execution stopped safely.`,
    }
  }
  return {
    status,
    title: 'ACE stopped before initialization.',
    detail: `${detail} No source, watch, first Brief, or maintenance loop was started.`,
  }
}

type ActivationPlanAvailability =
  | { readonly state: 'ready'; readonly current: Readonly<Record<string, unknown>> }
  | { readonly state: 'not_ready'; readonly reason: string }
  | { readonly state: 'unsupported' }

/**
 * Never fabricates a session: the v1alpha2 activation-plan coordinator
 * requires the exact durable `first_briefing_ready` session revision the
 * reviewed-build association or resource payload supplied. Any other case fails closed with a precise,
 * customer-visible reason instead of guessing.
 */
function activationPlanAvailability(
  session: IntelligenceBuilderSession | null,
  handlersConfigured: boolean,
): ActivationPlanAvailability {
  if (!handlersConfigured) return { state: 'unsupported' }
  if (session === null) {
    return {
      state: 'not_ready',
      reason: 'ACE has no current Builder session associated with this reviewed plan. No authorization or start can be recorded without that exact durable revision.',
    }
  }
  if (session.stage !== 'first_briefing_ready') {
    return {
      state: 'not_ready',
      reason: `The current durable Builder revision is ${session.stage.replace(/_/g, ' ')}. Maintenance authorization requires an exact first-briefing-ready revision; this screen does not infer later progress.`,
    }
  }
  if (session.exact_revision == null) {
    return {
      state: 'not_ready',
      reason: 'ACE does not hold the exact durable session revision required for this activation plan. Refresh the Builder session before authorizing maintenance.',
    }
  }
  return { state: 'ready', current: session.exact_revision }
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

function OutcomeIcon({ outcome }: { readonly outcome: IntelligenceOnboardingOutcome }) {
  const Icon = ICONS[outcome.icon_hint] ?? Compass
  return <Icon className="size-4" aria-hidden="true" />
}

function SourceIcon({ group }: { readonly group: IntelligenceOnboardingSourceGroup }) {
  const Icon = SOURCE_ICONS[group.evidence_role] ?? FileCheck2
  return <Icon className="size-4" aria-hidden="true" />
}

function laneState(rank: number, activeAt: number, completeAt: number): BuildState {
  if (rank >= completeAt) return 'complete'
  if (rank >= activeAt) return 'active'
  return 'waiting'
}

function recoveryLane(stage: IntelligenceBuilderStage | null): number {
  const rank = stage === null ? 0 : STAGE_RANK[stage]
  if (rank <= 2) return 1
  if (rank <= 6) return 3
  if (rank === 7) return 4
  return 5
}

function projectedBindingLane(
  projection: IntelligenceSystemProjection | null,
  field: 'permission_state' | 'readiness_state',
  label: string,
): BuildLane {
  const states = projection?.source_bindings.map((binding) => binding[field]) ?? []
  if (states.length === 0 || states.every((state) => state === 'not_evaluated')) {
    return {
      label,
      result: `Not reported${projection === null ? ' — canonical resource state is unavailable' : ' by the current canonical projection'}`,
      state: 'unsupported',
    }
  }
  if (states.some((state) => state === 'denied' || state === 'unavailable')) {
    return { label, result: 'At least one exact source binding is denied or unavailable', state: 'blocked' }
  }
  if (states.every((state) => state === 'ready')) {
    return { label, result: `Ready across ${states.length} exact source binding${states.length === 1 ? '' : 's'}`, state: 'complete' }
  }
  return { label, result: 'Pending in the canonical resource-state projection', state: 'active' }
}

function projectedAdmissionLane(projection: IntelligenceSystemProjection | null): BuildLane {
  const admission = projection?.initialization.find((stage) => stage.stage === 'evidence_admitted')
  if (admission === undefined) {
    return {
      label: 'Evidence admission',
      result: 'Not reported — a Builder stage alone does not prove source admission',
      state: 'unsupported',
    }
  }
  return {
    label: 'Evidence admission',
    result: admission.detail,
    state: admission.state === 'complete'
      ? 'complete'
      : admission.state === 'blocked'
        ? 'blocked'
        : admission.state === 'in_progress'
          ? 'active'
          : 'waiting',
  }
}

function buildLanes(
  session: IntelligenceBuilderSession | null,
  projection: IntelligenceSystemProjection | null,
): readonly BuildLane[] {
  const effectiveStage = session === null
    ? 'goal_selected'
    : session.stage === 'blocked' || session.stage === 'retrying'
      ? session.resume_stage ?? 'goal_selected'
      : session.stage
  const rank = session === null ? -1 : STAGE_RANK[effectiveStage]
  const sourceState = laneState(rank, 1, 2)
  const initializationState = laneState(rank, 3, 7)
  const briefingState = laneState(rank, 7, 7)
  const maintenanceState = laneState(rank, 8, 9)
  const lanes: BuildLane[] = [
    projectedBindingLane(projection, 'permission_state', 'Source permission'),
    {
      ...projectedBindingLane(projection, 'readiness_state', 'Source readiness'),
      ...(projection === null
        ? {
            result: session === null
              ? 'Not reported — no durable Builder session is associated with this view'
              : sourceState === 'complete'
                ? 'Sources-ready Builder revision recorded'
                : sourceState === 'active'
                  ? `Current durable revision: ${effectiveStage.replace(/_/g, ' ')}`
                  : 'Waiting for a durable source-readiness revision',
            state: session === null ? 'unsupported' as const : sourceState,
          }
        : {}),
    },
    projectedAdmissionLane(projection),
    {
      label: 'Domain initialization',
      result: initializationState === 'complete'
        ? 'First-Brief validation boundary reached'
        : initializationState === 'active'
          ? `Current durable revision: ${effectiveStage.replace(/_/g, ' ')}`
          : session === null
            ? 'Not started — no durable Builder session is associated with this view'
            : 'Waiting for a durable initialization revision',
      state: session === null ? 'unsupported' : initializationState,
    },
    {
      label: 'First cited Brief',
      result: briefingState === 'complete'
        ? 'First-briefing-ready revision recorded'
        : 'Waiting for a durable first-Brief result with citations',
      state: briefingState,
    },
    {
      label: 'Maintenance activation',
      result: maintenanceState === 'complete'
        ? 'Active Builder revision recorded'
        : maintenanceState === 'active'
          ? 'Activation-pending revision recorded; exact Core admission has not produced an active revision'
          : 'Not active — maintenance requires its own governed activation',
      state: maintenanceState,
    },
  ]

  if (session?.stage === 'blocked') {
    const lane = recoveryLane(session.resume_stage)
    lanes[lane] = {
      ...lanes[lane],
      result: session.safe_diagnostic ?? `ACE stopped safely: ${session.block_reason ?? 'review required'}.`,
      state: 'blocked',
    }
  } else if (session?.stage === 'retrying') {
    const lane = recoveryLane(session.resume_stage)
    lanes[lane] = { ...lanes[lane], result: 'Retrying revision recorded; a later durable revision must confirm the outcome.', state: 'active' }
  }
  return lanes
}

function customPreviewLanes(watchCount: number | 'Custom'): readonly BuildLane[] {
  return [
    { label: 'Recommend an evidence mix', result: 'Public evidence roles proposed for review', state: 'proposed' },
    { label: 'Draft the concept model', result: 'Entities, concepts, and relationships proposed', state: 'proposed' },
    { label: 'Draft the watch model', result: `${watchCount} starting areas proposed`, state: 'proposed' },
    { label: 'Activate and assemble a first cited Brief', result: 'Not supported for Custom Intelligence in v1', state: 'preview' },
  ]
}

function BuildContextRail({
  profile,
  subject,
  outcome,
  selectedSourceGroups,
  proposedSourceCount,
  cadenceLabel,
  preparedPlan,
  systemProjection,
  customPreview,
}: {
  readonly profile: IntelligenceOnboardingProfile
  readonly subject: string
  readonly outcome: IntelligenceOnboardingOutcome
  readonly selectedSourceGroups: readonly IntelligenceOnboardingSourceGroup[]
  readonly proposedSourceCount: number
  readonly cadenceLabel: string
  readonly preparedPlan: IntelligenceBuildPlan | null
  readonly systemProjection: IntelligenceSystemProjection | null
  readonly customPreview: boolean
}) {
  const review = preparedPlan?.review_projection ?? null
  const sources = review === null
    ? selectedSourceGroups.map((group) => group.label).join(' · ') || 'No evidence selected'
    : `${review.sources.length} exact source binding${review.sources.length === 1 ? '' : 's'}`
  const blueprint = systemProjection === null
    ? outcome.recommended_topic_labels.length === 0
      ? 'Generated model pending review'
      : outcome.recommended_topic_labels.slice(0, 3).join(' · ')
    : `${systemProjection.blueprint.elements.length} exact elements`
  const changes = systemProjection !== null
    ? `${systemProjection.changes.length} canonical change${systemProjection.changes.length === 1 ? '' : 's'}`
    : review === null
    ? customPreview ? 'Local draft · runtime unavailable' : 'Exact change set pending'
    : `${review.effects.length} reviewable effect${review.effects.length === 1 ? '' : 's'}`

  const rows = [
    { label: 'Domain', value: `${profile.domain_label} · ${profile.topic_label}` },
    { label: 'Intent', value: subject.trim() || 'Not yet described' },
    { label: 'Blueprint', value: blueprint },
    { label: 'Source plan', value: `${sources}${review === null && proposedSourceCount > 0 ? ` · ${proposedSourceCount} proposed` : ''}` },
    { label: 'Cadence', value: cadenceLabel },
    { label: 'Change set', value: changes },
  ]

  return (
    <aside aria-label="Build context" className="border-t border-border pt-5 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
      <div className="font-mono text-[8px] uppercase tracking-[0.16em] text-muted-foreground">Build context</div>
      <dl className="mt-3">
        {rows.map((row) => (
          <div key={row.label} className="border-t border-border py-3 first:border-t-0">
            <dt className="font-mono text-[7px] uppercase tracking-[0.12em] text-muted-foreground">{row.label}</dt>
            <dd className="mt-1 text-[10px] leading-4 text-foreground/80">{row.value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 border-t border-border pt-4">
        <div className="flex items-center gap-2 text-[10px] font-medium text-foreground">
          <LockKeyhole className="size-3.5 text-muted-foreground" aria-hidden="true" /> Authority not granted
        </div>
        <p className="mt-2 text-[9px] leading-4 text-muted-foreground">
          {systemProjection === null
            ? 'Predicted coverage and binding readiness are not projected by the current review material.'
            : 'Permission, readiness, predicted coverage, and observed coverage remain separate; unsupported values are not converted into scores.'}
        </p>
      </div>
    </aside>
  )
}

export function OnboardingPreview({
  open,
  onOpenChange,
  profiles,
  session,
  onPrepareBuild,
  onProjectBuild,
  activationSetup = {
    state: 'unavailable',
    detail: 'This host has no reviewed activation approval or exact bindings.',
  },
  onBindBuild,
  onApproveBuild,
  onAssociateBuilderSession,
  onPrepareActivationPlan,
  onApproveActivationPlan,
  onActivatePlan,
  onStartBuild,
  onProjectResourceState,
  onRetryBuild,
  onBuildStarted,
  onOpenBrief,
}: {
  readonly open: boolean
  readonly onOpenChange: (open: boolean) => void
  readonly profiles: readonly IntelligenceOnboardingProfile[]
  readonly session: IntelligenceBuilderSession | null
  readonly onPrepareBuild: (request: IntelligenceBuildPlanPrepareInput) => Promise<IntelligenceBuildPlan>
  readonly onProjectBuild?: (plan: IntelligenceBuildPlan) => Promise<IntelligenceSystemProjection>
  readonly activationSetup?: IntelligenceBuildActivationSetup
  readonly onBindBuild?: (request: IntelligenceBuildPlanBindInput) => Promise<BoundIntelligenceBuildPlan>
  readonly onApproveBuild?: (boundPlan: BoundIntelligenceBuildPlan) => Promise<IntelligenceBuildApprovalResult>
  readonly onAssociateBuilderSession?: (
    boundPlan: BoundIntelligenceBuildPlan,
    approvalReceiptRef: string,
  ) => Promise<IntelligenceBuildSessionAssociationResult>
  readonly onPrepareActivationPlan?: (input: DomainActivationPlanPrepareInput) => Promise<IntelligenceActivationPlan>
  readonly onApproveActivationPlan?: (input: DomainActivationPlanApproveInput) => Promise<DomainActivationCommitReference>
  readonly onActivatePlan?: (input: IntelligenceBuilderPlanActivateInput) => Promise<IntelligenceBuilderActivationResult>
  readonly onStartBuild?: (request: IntelligenceBuildStartInput) => Promise<IntelligenceBuildResult>
  readonly onProjectResourceState?: (input: IntelligenceBuildResourceStateInput) => Promise<IntelligenceSystemProjection>
  readonly onRetryBuild?: (current: Readonly<Record<string, unknown>>) => Promise<Readonly<Record<string, unknown>>>
  readonly onBuildStarted?: (result: IntelligenceBuildResult) => void | Promise<void>
  readonly onOpenBrief: () => void
}) {
  const [profileId, setProfileId] = useState(profiles[0].profile_id)
  const profile = useMemo(
    () => profiles.find((item) => item.profile_id === profileId) ?? profiles[0],
    [profileId, profiles],
  )
  const [step, setStep] = useState(0)
  const [subject, setSubject] = useState(profile.starter_prompts[0] ?? '')
  const [outcomeId, setOutcomeId] = useState(profile.outcomes[0]?.outcome_id ?? '')
  const [cadenceId, setCadenceId] = useState(profile.default_cadence_id)
  const [sourceGroupIds, setSourceGroupIds] = useState<readonly string[]>(() =>
    profile.source_groups.filter((group) => group.default_selected).map((group) => group.source_group_id),
  )
  const [planPending, setPlanPending] = useState(false)
  const [planError, setPlanError] = useState<PlanErrorState | null>(null)
  const [preparedInput, setPreparedInput] = useState<IntelligenceBuildPlanPrepareInput | null>(null)
  const [preparedPlan, setPreparedPlan] = useState<IntelligenceBuildPlan | null>(null)
  const [systemProjection, setSystemProjection] = useState<IntelligenceSystemProjection | null>(null)
  const [projectionError, setProjectionError] = useState<string | null>(null)
  const [activationPending, setActivationPending] = useState(false)
  const [activationError, setActivationError] = useState<PlanErrorState | null>(null)
  const [activationPlanPreview, setActivationPlanPreview] = useState<IntelligenceActivationPlan | null>(null)
  const [activationPlanNotice, setActivationPlanNotice] = useState<string | null>(null)
  const [activationPlanPending, setActivationPlanPending] = useState(false)
  const [activationPlanError, setActivationPlanError] = useState<PlanErrorState | null>(null)
  const [pendingActivationPlan, setPendingActivationPlan] = useState<{
    readonly current: Readonly<Record<string, unknown>>
    readonly bound: BoundIntelligenceBuildPlan
    readonly approval: IntelligenceBuildApprovalResult
  } | null>(null)
  const [buildResult, setBuildResult] = useState<IntelligenceBuildResult | null>(null)
  const [resourceStateProjection, setResourceStateProjection] = useState<IntelligenceSystemProjection | null>(null)
  const [resourceStateError, setResourceStateError] = useState<string | null>(null)
  const [retryPending, setRetryPending] = useState(false)
  const [retryError, setRetryError] = useState<PlanErrorState | null>(null)
  const [retrySession, setRetrySession] = useState<IntelligenceBuilderSession | null>(null)
  const [associatedSession, setAssociatedSession] = useState<IntelligenceBuilderSession | null>(null)
  const outcome = useMemo(() => profile.outcomes.find((item) => item.outcome_id === outcomeId) ?? profile.outcomes[0], [outcomeId, profile.outcomes])
  const selectedSourceGroups = useMemo(
    () => profile.source_groups.filter((group) => sourceGroupIds.includes(group.source_group_id)),
    [profile.source_groups, sourceGroupIds],
  )
  const proposedSourceCount = selectedSourceGroups.reduce((total, group) => total + group.source_ids.length, 0)
  const cadenceLabel = profile.cadences.find((item) => item.cadence_id === cadenceId)?.label ?? 'Not selected'
  const customPreview = isCustomPreviewProfile(profile)
  const activeSession = profile.profile_id === profiles[0]?.profile_id ? session : null
  const acceptedSession = buildResult === null ? null : onboardingSessionFromResources(buildResult.resource_page.items)
  const effectiveSession = retrySession ?? associatedSession ?? activeSession ?? acceptedSession
  const firstBriefReady = effectiveSession !== null && STAGE_RANK[effectiveSession.stage] >= STAGE_RANK.first_briefing_ready
  const activationEligibleSession = buildResult === null
    && (effectiveSession === null || effectiveSession.stage === 'first_briefing_ready')
  const lanes = customPreview
    ? customPreviewLanes(outcome.recommended_topic_labels.length || 'Custom')
    : buildLanes(effectiveSession, resourceStateProjection)
  const evidenceRequired = profile.source_groups.length > 0
  const canContinue = step === 1
    ? subject.trim().length >= 8
    : step !== 2 || !evidenceRequired || selectedSourceGroups.length > 0
  const stepLabels = customPreview ? CUSTOM_PREVIEW_STEP_LABELS : STEP_LABELS
  const semanticStages = semanticOnboardingStages({
    subject,
    plan: preparedPlan,
    session: effectiveSession,
    customPreview,
  })
  const activationUnavailableDetail = activationSetup.state === 'unavailable'
    ? activationSetup.detail
    : 'This host has no activation binding or start handler.'
  const activationPlanHandlersConfigured = onPrepareActivationPlan !== undefined
    && onApproveActivationPlan !== undefined
    && onActivatePlan !== undefined

  useEffect(() => {
    if (!profiles.some((item) => item.profile_id === profileId)) setProfileId(profiles[0].profile_id)
  }, [profileId, profiles])

  useEffect(() => {
    if (open) setProfileId(profiles[0].profile_id)
  }, [open, profiles])

  useEffect(() => {
    setOutcomeId(profile.outcomes[0]?.outcome_id ?? '')
    setCadenceId(profile.default_cadence_id)
    setSubject(profile.starter_prompts[0] ?? '')
    setSourceGroupIds(
      profile.source_groups.filter((group) => group.default_selected).map((group) => group.source_group_id),
    )
    setPreparedInput(null)
    setPreparedPlan(null)
    setSystemProjection(null)
    setProjectionError(null)
    setPlanError(null)
    setActivationError(null)
    setActivationPlanPreview(null)
    setActivationPlanNotice(null)
    setActivationPlanError(null)
    setPendingActivationPlan(null)
    setBuildResult(null)
    setResourceStateProjection(null)
    setResourceStateError(null)
    setRetryError(null)
    setRetrySession(null)
    setAssociatedSession(null)
  }, [profile])

  function invalidatePreparedPlan() {
    setPreparedInput(null)
    setPreparedPlan(null)
    setSystemProjection(null)
    setProjectionError(null)
    setPlanError(null)
    setActivationError(null)
    setActivationPlanPreview(null)
    setActivationPlanNotice(null)
    setActivationPlanError(null)
    setPendingActivationPlan(null)
    setBuildResult(null)
    setResourceStateProjection(null)
    setResourceStateError(null)
    setAssociatedSession(null)
  }

  function toggleSourceGroup(sourceGroupId: string) {
    invalidatePreparedPlan()
    setSourceGroupIds((current) => current.includes(sourceGroupId)
      ? current.filter((item) => item !== sourceGroupId)
      : [...current, sourceGroupId])
  }

  function close(next: boolean) {
    onOpenChange(next)
    if (!next) setStep(0)
    if (!next) setPlanError(null)
  }

  async function preparePlan() {
    if (customPreview) {
      setPlanError(null)
      setStep(3)
      return
    }
    if (profile.profile_digest === null) {
      setPlanError(planErrorState(new IntelligenceBuildApiError(503, 'The installed profile has no exact digest.')))
      return
    }
    const exactInput = preparedInput ?? createIntelligenceBuildPlanPrepareInput({
      profile_id: profile.profile_id,
      profile_digest: profile.profile_digest,
      subject: subject.trim(),
      outcome_id: outcome.outcome_id,
      source_group_ids: sourceGroupIds,
      cadence_id: cadenceId,
    })
    setPreparedInput(exactInput)
    setPlanPending(true)
    setPlanError(null)
    try {
      const plan = await onPrepareBuild(exactInput)
      setPreparedPlan(plan)
      if (onProjectBuild === undefined) {
        setSystemProjection(null)
        setProjectionError('The canonical system projection is not connected in this host.')
      } else {
        try {
          setSystemProjection(await onProjectBuild(plan))
          setProjectionError(null)
        } catch (reason: unknown) {
          setSystemProjection(null)
          setProjectionError(reason instanceof Error ? reason.message : 'The canonical system projection is unavailable.')
        }
      }
      setStep(3)
    } catch (reason: unknown) {
      setPlanError(planErrorState(reason))
    } finally {
      setPlanPending(false)
    }
  }

  async function finishStart(bound: BoundIntelligenceBuildPlan, approval: IntelligenceBuildApprovalResult) {
    if (onStartBuild === undefined) return
    const result = await onStartBuild(approval.start_request)
    setBuildResult(result)
    setStep(4)
    await onBuildStarted?.(result)
    // This read-only enrichment must never replace or invalidate the
    // governed start result above: it runs after that result is already
    // recorded, in its own try/catch, using only the exact bound plan, the
    // server's own approval receipt, the server's own resource-authority
    // grant, and the server's own resource-page as_of/available_at.
    if (onProjectResourceState !== undefined) {
      try {
        const resourceStateInput = createIntelligenceBuildResourceStateInput(
          bound,
          approval.approval.receipt_ref,
          approval.start_request.resource_authority_grant_ref,
          result.resource_page,
        )
        setResourceStateProjection(await onProjectResourceState(resourceStateInput))
        setResourceStateError(null)
      } catch (reason: unknown) {
        setResourceStateProjection(null)
        setResourceStateError(
          reason instanceof Error ? reason.message : 'The live resource-state projection is unavailable.',
        )
      }
    }
  }

  async function activatePlan() {
    if (
      preparedPlan === null
      || activationSetup.state !== 'configured'
      || onBindBuild === undefined
      || onApproveBuild === undefined
      || onStartBuild === undefined
    ) return
    setActivationPending(true)
    setActivationError(null)
    setActivationPlanNotice(null)
    setActivationPlanError(null)
    setActivationPlanPreview(null)
    setPendingActivationPlan(null)
    try {
      if (activationPlanHandlersConfigured && effectiveSession === null && onAssociateBuilderSession === undefined) {
        setActivationPlanNotice('ACE has no current Builder session associated with this reviewed plan. The host cannot record that exact durable association, so no approval, authorization, or start was recorded.')
        return
      }
      const bound = await onBindBuild(createIntelligenceBuildPlanBindInput(preparedPlan, {
        capability_bindings: activationSetup.inputs.capability_bindings,
        authority_bindings: activationSetup.inputs.authority_bindings,
      }))
      const approval = await onApproveBuild(bound)
      let currentSession = effectiveSession
      if (activationPlanHandlersConfigured && currentSession === null) {
        if (onAssociateBuilderSession === undefined) {
          throw new IntelligenceBuildApiError(503, 'The reviewed-build association handler is unavailable.')
        }
        const association = await onAssociateBuilderSession(bound, approval.approval.receipt_ref)
        const parsed = parseBuilderSession(association.session)
        if (parsed === null || parsed.stage !== 'goal_selected' || parsed.exact_revision === null) {
          throw new IntelligenceBuildApiError(503, 'The reviewed-build association did not return the exact durable goal-selected Builder revision.')
        }
        currentSession = parsed
        setAssociatedSession(parsed)
      }
      const availability = activationPlanAvailability(currentSession, activationPlanHandlersConfigured)
      if (availability.state === 'unsupported') {
        await finishStart(bound, approval)
        return
      }
      if (availability.state === 'not_ready') {
        setActivationPlanNotice(availability.reason)
        setStep(4)
        return
      }
      if (onPrepareActivationPlan === undefined) {
        throw new IntelligenceBuildApiError(503, 'The activation-plan preview handler is unavailable.')
      }
      // A separate, distinct approval from the reviewed activation
      // specification's own `/approve` above: the preview is only
      // disclosed here, never auto-approved. Confirming it is a second,
      // explicit owner decision (confirmActivationPlan).
      const plan = await onPrepareActivationPlan(createDomainActivationPlanPrepareInput(
        availability.current,
        bound,
        approval.approval.approved_at,
      ))
      setActivationPlanPreview(plan)
      setPendingActivationPlan({ current: availability.current, bound, approval })
    } catch (reason: unknown) {
      setActivationError(activationErrorState(reason))
    } finally {
      setActivationPending(false)
    }
  }

  async function confirmActivationPlan() {
    if (
      pendingActivationPlan === null
      || onApproveActivationPlan === undefined
      || onActivatePlan === undefined
    ) return
    const { current, bound, approval } = pendingActivationPlan
    setActivationPlanPending(true)
    setActivationPlanError(null)
    try {
      await onApproveActivationPlan(createDomainActivationPlanApproveInput(current, bound, approval.approval.approved_at))
      await onActivatePlan(createIntelligenceBuilderPlanActivateInput(
        bound,
        approval.approval.receipt_ref,
        approval.approval.approved_at,
      ))
      await finishStart(bound, approval)
      setActivationPlanPreview(null)
      setPendingActivationPlan(null)
    } catch (reason: unknown) {
      setActivationPlanError(activationErrorState(reason))
    } finally {
      setActivationPlanPending(false)
    }
  }

  async function retryBuild() {
    if (effectiveSession?.stage !== 'blocked' || effectiveSession.exact_revision == null || onRetryBuild === undefined) return
    setRetryPending(true)
    setRetryError(null)
    try {
      const revision = await onRetryBuild(effectiveSession.exact_revision)
      const parsed = parseBuilderSession(revision)
      if (parsed === null || parsed.stage !== 'retrying') {
        throw new IntelligenceBuildApiError(409, 'ACE returned a retry result that did not preserve the exact Builder session contract.')
      }
      setRetrySession(parsed)
    } catch (reason: unknown) {
      setRetryError(activationErrorState(reason))
    } finally {
      setRetryPending(false)
    }
  }

  function finish() {
    close(false)
    if (firstBriefReady) onOpenBrief()
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="atrium-command-center dark max-h-[calc(100svh-2rem)] overflow-y-auto rounded-md border-border bg-popover p-0 sm:max-w-6xl">
        <div className="border-b px-6 py-4 sm:px-8">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.17em] text-brand">
              <BuildIcon className="size-3.5" aria-hidden="true" /> Build your intelligence
            </div>
            <Badge variant="outline" className="mr-6 rounded-sm font-mono text-[9px]">
              {customPreview
                ? 'Custom · Preview'
                : planPending
                  ? 'Preparing'
                  : step < 4
                    ? 'Plan review'
                    : activeSession === null
                      ? 'Plan ready'
                      : `Builder · revision ${activeSession.sequence}`}
            </Badge>
          </div>
          <ol className="mt-3 grid grid-cols-5 gap-1.5" aria-label={`Step ${step + 1} of 5: ${stepLabels[step]}`}>
            {stepLabels.map((label, index) => (
              <li key={label} className="min-w-0" aria-current={index === step ? 'step' : undefined}>
                <div className={`h-1 rounded-full ${index <= step ? 'bg-brand' : 'bg-border'}`} />
                <div className={`mt-1.5 hidden truncate font-mono text-[8px] uppercase tracking-[0.12em] sm:block ${index === step ? 'text-brand' : 'text-muted-foreground'}`}>{label}</div>
                <span className="sr-only">{label}: {index < step ? 'complete' : index === step ? 'current' : 'upcoming'}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="px-6 py-7 sm:px-8">
          <div className={step > 0 && step < 4 ? 'grid gap-8 lg:grid-cols-[minmax(0,1fr)_15rem]' : ''}>
            <div className="min-w-0">
          {step === 0 && (
            <>
              <DialogHeader className="max-w-2xl">
                <DialogTitle className="text-2xl tracking-tight">What kind of intelligence do you want to build?</DialogTitle>
                <DialogDescription className="text-sm leading-relaxed">
                  Start with a proven domain or build a new one around your question. This choice gives ACE the vocabulary, evidence roles, and quality rules for the first picture.
                </DialogDescription>
              </DialogHeader>
              <div className="mt-6 grid gap-3 md:grid-cols-3">
                  {profiles.map((item) => {
                    const selected = item.profile_id === profile.profile_id
                    return (
                      <Button
                        key={item.profile_id}
                        type="button"
                        variant="ghost"
                        onClick={() => setProfileId(item.profile_id)}
                        aria-pressed={selected}
                        className={`h-auto min-h-44 w-full flex-col items-start justify-start whitespace-normal rounded-lg border p-5 text-left ${selected ? 'border-brand/70 bg-brand/7 ring-1 ring-brand/20' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}
                      >
                        <div className="flex w-full items-start justify-between gap-3">
                          <div className={`flex size-9 items-center justify-center rounded-md border ${selected ? 'border-brand/40 bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'}`}>
                            {item.profile_id.includes('custom') ? <Compass className="size-4" aria-hidden="true" /> : <BookOpenCheck className="size-4" aria-hidden="true" />}
                          </div>
                          <div className="flex items-center gap-1.5">
                            {isCustomPreviewProfile(item) && <Badge variant="outline" className="rounded-sm border-border bg-muted/30 font-mono text-[8px] text-muted-foreground">Preview</Badge>}
                            {selected && <Badge variant="outline" className="rounded-sm border-brand/30 font-mono text-[8px] text-brand">Selected</Badge>}
                          </div>
                        </div>
                        <div className="mt-5 text-base font-semibold">{item.domain_label}</div>
                        <div className="mt-1 text-xs font-medium text-foreground/85">{item.topic_label}</div>
                        <p className="mt-3 text-[11px] font-normal leading-relaxed text-muted-foreground">{item.description}</p>
                      </Button>
                    )
                  })}
              </div>
              <div className="mt-4 flex items-start gap-3 rounded-lg border border-border bg-muted/25 p-4">
                {customPreview
                  ? <FlaskConical className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  : <BookOpenCheck className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
                <div>
                  <div className="text-xs font-medium text-foreground">{customPreview ? 'Custom Intelligence is a proposal preview.' : `${profile.display_name} is ready to specialize.`}</div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {customPreview
                      ? 'ACE can draft an evidence mix, concept model, watches, and cadence for review. v1 stops before source activation and does not run a Custom first-Brief executor.'
                      : 'Next, tell ACE what you need to understand or decide. Nothing connects or starts watching until you review the plan.'}
                  </p>
                </div>
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <DialogHeader className="max-w-2xl">
                <DialogTitle className="text-2xl font-normal tracking-[-0.025em]">What should ACE understand?</DialogTitle>
                <DialogDescription className="text-sm leading-relaxed">
                  Describe the changing subject or decision in plain language. ACE will specialize {profile.domain_label}, then propose the model and evidence plan for review.
                </DialogDescription>
              </DialogHeader>
              <div className="mt-5">
                <Textarea
                  aria-label="Describe the intelligence you want"
                  value={subject}
                  onChange={(event) => {
                    invalidatePreparedPlan()
                    setSubject(event.target.value)
                  }}
                  placeholder="For example: Keep me ahead of meaningful AI capability, cost, policy, and adoption shifts."
                  className="min-h-24 rounded-lg border-border bg-card px-4 py-3 text-sm leading-relaxed"
                />
                {profile.starter_prompts.length > 1 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {profile.starter_prompts.slice(1).map((prompt) => (
                      <Button key={prompt} type="button" variant="outline" size="sm" className="h-auto whitespace-normal rounded-md py-1.5 text-left text-[10px] text-muted-foreground" onClick={() => {
                        invalidatePreparedPlan()
                        setSubject(prompt)
                      }}>{prompt}</Button>
                    ))}
                  </div>
                )}
              </div>
              <div className="mt-6 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">{profile.prompt}</div>
              <div className="mt-6 grid gap-3 md:grid-cols-2">
                {profile.outcomes.map((item) => {
                  const selected = item.outcome_id === outcomeId
                  return (
                    <Button key={item.outcome_id} type="button" variant="ghost" aria-pressed={selected} onClick={() => {
                      invalidatePreparedPlan()
                      setOutcomeId(item.outcome_id)
                    }} className={`h-auto w-full justify-start gap-4 whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-brand/70 bg-brand/7' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}>
                      <div className={`flex size-9 shrink-0 items-center justify-center rounded-md border ${selected ? 'border-brand/40 bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'}`}><OutcomeIcon outcome={item} /></div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 text-sm font-semibold">{item.label}{selected && <Check className="size-3.5 text-brand" aria-hidden="true" />}</div>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.description}</p>
                      </div>
                    </Button>
                  )
                })}
              </div>
              <div className="mt-6">
                <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">How often should ACE orient you?</div>
                <div className="mt-3 grid gap-2 md:grid-cols-3">
                  {profile.cadences.map((cadence) => {
                    const selected = cadence.cadence_id === cadenceId
                    return <Button key={cadence.cadence_id} type="button" variant="ghost" aria-pressed={selected} onClick={() => {
                      invalidatePreparedPlan()
                      setCadenceId(cadence.cadence_id)
                    }} className={`h-auto w-full flex-col items-start whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-brand/70 bg-brand/7' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}><div className="flex items-center gap-2 text-sm font-semibold"><CircleDot className={`size-3.5 ${selected ? 'text-brand' : 'text-muted-foreground'}`} aria-hidden="true" />{cadence.label}</div><p className="mt-1 pl-5 text-xs font-normal text-muted-foreground">{cadence.description}</p></Button>
                  })}
                </div>
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <DialogHeader className="max-w-2xl">
                <DialogTitle className="text-2xl tracking-tight">Choose the evidence ACE can use</DialogTitle>
                <DialogDescription>
                  Start with a balanced public picture. These are proposed source groups—not silent connections—and every record keeps its publisher and evidence role.
                </DialogDescription>
              </DialogHeader>
              {profile.source_groups.length > 0 ? (
                <>
                  <div className="mt-6 grid gap-3 md:grid-cols-2">
                    {profile.source_groups.map((group) => {
                      const selected = sourceGroupIds.includes(group.source_group_id)
                      return (
                        <Button
                          key={group.source_group_id}
                          type="button"
                          variant="ghost"
                          onClick={() => toggleSourceGroup(group.source_group_id)}
                          aria-pressed={selected}
                          className={`h-auto min-h-40 w-full flex-col items-stretch justify-start whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-brand/70 bg-brand/7' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}
                        >
                          <div className="flex items-start gap-3">
                            <div className={`flex size-9 shrink-0 items-center justify-center rounded-md border ${selected ? 'border-brand/40 bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'}`}><SourceIcon group={group} /></div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 text-sm font-semibold">{group.label}{selected && <Check className="size-3.5 text-brand" aria-hidden="true" />}</div>
                              <p className="mt-1 text-xs font-normal leading-relaxed text-muted-foreground">{group.description}</p>
                            </div>
                          </div>
                          <div className="mt-auto flex flex-wrap items-center gap-1.5 border-t pt-3">
                            {group.source_labels.slice(0, 4).map((label) => <Badge key={label} variant="secondary" className="rounded-sm font-normal">{label}</Badge>)}
                            {group.source_labels.length > 4 && <Badge variant="outline" className="rounded-sm font-mono text-[9px]">+{group.source_labels.length - 4}</Badge>}
                          </div>
                          <div className="mt-2 flex items-center justify-between gap-3 font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">
                            <span>{group.source_ids.length} sources</span><span>{group.access_label}</span>
                          </div>
                        </Button>
                      )
                    })}
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
                    <PlugZap className="size-3.5 text-muted-foreground" aria-hidden="true" /> {selectedSourceGroups.length} groups · {proposedSourceCount} sources proposed
                  </div>
                </>
              ) : (
                <div className="mt-6 rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                  ACE will propose a balanced mix of primary records, first-party claims, independent evidence, telemetry, and leading indicators for review.
                </div>
              )}
            </>
          )}

          {step === 3 && (
            customPreview ? (
              <>
                <DialogHeader className="max-w-2xl"><DialogTitle className="text-2xl tracking-tight">Review what ACE will build</DialogTitle><DialogDescription>Public evidence creates the first picture. Private sources remain optional and require explicit permission.</DialogDescription></DialogHeader>
                <PlanLedger rows={[
                  { label: 'Evidence', value: 'Recommended public mix', detail: 'Primary records, first-party claims, independent measurement, operational telemetry, and leading indicators.' },
                  { label: 'Concept map', value: `${outcome.recommended_topic_labels.length || 'Custom'} starting concepts`, detail: outcome.recommended_topic_labels.length > 0 ? outcome.recommended_topic_labels.join(' · ') : 'Entities, aliases, attributes, relationships, claims, events, and outcomes.' },
                  { label: 'Watches', value: `${outcome.recommended_topic_labels.length || 'Custom'} starting areas`, detail: 'Material changes, contradictions, catalysts, and weak signals—scoped to your selected job.' },
                  { label: 'Briefing', value: 'Preview only', detail: `Cadence captured: ${profile.cadences.find((item) => item.cadence_id === cadenceId)?.label ?? 'Selected cadence'}. v1 does not activate this Custom plan or run a first-Brief executor.` },
                ]} />
                <div className="mt-5 grid border-y border-border md:grid-cols-[minmax(0,1fr)_12rem]">
                  <div className="flex items-start gap-3 border-b border-border bg-muted/20 p-4 md:border-b-0 md:border-r"><Scale className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" /><p className="text-xs leading-relaxed text-muted-foreground"><span className="font-medium text-foreground">Nothing is connected or activated silently.</span> This Custom preview is a local draft and makes no server request.</p></div>
                  <div className="flex items-center gap-3 px-4 py-3">
                    <FlaskConical className="size-4 text-muted-foreground" aria-hidden="true" />
                    <div><div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">Preview boundary</div><div className="mt-0.5 text-xs font-medium">Draft proposal only</div></div>
                  </div>
                </div>
              </>
            ) : preparedPlan?.review_projection !== null && preparedPlan?.review_projection !== undefined ? (
              <>
                <ExactPlanReview plan={preparedPlan} projection={systemProjection} projectionError={projectionError} />
                <ActivationInputReview plan={preparedPlan} setup={activationSetup} twoDecisions={activationPlanHandlersConfigured} />
                {activationPlanPreview !== null && <ActivationPlanPreviewReview plan={activationPlanPreview} />}
              </>
            ) : null
          )}

          {step === 4 && (
            <>
              <DialogHeader className="max-w-2xl">
                <DialogTitle className="text-2xl tracking-tight">{customPreview ? 'Your Custom proposal is ready' : firstBriefReady ? 'Your first picture is ready' : effectiveSession?.stage === 'blocked' ? 'ACE needs your attention' : effectiveSession?.stage === 'retrying' ? 'Retry recorded' : effectiveSession === null ? 'Builder state is not available' : 'Initialization status'}</DialogTitle>
                <DialogDescription>
                  {customPreview
                    ? 'This is a draft model for review. ACE has not connected sources, activated watches, or run a first-Brief executor.'
                    : effectiveSession === null
                    ? 'No durable Builder session is associated with this view. The reviewed plan alone does not prove permission, readiness, admission, or runtime progress.'
                    : firstBriefReady
                      ? 'A durable first-briefing-ready revision is recorded. Open the cited result in Overview; maintenance remains a separate status below.'
                      : effectiveSession.stage === 'blocked'
                        ? 'The durable session stopped safely at the named stage. Retry is offered only when the exact blocked revision is available.'
                        : effectiveSession.stage === 'retrying'
                          ? 'The retry request is durable. Only a later Builder revision can confirm that initialization continued.'
                          : `The latest durable Builder revision is ${effectiveSession.stage.replace(/_/g, ' ')}. No later progress is inferred.`}
                </DialogDescription>
              </DialogHeader>
              <div className="mt-7 space-y-2" role="list" aria-label="Source readiness, initialization, and first-Brief status">
                {lanes.map((lane) => <BuildStep key={lane.label} {...lane} />)}
              </div>
              <div className="mt-5 rounded-lg border bg-card p-4 text-xs text-muted-foreground">
                {customPreview
                  ? 'Preview complete · No runtime execution performed'
                  : effectiveSession === null
                  ? 'No durable Builder revision is available for this reviewed plan.'
                  : effectiveSession.stage === 'active'
                    ? `Builder revision ${effectiveSession.sequence} · Continuous maintenance active`
                    : effectiveSession.stage === 'activation_pending'
                      ? `Builder revision ${effectiveSession.sequence} · Exact Core admission pending`
                      : firstBriefReady
                        ? `Builder revision ${effectiveSession.sequence} · First cited Brief ready · Maintenance not active`
                        : `Builder revision ${effectiveSession.sequence} · ${effectiveSession.stage.replace(/_/g, ' ')}`}
              </div>
              {onProjectResourceState !== undefined && buildResult !== null && (
                <SystemProjectionReview projection={resourceStateProjection} error={resourceStateError} />
              )}
            </>
          )}
          {(step === 3 || step === 4) && <SemanticJourney stages={semanticStages} />}
          {planError !== null && (
            <div role="alert" className="mt-5 flex items-start gap-3 rounded-lg border border-destructive/45 bg-destructive/5 p-4 text-xs text-destructive">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div>
                <div className="font-semibold">{planError.title}</div>
                <div className="mt-1 text-destructive/85">{planError.detail}</div>
                {planError.status > 0 && <div className="mt-2 font-mono text-[8px] uppercase tracking-[0.12em] text-destructive/70">Prepare response · {planError.status}</div>}
              </div>
            </div>
          )}
          {activationError !== null && (
            <div role="alert" className="mt-5 flex items-start gap-3 rounded-lg border border-destructive/45 bg-destructive/5 p-4 text-xs text-destructive">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div>
                <div className="font-semibold">{activationError.title}</div>
                <div className="mt-1 text-destructive/85">{activationError.detail}</div>
                {activationError.status > 0 && <div className="mt-2 font-mono text-[8px] uppercase tracking-[0.12em] text-destructive/70">Activation response · {activationError.status}</div>}
              </div>
            </div>
          )}
          {activationPlanNotice !== null && <ActivationPlanNotice reason={activationPlanNotice} />}
          {activationPlanError !== null && (
            <div role="alert" className="mt-5 flex items-start gap-3 rounded-lg border border-destructive/45 bg-destructive/5 p-4 text-xs text-destructive">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div>
                <div className="font-semibold">{activationPlanError.title}</div>
                <div className="mt-1 text-destructive/85">{activationPlanError.detail}</div>
                {activationPlanError.status > 0 && <div className="mt-2 font-mono text-[8px] uppercase tracking-[0.12em] text-destructive/70">Activation-plan response · {activationPlanError.status}</div>}
              </div>
            </div>
          )}
          {retryError !== null && (
            <div role="alert" className="mt-5 flex items-start gap-3 rounded-lg border border-destructive/45 bg-destructive/5 p-4 text-xs text-destructive">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div>
                <div className="font-semibold">ACE could not retry this exact session.</div>
                <div className="mt-1 text-destructive/85">{retryError.detail}</div>
                {retryError.status > 0 && <div className="mt-2 font-mono text-[8px] uppercase tracking-[0.12em] text-destructive/70">Retry response · {retryError.status}</div>}
              </div>
            </div>
          )}
            </div>
            {step > 0 && step < 4 && (
              <BuildContextRail
                profile={profile}
                subject={subject}
                outcome={outcome}
                selectedSourceGroups={selectedSourceGroups}
                proposedSourceCount={proposedSourceCount}
                cadenceLabel={cadenceLabel}
                preparedPlan={preparedPlan}
                systemProjection={systemProjection}
                customPreview={customPreview}
              />
            )}
          </div>
        </div>

        <div className="flex items-center justify-between border-t px-6 py-4 sm:px-8">
          <Button type="button" variant="ghost" disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}><ArrowLeft className="size-4" aria-hidden="true" /> Back</Button>
          {step < 4
            ? step === 3 && !customPreview && activationEligibleSession
              ? activationSetup.state === 'configured' && onBindBuild !== undefined && onApproveBuild !== undefined && onStartBuild !== undefined
                ? activationPlanPreview !== null
                  ? <div className="flex items-center gap-3"><span className="hidden max-w-56 text-right text-[10px] leading-relaxed text-muted-foreground sm:block">Starts ACE: connects sources, runs the watches, and keeps maintaining this system.</span><Button type="button" disabled={activationPlanPending} onClick={() => void confirmActivationPlan()}>{activationPlanPending ? <><LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Authorizing</> : <><Check className="size-4" aria-hidden="true" /> Authorize ACE to start and maintain</>}</Button></div>
                  : <div className="flex items-center gap-3"><span className="hidden max-w-56 text-right text-[10px] leading-relaxed text-muted-foreground sm:block">{activationPlanHandlersConfigured ? 'Locks in the sources, authority, and system spec you reviewed. ACE will ask you to separately authorize starting and maintaining it next.' : 'Locks in the sources, authority, and system spec you reviewed, then starts ACE — connecting sources and building your first Brief.'}</span><Button type="button" disabled={activationPending} onClick={() => void activatePlan()}>{activationPending ? <><LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Recording approval</> : activationPlanHandlersConfigured ? <><Check className="size-4" aria-hidden="true" /> Approve reviewed plan</> : <><Check className="size-4" aria-hidden="true" /> Approve and initialize</>}</Button></div>
                : <div className="flex items-center gap-3"><span className="hidden max-w-56 text-right text-[10px] leading-relaxed text-muted-foreground sm:block">{activationUnavailableDetail}</span><Button type="button" disabled><LockKeyhole className="size-4" aria-hidden="true" /> Activation unavailable</Button></div>
              : <Button type="button" disabled={!canContinue || planPending} onClick={() => {
                if (step === 2) void preparePlan()
                else if (step === 3) setStep(4)
                else setStep((value) => Math.min(3, value + 1))
              }}>{planPending ? <><LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Preparing exact plan</> : <>{step === 0 ? customPreview ? 'Preview this intelligence' : 'Use this intelligence' : step === 1 ? 'Choose evidence' : step === 2 ? customPreview ? 'Review the plan' : preparedInput === null ? 'Prepare exact plan' : 'Retry exact plan' : customPreview ? 'View draft proposal' : 'View build status'} <ArrowRight className="size-4" aria-hidden="true" /></>}</Button>
            : effectiveSession?.stage === 'blocked'
              ? effectiveSession.exact_revision != null && onRetryBuild !== undefined
                ? <Button type="button" disabled={retryPending} onClick={() => void retryBuild()}>{retryPending ? <><LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Requesting retry</> : <><RefreshCw className="size-4" aria-hidden="true" /> Retry governed step</>}</Button>
                : <div className="flex items-center gap-3"><span className="hidden max-w-64 text-right text-[10px] leading-relaxed text-muted-foreground sm:block">The loaded session does not include the exact durable revision required for a safe retry.</span><Button type="button" disabled><LockKeyhole className="size-4" aria-hidden="true" /> Retry unavailable</Button></div>
              : <Button type="button" onClick={finish}>{firstBriefReady ? profile.completion_label : 'Return to Atrium'} <ArrowRight className="size-4" aria-hidden="true" /></Button>}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function SemanticJourney({ stages }: { readonly stages: readonly SemanticOnboardingStage[] }) {
  const stateLabel: Record<SemanticOnboardingStage['state'], string> = {
    complete: 'Complete',
    current: 'Current',
    waiting: 'Waiting',
    blocked: 'Needs attention',
    unsupported: 'Not supported',
    preview: 'Preview',
  }
  return (
    <details className="mt-7 border-t pt-5">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-xs font-medium">
        <span>View exact lifecycle stages</span>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px]">8 stages</Badge>
      </summary>
      <ol className="mt-4 border-y" aria-label="Eight semantic onboarding stages">
        {stages.map((stage) => (
          <li key={stage.id} className="grid gap-2 border-t py-3 first:border-t-0 sm:grid-cols-[2rem_8rem_minmax(0,1fr)_auto] sm:items-start">
            <span className="font-mono text-[9px] text-muted-foreground">{String(stage.number).padStart(2, '0')}</span>
            <div>
              <div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">{stage.chapter}</div>
              <div className="mt-1 text-xs font-medium">{stage.label}</div>
            </div>
            <p className="text-[10px] leading-4 text-muted-foreground">{stage.detail}</p>
            <Badge variant="outline" className="w-fit rounded-sm font-mono text-[8px]">{stateLabel[stage.state]}</Badge>
          </li>
        ))}
      </ol>
    </details>
  )
}

function shortReference(value: string): string {
  return value.length <= 34 ? value : `${value.slice(0, 18)}…${value.slice(-10)}`
}

function ActivationInputReview({
  plan,
  setup,
  twoDecisions,
}: {
  readonly plan: IntelligenceBuildPlan
  readonly setup: IntelligenceBuildActivationSetup
  readonly twoDecisions: boolean
}) {
  const proposal = plan.activation_proposal
  const configuredCapabilities = setup.state === 'configured' ? setup.inputs.capability_bindings.length : 0
  const configuredAuthorities = setup.state === 'configured' ? setup.inputs.authority_bindings.length : 0
  const rows = [
    {
      label: 'Capability bindings',
      required: proposal?.capability_requirement_ids.length ?? 0,
      supplied: configuredCapabilities,
      detail: proposal === undefined
        ? 'This plan has no activation-neutral proposal to bind.'
        : proposal.capability_requirement_ids.length === 0
          ? 'The exact Pack declares no capability implementation binding.'
          : proposal.capability_requirement_ids.join(' · '),
    },
    {
      label: 'Authority bindings',
      required: proposal?.authority_request_ids.length ?? 0,
      supplied: configuredAuthorities,
      detail: proposal === undefined
        ? 'This plan has no activation-neutral proposal to bind.'
        : proposal.authority_request_ids.length === 0
          ? 'The exact Pack declares no additional source authority binding.'
          : proposal.authority_request_ids.join(' · '),
    },
  ]
  return (
    <section className="mt-7 border-t border-border pt-6" aria-labelledby="activation-input-readiness">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">{twoDecisions ? 'Decision 1 of 2 · Validate inputs' : 'Validate inputs'}</div>
          <h3 id="activation-input-readiness" className="mt-1 text-base font-semibold tracking-tight">Checked before ACE touches anything</h3>
        </div>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px]">
          {setup.state === 'configured' ? 'Supplied · pending validation' : 'Setup unavailable'}
        </Badge>
      </div>
      <dl className="mt-3 border-y border-border">
        {rows.map((row) => (
          <div key={row.label} className="grid gap-2 border-t border-border py-3 first:border-t-0 sm:grid-cols-[10rem_8rem_minmax(0,1fr)]">
            <dt className="text-[10px] font-medium">{row.label}</dt>
            <dd className="font-mono text-[8px] uppercase text-muted-foreground">{row.supplied} supplied · {row.required} required</dd>
            <dd className="break-all text-[9px] leading-4 text-muted-foreground">{row.detail}</dd>
          </div>
        ))}
        <div className="grid gap-2 border-t border-border py-3 sm:grid-cols-[10rem_8rem_minmax(0,1fr)]">
          <dt className="text-[10px] font-medium">Owner approval</dt>
          <dd className="font-mono text-[8px] uppercase text-muted-foreground">{setup.state === 'configured' ? 'Awaiting decision' : 'Unavailable'}</dd>
          <dd className="text-[9px] leading-4 text-muted-foreground">
            {setup.state === 'configured'
              ? 'Approve and initialize records a new receipt over this exact bound activation, then Core resolves it again at governed start.'
              : setup.detail}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-[9px] leading-4 text-muted-foreground">Binding validates exact Pack requirements. Governed start separately validates current permission, approval, executor availability, and runtime readiness.</p>
    </section>
  )
}

function ActivationPlanPreviewReview({ plan }: { readonly plan: IntelligenceActivationPlan }) {
  return (
    <section className="mt-7 border-t border-border pt-6" aria-labelledby="activation-plan-preview">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Decision 2 of 2 · Authorize &amp; maintain</div>
          <h3 id="activation-plan-preview" className="mt-1 text-base font-semibold tracking-tight">Nothing starts until you authorize this</h3>
        </div>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px]">{plan.action.replace(/_/g, ' ')}</Badge>
      </div>
      <div className="mt-3 flex items-start gap-3 rounded-lg border border-border bg-muted/20 p-4">
        <Eye className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <p className="text-xs leading-relaxed text-muted-foreground">
          You already approved the reviewed sources, authority, and system spec. This exact activation plan is recorded and approved separately — confirming it is what tells ACE to start: connect sources, run the watches, and keep maintaining this system from here on. Nothing has started yet.
        </p>
      </div>
      <dl className="mt-3 border-y border-border">
        <div className="grid gap-2 border-t border-border py-3 first:border-t-0 sm:grid-cols-[10rem_minmax(0,1fr)]">
          <dt className="text-[10px] font-medium">Activation key</dt>
          <dd className="break-all font-mono text-[9px] text-muted-foreground">{plan.spec.activation_key}</dd>
        </div>
        <div className="grid gap-2 border-t border-border py-3 sm:grid-cols-[10rem_minmax(0,1fr)]">
          <dt className="text-[10px] font-medium">Requested effects</dt>
          <dd className="font-mono text-[9px] text-muted-foreground">{plan.requested_effects.join(' · ')}</dd>
        </div>
        <div className="grid gap-2 border-t border-border py-3 sm:grid-cols-[10rem_minmax(0,1fr)]">
          <dt className="text-[10px] font-medium">Plan identity</dt>
          <dd className="break-all font-mono text-[9px] text-muted-foreground">{shortReference(plan.plan_id)}</dd>
        </div>
      </dl>
    </section>
  )
}

function ActivationPlanNotice({ reason }: { readonly reason: string }) {
  return (
    <div className="mt-5 flex items-start gap-3 rounded-lg border border-border bg-muted/20 p-4 text-xs text-muted-foreground">
      <LockKeyhole className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div>
        <div className="font-medium text-foreground">ACE cannot ask you to authorize maintenance yet.</div>
        <div className="mt-1">{reason}</div>
      </div>
    </div>
  )
}

function ExactPlanReview({
  plan,
  projection,
  projectionError,
}: {
  readonly plan: IntelligenceBuildPlan
  readonly projection: IntelligenceSystemProjection | null
  readonly projectionError: string | null
}) {
  const review = plan.review_projection
  if (review === null) return null
  return (
    <>
      <DialogHeader className="max-w-3xl">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="rounded-sm border-border bg-muted/25 font-mono text-[8px] uppercase tracking-[0.12em] text-foreground/75">Exact proposal</Badge>
          <span className="font-mono text-[8px] text-muted-foreground">{shortReference(review.projection_id)}</span>
        </div>
        <DialogTitle className="text-2xl tracking-tight">Review the exact plan ACE prepared</DialogTitle>
        <DialogDescription className="text-sm leading-relaxed">Every item below came back from the installed planner and exact Pack. This review grants no authority and performs no work.</DialogDescription>
      </DialogHeader>

      <div className="mt-5 flex items-start gap-3 rounded-lg border border-border bg-muted/20 p-4">
        <Eye className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div>
          <div className="text-xs font-semibold">Prepared for review—not connected or activated</div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">No source has been connected, no concept has been written, no watch is running, and no Brief has been generated.</p>
        </div>
      </div>

      <section className="mt-6">
        <ReviewHeading eyebrow="Evidence" title="Exact sources" count={review.sources.length} />
        <ol className="mt-3 border-y border-border" aria-label="Exact source bindings">
          {review.sources.map((source) => (
            <li key={source.selection.selection_id} className="grid gap-4 border-t border-border py-4 first:border-t-0 md:grid-cols-[minmax(0,1fr)_13rem]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2"><div className="text-sm font-semibold">{source.label}</div><Badge variant="secondary" className="rounded-sm font-mono text-[8px]">{source.evidence_role.replace(/_/g, ' ')}</Badge></div>
                <div className="mt-2 break-all text-[11px] text-foreground/80">{source.source_uri}</div>
              </div>
              <dl className="grid gap-1.5 border-t border-border pt-3 font-mono text-[8px] text-muted-foreground md:border-l md:border-t-0 md:pl-4 md:pt-0">
                <div><dt className="inline text-foreground/65">Entity</dt><dd className="inline"> · {source.entity_type_id} · {shortReference(source.entity_ref)}</dd></div>
                <div><dt className="inline text-foreground/65">Selection</dt><dd className="inline"> · {shortReference(source.selection.selection_id)}</dd></div>
                <div><dt className="inline text-foreground/65">Observed</dt><dd className="inline"> · {source.observed_at}</dd></div>
              </dl>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-6 border-t pt-6">
        <ReviewHeading eyebrow="Orientation" title="Concepts and watches" count={review.concepts.length + review.watches.length} />
        <div className="mt-3 grid border-y border-border md:grid-cols-2">
          <section className="py-4 md:pr-5">
            <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Concepts · {review.concepts.length}</div>
            <div className="mt-3 border-t border-border">
              {review.concepts.map((concept) => <div key={`${concept.entity_type_id}:${concept.entity_ref}`} className="border-b border-border py-3"><div className="text-xs font-semibold">{concept.display_name}</div><div className="mt-1 font-mono text-[8px] text-muted-foreground">{concept.entity_type_id} · {shortReference(concept.entity_ref)}</div></div>)}
              {review.concepts.length === 0 && <p className="text-xs text-muted-foreground">The exact proposal returned no starting entity references.</p>}
            </div>
          </section>
          <section className="border-t border-border py-4 md:border-l md:border-t-0 md:pl-5">
            <div className="flex items-center justify-between gap-3"><div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Watches · {review.watches.length}</div><Badge variant="outline" className="rounded-sm font-mono text-[8px]">{review.cadence_label}</Badge></div>
            <div className="mt-3 border-t border-border">
              {review.watches.map((watch) => <div key={watch.detector_id} className="border-b border-border py-3"><div className="flex items-center gap-2 text-xs font-semibold"><Radar className="size-3 text-muted-foreground" aria-hidden="true" />{watch.detector_id}</div><div className="mt-2 text-[11px] leading-relaxed text-foreground/85">{watch.change_rule}</div><div className="mt-2 font-mono text-[8px] text-muted-foreground">{watch.entity_type_id}.{watch.attribute_id} · {watch.detector_family.replace(/_/g, ' ')}</div></div>)}
              {review.watches.length === 0 && <div className="border-b border-warning/35 bg-warning/[0.04] py-3 text-xs leading-relaxed text-muted-foreground"><span className="font-medium text-foreground">No exact starting watch was returned.</span> There is no detector rule to activate.</div>}
            </div>
            <p className="mt-3 text-[10px] leading-relaxed text-muted-foreground">{review.cadence_description}</p>
          </section>
        </div>
      </section>

      <section className="mt-6 border-t pt-6">
        <ReviewHeading eyebrow="Proposed effects" title="What would happen next" count={review.effects.length} />
        <ol className="mt-3 border-y border-border" aria-label="Reviewable proposed effects">
          {review.effects.map((effect, index) => <ReviewEffectRow key={effect.effect} effect={effect} index={index} />)}
        </ol>
      </section>
      <SystemProjectionReview projection={projection} error={projectionError} />
    </>
  )
}

function supportLabel(value: IntelligenceProjectionSupport): string {
  return value === 'unsupported' ? 'Not supported' : value
}

function SystemProjectionReview({
  projection,
  error,
}: {
  readonly projection: IntelligenceSystemProjection | null
  readonly error: string | null
}) {
  if (projection === null) {
    return (
      <section className="mt-6 border-t border-warning/35 pt-6" aria-label="Canonical system projection unavailable">
        <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-warning">Canonical projection unavailable</div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          {error ?? 'ACE returned exact plan review material, but no canonical blueprint, coverage, readiness, or Domain Health projection.'}
        </p>
      </section>
    )
  }

  return (
    <section className="mt-8 border-t border-border pt-7" aria-labelledby="canonical-system-projection">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Canonical system projection</div>
          <h3 id="canonical-system-projection" className="mt-1 text-lg font-semibold tracking-tight">Blueprint, bindings, coverage, and readiness</h3>
        </div>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px]">
          {projection.mode === 'live' ? 'Live · point-in-time read' : 'Proposal · no authority'}
        </Badge>
      </div>

      {projection.gaps.length > 0 && (
        <section className="mt-5 rounded-lg border border-border bg-muted/20 p-4" aria-label="Exact projection gaps">
          <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
            {projection.gaps.length} exact gap{projection.gaps.length === 1 ? '' : 's'}
          </div>
          <ul className="mt-2 space-y-1.5">
            {projection.gaps.map((gap) => (
              <li key={gap} className="text-[10px] leading-4 text-muted-foreground">{gap}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-5">
        <ReviewHeading eyebrow="Blueprint" title="What ACE proposes to maintain" count={projection.blueprint.elements.length} />
        <ol className="mt-3 border-y border-border" aria-label="Canonical blueprint elements">
          {projection.blueprint.elements.map((element) => (
            <li key={element.element_ref} className="grid gap-3 border-t border-border py-4 first:border-t-0 md:grid-cols-[7rem_minmax(0,1fr)_9rem]">
              <Badge variant="outline" className="h-fit w-fit rounded-sm font-mono text-[8px] uppercase">{element.kind}</Badge>
              <div><div className="text-xs font-semibold">{element.label}</div><p className="mt-1 text-[10px] leading-4 text-muted-foreground">{element.rationale}</p></div>
              <div className="font-mono text-[8px] text-muted-foreground">Confidence · {supportLabel(element.confidence.support)}</div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-6 border-t border-border pt-6">
        <ReviewHeading eyebrow="Exact bindings" title="Permission and readiness stay separate" count={projection.source_bindings.length} />
        <ol className="mt-3 border-y border-border" aria-label="Canonical source binding readiness">
          {projection.source_bindings.map((binding) => (
            <li key={binding.binding_id} className="grid gap-3 border-t border-border py-4 first:border-t-0 md:grid-cols-[minmax(0,1fr)_9rem_9rem]">
              <div><div className="text-xs font-semibold">{binding.label}</div><div className="mt-1 break-all font-mono text-[8px] text-muted-foreground">{binding.source_uri}</div></div>
              <div><div className="font-mono text-[7px] uppercase text-muted-foreground">Permission</div><div className="mt-1 text-[10px]">{binding.permission_state.replace(/_/g, ' ')}</div></div>
              <div><div className="font-mono text-[7px] uppercase text-muted-foreground">Readiness</div><div className="mt-1 text-[10px]">{binding.readiness_state.replace(/_/g, ' ')}</div></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-6 border-t border-border pt-6">
        <ReviewHeading eyebrow="Coverage" title="Predicted and observed remain distinct" count={projection.coverage.length} />
        <ol className="mt-3 border-y border-border" aria-label="Predicted and observed coverage">
          {projection.coverage.map((coverage) => (
            <li key={`${coverage.dimension}:${coverage.target_ref}`} className="grid gap-3 border-t border-border py-4 first:border-t-0 md:grid-cols-[minmax(0,1fr)_9rem_9rem]">
              <div><div className="text-xs font-semibold">{coverage.target_label}</div><div className="mt-1 font-mono text-[8px] uppercase text-muted-foreground">{coverage.dimension}</div></div>
              <div><div className="font-mono text-[7px] uppercase text-muted-foreground">Predicted</div><div className="mt-1 text-[10px]">{supportLabel(coverage.predicted.support)}</div></div>
              <div><div className="font-mono text-[7px] uppercase text-muted-foreground">Observed</div><div className="mt-1 text-[10px]">{supportLabel(coverage.observed.support)}</div></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-6 grid gap-6 border-t border-border pt-6 lg:grid-cols-2">
        <div>
          <ReviewHeading eyebrow="Initialization" title="Durable semantic stages" count={projection.initialization.length} />
          <ol className="mt-3 border-y border-border" aria-label="Canonical initialization stages">
            {projection.initialization.map((stage) => <li key={stage.stage} className="grid grid-cols-[2rem_minmax(0,1fr)_6rem] gap-2 border-t border-border py-3 first:border-t-0"><span className="font-mono text-[8px] text-muted-foreground">{String(stage.sequence).padStart(2, '0')}</span><div><div className="text-[10px] font-medium">{stage.stage.replace(/_/g, ' ')}</div><p className="mt-1 text-[9px] leading-4 text-muted-foreground">{stage.detail}</p></div><div className="text-right font-mono text-[8px] uppercase text-muted-foreground">{stage.state.replace(/_/g, ' ')}</div></li>)}
          </ol>
        </div>
        <div>
          <ReviewHeading eyebrow="Domain Health" title="Truthful ceiling at proposal time" count={projection.domain_health.length} />
          <dl className="mt-3 border-y border-border">
            {projection.domain_health.map((health) => <div key={health.dimension} className="grid grid-cols-[minmax(0,1fr)_7rem] gap-3 border-t border-border py-3 first:border-t-0"><dt className="text-[10px] capitalize">{health.dimension.replace(/_/g, ' ')}</dt><dd className="text-right font-mono text-[8px] uppercase text-muted-foreground">{supportLabel(health.value.support)}</dd>{health.value.reason !== null && <dd className="col-span-2 text-[9px] leading-4 text-muted-foreground">{health.value.reason}</dd>}</div>)}
          </dl>
        </div>
      </section>
    </section>
  )
}

function ReviewHeading({ eyebrow, title, count }: { readonly eyebrow: string; readonly title: string; readonly count: number }) {
  return <div className="flex items-end justify-between gap-3"><div><div className="font-mono text-[8px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{eyebrow}</div><h3 className="mt-1 text-base font-semibold tracking-tight">{title}</h3></div><Badge variant="outline" className="rounded-sm font-mono text-[8px]">{count} exact</Badge></div>
}

function ReviewEffectRow({ effect, index }: { readonly effect: IntelligenceBuildPlanReviewEffect; readonly index: number }) {
  return (
    <li className="grid gap-4 border-t border-border py-5 first:border-t-0 md:grid-cols-[2rem_minmax(0,1fr)_13rem]">
      <span className="font-mono text-[9px] text-foreground/65">{String(index + 1).padStart(2, '0')}</span>
      <div className="min-w-0">
        <div className="text-xs font-semibold">{effect.label}</div>
        <div className="mt-1 font-mono text-[8px] text-muted-foreground">{effect.effect}</div>
        <p className="mt-3 text-sm leading-5 text-foreground/90">{effect.what}</p>
        <div className="mt-3 border-l-2 border-foreground/30 pl-3">
          <div className="font-mono text-[7px] uppercase tracking-[0.12em] text-muted-foreground">Rationale</div>
          <p className="mt-1 text-[10px] leading-4 text-muted-foreground">{effect.why}</p>
        </div>
      </div>
      <dl className="border-t border-border pt-3 md:border-l md:border-t-0 md:pl-4 md:pt-0">
        <div><dt className="font-mono text-[7px] uppercase tracking-[0.12em] text-muted-foreground">Method</dt><dd className="mt-1 text-[10px] leading-4 text-foreground/80">{effect.how}</dd></div>
        <div className="mt-3"><dt className="font-mono text-[7px] uppercase tracking-[0.12em] text-muted-foreground">Timing</dt><dd className="mt-1 text-[10px] leading-4 text-foreground/80">{effect.when}</dd></div>
        {effect.unknowns.length > 0 && <div className="mt-3 border-t border-warning/30 pt-3"><dt className="font-mono text-[7px] uppercase tracking-[0.12em] text-warning">Unknowns</dt><dd className="mt-1 text-[9px] leading-4 text-muted-foreground">{effect.unknowns.join(' ')}</dd></div>}
      </dl>
    </li>
  )
}

function PlanLedger({ rows }: { readonly rows: readonly { readonly label: string; readonly value: string | number; readonly detail: string }[] }) {
  return (
    <dl className="mt-6 border-y border-border">
      {rows.map((row) => (
        <div key={row.label} className="grid gap-2 border-t border-border py-4 first:border-t-0 sm:grid-cols-[7rem_11rem_minmax(0,1fr)] sm:gap-4">
          <dt className="font-mono text-[8px] uppercase tracking-[0.15em] text-muted-foreground">{row.label}</dt>
          <dd className="text-sm font-semibold">{row.value}</dd>
          <dd className="text-xs leading-relaxed text-muted-foreground">{row.detail}</dd>
        </div>
      ))}
    </dl>
  )
}

function BuildStep({ label, result, state }: BuildLane) {
  const Icon = state === 'complete' ? Check : state === 'blocked' ? TriangleAlert : state === 'preview' ? FlaskConical : state === 'unsupported' ? LockKeyhole : CircleDot
  const stateLabel = state === 'complete' ? 'Recorded' : state === 'blocked' ? 'Needs attention' : state === 'active' ? 'Current revision' : state === 'waiting' ? 'Waiting' : state === 'preview' ? 'Preview' : state === 'unsupported' ? 'Not reported' : 'Proposed'
  return (
    <div role="listitem" className={`flex items-center gap-3 rounded-lg border p-4 ${state === 'active' ? 'border-foreground/20 bg-muted/20' : state === 'blocked' ? 'border-warning/45 bg-warning/5' : state === 'preview' ? 'border-border bg-muted/20' : 'bg-card'}`}>
      <div className={`flex size-7 items-center justify-center rounded-full ${state === 'blocked' ? 'bg-warning/15 text-warning' : state === 'complete' ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground'}`}>
        <Icon className="size-3.5" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1"><div className="text-sm font-medium">{label}</div><div className="mt-0.5 text-xs text-muted-foreground">{result}</div></div>
      <Badge variant="secondary" className="rounded-sm font-mono text-[9px]">{stateLabel}</Badge>
    </div>
  )
}
