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
  Scale,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from 'lucide-react'

import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/design/shadcn/ui/dialog'
import { Textarea } from '@/design/shadcn/ui/textarea'
import {
  createIntelligenceBuildPlanPrepareInput,
  IntelligenceBuildApiError,
  type IntelligenceBuildPlan,
  type IntelligenceBuildPlanPrepareInput,
  type IntelligenceBuildPlanReviewEffect,
} from '@/api/intelligenceBuildsApi'
import type {
  IntelligenceBuilderSession,
  IntelligenceBuilderStage,
  IntelligenceOnboardingOutcome,
  IntelligenceOnboardingProfile,
  IntelligenceOnboardingSourceGroup,
} from './onboardingModel'
import { isCustomPreviewProfile } from './onboardingModel'

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

type BuildState = 'complete' | 'active' | 'blocked' | 'waiting' | 'proposed' | 'preview'

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
  return <Icon className="size-4" />
}

function SourceIcon({ group }: { readonly group: IntelligenceOnboardingSourceGroup }) {
  const Icon = SOURCE_ICONS[group.evidence_role] ?? FileCheck2
  return <Icon className="size-4" />
}

function laneState(rank: number, activeAt: number, completeAt: number): BuildState {
  if (rank >= completeAt) return 'complete'
  if (rank >= activeAt) return 'active'
  return 'waiting'
}

function blockedLane(stage: IntelligenceBuilderStage | null): number {
  const rank = stage === null ? 0 : STAGE_RANK[stage]
  if (rank <= 1) return 0
  if (rank <= 3) return 1
  if (rank <= 5) return 2
  return 3
}

function buildLanes(session: IntelligenceBuilderSession | null, watchCount: number | 'Custom'): readonly BuildLane[] {
  if (session === null) {
    return [
      { label: 'Connect and validate evidence', result: 'Source plan proposed for review', state: 'proposed' },
      { label: 'Map entities and concepts', result: 'Concept model will follow admitted evidence', state: 'proposed' },
      { label: 'Configure governed watches', result: `${watchCount} starting areas proposed`, state: 'proposed' },
      { label: 'Assemble the first cited Brief', result: 'Begins only after the governed inputs are ready', state: 'proposed' },
    ]
  }

  const effectiveStage = session.stage === 'blocked' || session.stage === 'retrying'
    ? session.resume_stage ?? 'goal_selected'
    : session.stage
  const rank = STAGE_RANK[effectiveStage]
  const evidenceState = laneState(rank, 1, 2)
  const conceptState = laneState(rank, 3, 4)
  const watchState = laneState(rank, 5, 6)
  const briefingState = laneState(rank, 6, 7)
  const lanes: BuildLane[] = [
    { label: 'Connect and validate evidence', result: evidenceState === 'complete' ? 'Approved evidence connected' : 'Connection Agent is validating permitted sources', state: evidenceState },
    { label: 'Map entities and concepts', result: conceptState === 'complete' ? 'Entities and concepts mapped' : 'Ontology Agent is grounding the concept map', state: conceptState },
    { label: 'Configure governed watches', result: watchState === 'complete' ? 'Watch plan approved' : `Intelligence Agent is evaluating ${watchCount} starting areas`, state: watchState },
    { label: 'Assemble the first cited Brief', result: briefingState === 'complete' ? 'First cited Brief ready' : 'Briefing Agent is preserving claims and citations', state: briefingState },
  ]

  if (session.stage === 'blocked') {
    const lane = blockedLane(session.resume_stage)
    lanes[lane] = {
      ...lanes[lane],
      result: session.safe_diagnostic ?? `ACE stopped safely: ${session.block_reason ?? 'review required'}.`,
      state: 'blocked',
    }
  } else if (session.stage === 'retrying') {
    const lane = blockedLane(session.resume_stage)
    lanes[lane] = { ...lanes[lane], result: 'ACE is retrying the governed step.', state: 'active' }
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

export function OnboardingPreview({
  open,
  onOpenChange,
  profiles,
  session,
  onPrepareBuild,
  onOpenBrief,
}: {
  readonly open: boolean
  readonly onOpenChange: (open: boolean) => void
  readonly profiles: readonly IntelligenceOnboardingProfile[]
  readonly session: IntelligenceBuilderSession | null
  readonly onPrepareBuild: (request: IntelligenceBuildPlanPrepareInput) => Promise<IntelligenceBuildPlan>
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
  const outcome = useMemo(() => profile.outcomes.find((item) => item.outcome_id === outcomeId) ?? profile.outcomes[0], [outcomeId, profile.outcomes])
  const selectedSourceGroups = useMemo(
    () => profile.source_groups.filter((group) => sourceGroupIds.includes(group.source_group_id)),
    [profile.source_groups, sourceGroupIds],
  )
  const proposedSourceCount = selectedSourceGroups.reduce((total, group) => total + group.source_ids.length, 0)
  const customPreview = isCustomPreviewProfile(profile)
  const activeSession = profile.profile_id === profiles[0]?.profile_id ? session : null
  const firstBriefReady = activeSession !== null && STAGE_RANK[activeSession.stage] >= STAGE_RANK.first_briefing_ready
  const lanes = customPreview
    ? customPreviewLanes(outcome.recommended_topic_labels.length || 'Custom')
    : buildLanes(activeSession, outcome.recommended_topic_labels.length || 'Custom')
  const evidenceRequired = profile.source_groups.length > 0
  const canContinue = step === 1
    ? subject.trim().length >= 8
    : step !== 2 || !evidenceRequired || selectedSourceGroups.length > 0
  const stepLabels = customPreview ? CUSTOM_PREVIEW_STEP_LABELS : STEP_LABELS

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
    setPlanError(null)
  }, [profile])

  function invalidatePreparedPlan() {
    setPreparedInput(null)
    setPreparedPlan(null)
    setPlanError(null)
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
      setStep(3)
    } catch (reason: unknown) {
      setPlanError(planErrorState(reason))
    } finally {
      setPlanPending(false)
    }
  }

  function finish() {
    close(false)
    if (firstBriefReady) onOpenBrief()
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="atrium-command-center dark max-h-[calc(100svh-2rem)] overflow-y-auto rounded-lg border-border bg-popover p-0 sm:max-w-4xl">
        <div className="border-b px-6 py-4 sm:px-8">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 font-mono text-[9px] font-semibold uppercase tracking-[0.17em] text-muted-foreground">
              <Sparkles className="size-3.5" /> Build your intelligence
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
                      : `Live · step ${activeSession.sequence}`}
            </Badge>
          </div>
          <div className="mt-3 grid grid-cols-5 gap-1.5" aria-label={`Step ${step + 1} of 5: ${stepLabels[step]}`}>
            {stepLabels.map((label, index) => (
              <div key={label} className="min-w-0">
                <div className={`h-1 rounded-full ${index <= step ? 'bg-foreground/75' : 'bg-border'}`} />
                <div className={`mt-1.5 hidden truncate font-mono text-[8px] uppercase tracking-[0.12em] sm:block ${index === step ? 'text-foreground' : 'text-muted-foreground'}`}>{label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="px-6 py-7 sm:px-8">
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
                        className={`h-auto min-h-44 w-full flex-col items-start justify-start whitespace-normal rounded-lg border p-5 text-left ${selected ? 'border-foreground/30 bg-foreground/[0.045] ring-1 ring-foreground/10' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}
                      >
                        <div className="flex w-full items-start justify-between gap-3">
                          <div className={`flex size-9 items-center justify-center rounded-md border ${selected ? 'border-foreground/25 bg-foreground/[0.06] text-foreground' : 'bg-muted text-muted-foreground'}`}>
                            {item.profile_id.includes('custom') ? <Compass className="size-4" /> : <Sparkles className="size-4" />}
                          </div>
                          <div className="flex items-center gap-1.5">
                            {isCustomPreviewProfile(item) && <Badge variant="outline" className="rounded-sm border-[var(--ace-purple-500)]/40 bg-[var(--ace-purple-500)]/10 font-mono text-[8px] text-[var(--ace-purple-300)]">Preview</Badge>}
                            {selected && <Badge variant="outline" className="rounded-sm border-foreground/20 font-mono text-[8px] text-foreground/75">Selected</Badge>}
                          </div>
                        </div>
                        <div className="mt-5 text-base font-semibold">{item.domain_label}</div>
                        <div className="mt-1 text-xs font-medium text-foreground/85">{item.topic_label}</div>
                        <p className="mt-3 text-[11px] font-normal leading-relaxed text-muted-foreground">{item.description}</p>
                      </Button>
                    )
                  })}
              </div>
              <div className={`mt-4 flex items-start gap-3 rounded-lg border p-4 ${customPreview ? 'border-[var(--ace-purple-500)]/35 bg-[var(--ace-purple-500)]/8' : 'border-evidence/20 bg-evidence/[0.05]'}`}>
                {customPreview
                  ? <FlaskConical className="mt-0.5 size-4 shrink-0 text-[var(--ace-purple-300)]" />
                  : <BookOpenCheck className="mt-0.5 size-4 shrink-0 text-evidence" />}
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
                <DialogTitle className="text-2xl tracking-tight">What do you need to stay ahead of?</DialogTitle>
                <DialogDescription className="text-sm leading-relaxed">
                  Describe the subject or decision in plain language. ACE will specialize {profile.domain_label} around your job.
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
                    <Button key={item.outcome_id} type="button" variant="ghost" onClick={() => {
                      invalidatePreparedPlan()
                      setOutcomeId(item.outcome_id)
                    }} className={`h-auto w-full justify-start gap-4 whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-foreground/30 bg-foreground/[0.045]' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}>
                      <div className={`flex size-9 shrink-0 items-center justify-center rounded-md border ${selected ? 'border-foreground/25 bg-foreground/[0.06] text-foreground' : 'bg-muted text-muted-foreground'}`}><OutcomeIcon outcome={item} /></div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 text-sm font-semibold">{item.label}{selected && <Check className="size-3.5 text-foreground/70" />}</div>
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
                    return <Button key={cadence.cadence_id} type="button" variant="ghost" onClick={() => {
                      invalidatePreparedPlan()
                      setCadenceId(cadence.cadence_id)
                    }} className={`h-auto w-full flex-col items-start whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-foreground/30 bg-foreground/[0.045]' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}><div className="flex items-center gap-2 text-sm font-semibold"><CircleDot className={`size-3.5 ${selected ? 'text-foreground/70' : 'text-muted-foreground'}`} />{cadence.label}</div><p className="mt-1 pl-5 text-xs font-normal text-muted-foreground">{cadence.description}</p></Button>
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
                          className={`h-auto min-h-40 w-full flex-col items-stretch justify-start whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-evidence/35 bg-evidence/[0.055]' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}
                        >
                          <div className="flex items-start gap-3">
                            <div className={`flex size-9 shrink-0 items-center justify-center rounded-md border ${selected ? 'border-evidence/30 bg-evidence/[0.08] text-evidence' : 'bg-muted text-muted-foreground'}`}><SourceIcon group={group} /></div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 text-sm font-semibold">{group.label}{selected && <Check className="size-3.5 text-evidence" />}</div>
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
                    <PlugZap className="size-3.5 text-evidence" /> {selectedSourceGroups.length} groups · {proposedSourceCount} sources proposed
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
                <div className="mt-6 grid gap-3 sm:grid-cols-2">
                  <PlanCard label="Evidence" value="Recommended public mix" detail="Primary records, first-party claims, independent measurement, operational telemetry, and leading indicators." />
                  <PlanCard label="Concept map" value={`${outcome.recommended_topic_labels.length || 'Custom'} starting concepts`} detail={outcome.recommended_topic_labels.length > 0 ? outcome.recommended_topic_labels.join(' · ') : 'Entities, aliases, attributes, relationships, claims, events, and outcomes.'} />
                  <PlanCard label="Watches" value={`${outcome.recommended_topic_labels.length || 'Custom'} starting areas`} detail="Material changes, contradictions, catalysts, and weak signals—scoped to your selected job." />
                  <PlanCard label="Briefing" value="Preview only" detail={`Cadence captured: ${profile.cadences.find((item) => item.cadence_id === cadenceId)?.label ?? 'Selected cadence'}. v1 does not activate this Custom plan or run a first-Brief executor.`} />
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
                  <div className="flex items-start gap-3 rounded-lg border border-brand/25 bg-brand/5 p-4"><Scale className="mt-0.5 size-4 shrink-0 text-brand" /><p className="text-xs leading-relaxed text-muted-foreground"><span className="font-medium text-foreground">Nothing is connected or activated silently.</span> This Custom preview is a local draft and makes no server request.</p></div>
                  <div className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3">
                    <FlaskConical className="size-4 text-[var(--ace-purple-300)]" />
                    <div><div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">Preview boundary</div><div className="mt-0.5 text-xs font-medium">Draft proposal only</div></div>
                  </div>
                </div>
              </>
            ) : preparedPlan?.review_projection !== null && preparedPlan?.review_projection !== undefined ? (
              <ExactPlanReview plan={preparedPlan} />
            ) : null
          )}

          {step === 4 && (
            <>
              <DialogHeader className="max-w-2xl">
                <DialogTitle className="text-2xl tracking-tight">{customPreview ? 'Your Custom proposal is ready' : firstBriefReady ? 'Your first picture is ready' : activeSession?.stage === 'blocked' ? 'ACE needs your attention' : activeSession === null ? 'Your governed plan is ready' : 'Your first picture is assembling'}</DialogTitle>
                <DialogDescription>
                  {customPreview
                    ? 'This is a draft model for review. ACE has not connected sources, activated watches, or run a first-Brief executor.'
                    : activeSession === null
                    ? 'Review the plan before ACE connects sources or starts watching.'
                    : firstBriefReady
                      ? 'ACE built this picture from the sources and watch settings you approved.'
                      : activeSession.stage === 'blocked'
                        ? 'ACE paused safely before changing your intelligence picture.'
                        : 'ACE is assembling the picture from the sources and watch settings you approved.'}
                </DialogDescription>
              </DialogHeader>
              <div className="mt-7 space-y-2">
                {lanes.map((lane) => <BuildStep key={lane.label} {...lane} />)}
              </div>
              <div className="mt-5 rounded-lg border bg-card p-4 text-xs text-muted-foreground">
                {customPreview
                  ? 'Preview complete · No runtime execution performed'
                  : activeSession === null
                  ? 'Reviewing this plan changes nothing until you approve it.'
                  : firstBriefReady
                    ? 'First cited Brief ready · Setup saved'
                    : `Setup saved · Step ${activeSession.sequence}`}
              </div>
            </>
          )}
          {planError !== null && (
            <div role="alert" className="mt-5 flex items-start gap-3 rounded-lg border border-destructive/45 bg-destructive/5 p-4 text-xs text-destructive">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              <div>
                <div className="font-semibold">{planError.title}</div>
                <div className="mt-1 text-destructive/85">{planError.detail}</div>
                {planError.status > 0 && <div className="mt-2 font-mono text-[8px] uppercase tracking-[0.12em] text-destructive/70">Prepare response · {planError.status}</div>}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t px-6 py-4 sm:px-8">
          <Button type="button" variant="ghost" disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}><ArrowLeft className="size-4" /> Back</Button>
          {step < 4
            ? step === 3 && !customPreview && activeSession === null
              ? <div className="flex items-center gap-3"><span className="hidden max-w-52 text-right text-[10px] leading-relaxed text-muted-foreground sm:block">Owner approval and activation setup are not available yet.</span><Button type="button" disabled><LockKeyhole className="size-4" /> Activation unavailable</Button></div>
              : <Button type="button" disabled={!canContinue || planPending} onClick={() => {
                if (step === 2) void preparePlan()
                else if (step === 3) setStep(4)
                else setStep((value) => Math.min(3, value + 1))
              }}>{planPending ? <><LoaderCircle className="size-4 animate-spin" /> Preparing exact plan</> : <>{step === 0 ? customPreview ? 'Preview this intelligence' : 'Use this intelligence' : step === 1 ? 'Choose evidence' : step === 2 ? customPreview ? 'Review the plan' : preparedInput === null ? 'Prepare exact plan' : 'Retry exact plan' : customPreview ? 'View draft proposal' : 'View live build'} <ArrowRight className="size-4" /></>}</Button>
            : <Button type="button" onClick={finish}>{firstBriefReady ? profile.completion_label : 'Return to Atrium'} <ArrowRight className="size-4" /></Button>}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function shortReference(value: string): string {
  return value.length <= 34 ? value : `${value.slice(0, 18)}…${value.slice(-10)}`
}

function ExactPlanReview({ plan }: { readonly plan: IntelligenceBuildPlan }) {
  const review = plan.review_projection
  if (review === null) return null
  return (
    <>
      <DialogHeader className="max-w-3xl">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="rounded-sm border-brand/35 bg-brand/8 font-mono text-[8px] uppercase tracking-[0.12em] text-brand">Exact proposal</Badge>
          <span className="font-mono text-[8px] text-muted-foreground">{shortReference(review.projection_id)}</span>
        </div>
        <DialogTitle className="text-2xl tracking-tight">Review the exact plan ACE prepared</DialogTitle>
        <DialogDescription className="text-sm leading-relaxed">Every item below came back from the installed planner and exact Pack. This review grants no authority and performs no work.</DialogDescription>
      </DialogHeader>

      <div className="mt-5 flex items-start gap-3 rounded-lg border border-brand/30 bg-brand/7 p-4">
        <Eye className="mt-0.5 size-4 shrink-0 text-brand" />
        <div>
          <div className="text-xs font-semibold">Prepared for review—not connected or activated</div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">No source has been connected, no concept has been written, no watch is running, and no Brief has been generated.</p>
        </div>
      </div>

      <section className="mt-6">
        <ReviewHeading eyebrow="Evidence" title="Exact sources" count={review.sources.length} />
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {review.sources.map((source) => (
            <div key={source.selection.selection_id} className="rounded-lg border bg-card p-4">
              <div className="flex items-start justify-between gap-3"><div className="text-sm font-semibold">{source.label}</div><Badge variant="secondary" className="rounded-sm font-mono text-[8px]">{source.evidence_role.replace(/_/g, ' ')}</Badge></div>
              <div className="mt-2 break-all text-[11px] text-foreground/80">{source.source_uri}</div>
              <div className="mt-3 grid gap-1.5 border-t pt-3 font-mono text-[8px] text-muted-foreground">
                <div><span className="text-foreground/65">Entity</span> · {source.entity_type_id} · {shortReference(source.entity_ref)}</div>
                <div><span className="text-foreground/65">Selection</span> · {shortReference(source.selection.selection_id)}</div>
                <div><span className="text-foreground/65">Observed</span> · {source.observed_at}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-6 border-t pt-6">
        <ReviewHeading eyebrow="Orientation" title="Concepts and watches" count={review.concepts.length + review.watches.length} />
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border bg-card p-4">
            <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Concepts · {review.concepts.length}</div>
            <div className="mt-3 space-y-2">
              {review.concepts.map((concept) => <div key={`${concept.entity_type_id}:${concept.entity_ref}`} className="rounded-md border bg-background/55 p-3"><div className="text-xs font-semibold">{concept.display_name}</div><div className="mt-1 font-mono text-[8px] text-muted-foreground">{concept.entity_type_id} · {shortReference(concept.entity_ref)}</div></div>)}
              {review.concepts.length === 0 && <p className="text-xs text-muted-foreground">The exact proposal returned no starting entity references.</p>}
            </div>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between gap-3"><div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Watches · {review.watches.length}</div><Badge variant="outline" className="rounded-sm font-mono text-[8px]">{review.cadence_label}</Badge></div>
            <div className="mt-3 space-y-2">
              {review.watches.map((watch) => <div key={watch.detector_id} className="rounded-md border bg-background/55 p-3"><div className="flex items-center gap-2 text-xs font-semibold"><Radar className="size-3 text-live" />{watch.detector_id}</div><div className="mt-2 text-[11px] leading-relaxed text-foreground/85">{watch.change_rule}</div><div className="mt-2 font-mono text-[8px] text-muted-foreground">{watch.entity_type_id}.{watch.attribute_id} · {watch.detector_family.replace(/_/g, ' ')}</div></div>)}
              {review.watches.length === 0 && <div className="rounded-md border border-warning/35 bg-warning/5 p-3 text-xs leading-relaxed text-muted-foreground"><span className="font-medium text-foreground">No exact starting watch was returned.</span> There is no detector rule to activate.</div>}
            </div>
            <p className="mt-3 text-[10px] leading-relaxed text-muted-foreground">{review.cadence_description}</p>
          </div>
        </div>
      </section>

      <section className="mt-6 border-t pt-6">
        <ReviewHeading eyebrow="Proposed effects" title="What would happen next" count={review.effects.length} />
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {review.effects.map((effect, index) => <ReviewEffectCard key={effect.effect} effect={effect} index={index} />)}
        </div>
      </section>
    </>
  )
}

function ReviewHeading({ eyebrow, title, count }: { readonly eyebrow: string; readonly title: string; readonly count: number }) {
  const tone = eyebrow === 'Evidence' ? 'text-evidence' : eyebrow === 'Orientation' ? 'text-live' : 'text-brand'
  return <div className="flex items-end justify-between gap-3"><div><div className={`font-mono text-[8px] font-semibold uppercase tracking-[0.16em] ${tone}`}>{eyebrow}</div><h3 className="mt-1 text-base font-semibold tracking-tight">{title}</h3></div><Badge variant="outline" className="rounded-sm font-mono text-[8px]">{count} exact</Badge></div>
}

function ReviewEffectCard({ effect, index }: { readonly effect: IntelligenceBuildPlanReviewEffect; readonly index: number }) {
  const rows = [
    ['What', effect.what],
    ['Why', effect.why],
    ['How', effect.how],
    ['When', effect.when],
    ['Unknowns', effect.unknowns.join(' ')],
  ] as const
  return <Card className="overflow-hidden"><CardContent className="p-0"><div className="flex items-center gap-3 border-b bg-muted/25 px-4 py-3"><span className="font-mono text-[9px] text-foreground/55">0{index + 1}</span><div><div className="text-xs font-semibold">{effect.label}</div><div className="mt-0.5 font-mono text-[8px] text-muted-foreground">{effect.effect}</div></div></div><dl>{rows.map(([label, value]) => <div key={label} className="grid grid-cols-[4.5rem_1fr] gap-3 border-b px-4 py-2.5 last:border-b-0"><dt className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">{label}</dt><dd className="text-[11px] leading-relaxed text-foreground/85">{value}</dd></div>)}</dl></CardContent></Card>
}

function PlanCard({ label, value, detail }: { readonly label: string; readonly value: string | number; readonly detail: string }) {
  return <Card><CardContent className="p-5"><div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">{label}</div><div className="mt-2 text-sm font-semibold">{value}</div><p className="mt-2 text-xs leading-relaxed text-muted-foreground">{detail}</p></CardContent></Card>
}

function BuildStep({ label, result, state }: BuildLane) {
  const Icon = state === 'complete' ? Check : state === 'blocked' ? TriangleAlert : state === 'active' ? LoaderCircle : state === 'preview' ? FlaskConical : CircleDot
  const stateLabel = state === 'complete' ? 'Complete' : state === 'blocked' ? 'Needs attention' : state === 'active' ? 'Working' : state === 'waiting' ? 'Waiting' : state === 'preview' ? 'Preview' : 'Proposed'
  return (
    <div className={`flex items-center gap-3 rounded-lg border p-4 ${state === 'active' ? 'border-live/30 bg-live/[0.055]' : state === 'blocked' ? 'border-warning/45 bg-warning/5' : state === 'preview' ? 'border-[var(--ace-purple-500)]/35 bg-[var(--ace-purple-500)]/8' : 'bg-card'}`}>
      <div className={`flex size-7 items-center justify-center rounded-full ${state === 'blocked' ? 'bg-warning/15 text-warning' : state === 'complete' ? 'bg-success/12 text-success' : state === 'active' ? 'bg-live/10 text-live' : state === 'preview' ? 'bg-[var(--ace-purple-500)]/15 text-[var(--ace-purple-300)]' : 'bg-muted text-muted-foreground'}`}>
        <Icon className={`size-3.5 ${state === 'active' ? 'animate-spin' : ''}`} />
      </div>
      <div className="min-w-0 flex-1"><div className="text-sm font-medium">{label}</div><div className="mt-0.5 text-xs text-muted-foreground">{result}</div></div>
      <Badge variant="secondary" className="rounded-sm font-mono text-[9px]">{stateLabel}</Badge>
    </div>
  )
}
