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
import type { IntelligenceBuildStartInput } from '@/api/intelligenceBuildsApi'
import type {
  IntelligenceBuilderSession,
  IntelligenceBuilderStage,
  IntelligenceOnboardingOutcome,
  IntelligenceOnboardingProfile,
  IntelligenceOnboardingSourceGroup,
} from './onboardingModel'

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

const STEP_LABELS = ['Choose', 'Intent', 'Evidence', 'Review', 'Build'] as const

type BuildState = 'complete' | 'active' | 'blocked' | 'waiting' | 'proposed'

interface BuildLane {
  readonly label: string
  readonly result: string
  readonly state: BuildState
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

export function OnboardingPreview({
  open,
  onOpenChange,
  profiles,
  session,
  onStartBuild,
  onOpenBrief,
}: {
  readonly open: boolean
  readonly onOpenChange: (open: boolean) => void
  readonly profiles: readonly IntelligenceOnboardingProfile[]
  readonly session: IntelligenceBuilderSession | null
  readonly onStartBuild: (request: IntelligenceBuildStartInput) => Promise<void>
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
  const [buildPending, setBuildPending] = useState(false)
  const [buildError, setBuildError] = useState<string | null>(null)
  const outcome = useMemo(() => profile.outcomes.find((item) => item.outcome_id === outcomeId) ?? profile.outcomes[0], [outcomeId, profile.outcomes])
  const selectedSourceGroups = useMemo(
    () => profile.source_groups.filter((group) => sourceGroupIds.includes(group.source_group_id)),
    [profile.source_groups, sourceGroupIds],
  )
  const proposedSourceCount = selectedSourceGroups.reduce((total, group) => total + group.source_ids.length, 0)
  const activeSession = profile.profile_id === profiles[0]?.profile_id ? session : null
  const firstBriefReady = activeSession !== null && STAGE_RANK[activeSession.stage] >= STAGE_RANK.first_briefing_ready
  const lanes = buildLanes(activeSession, outcome.recommended_topic_labels.length || 'Custom')
  const evidenceRequired = profile.source_groups.length > 0
  const canContinue = step === 1
    ? subject.trim().length >= 8
    : step !== 2 || !evidenceRequired || selectedSourceGroups.length > 0

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
  }, [profile])

  function toggleSourceGroup(sourceGroupId: string) {
    setSourceGroupIds((current) => current.includes(sourceGroupId)
      ? current.filter((item) => item !== sourceGroupId)
      : [...current, sourceGroupId])
  }

  function close(next: boolean) {
    onOpenChange(next)
    if (!next) setStep(0)
    if (!next) setBuildError(null)
  }

  async function build() {
    setBuildPending(true)
    setBuildError(null)
    try {
      await onStartBuild({
        profile_id: profile.profile_id,
        subject: subject.trim(),
        outcome_id: outcome.outcome_id,
        source_group_ids: sourceGroupIds,
        cadence_id: cadenceId,
      })
      setStep(4)
    } catch (reason: unknown) {
      setBuildError(reason instanceof Error ? reason.message : 'ACE could not start this Intelligence build.')
    } finally {
      setBuildPending(false)
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
            <div className="flex items-center gap-2 font-mono text-[9px] font-semibold uppercase tracking-[0.17em] text-brand">
              <Sparkles className="size-3.5" /> Build your intelligence
            </div>
            <Badge variant="outline" className="mr-6 rounded-sm font-mono text-[9px]">
              {buildPending ? 'Building' : step < 4 ? 'Plan review' : activeSession === null ? 'Plan ready' : `Live · step ${activeSession.sequence}`}
            </Badge>
          </div>
          <div className="mt-3 grid grid-cols-5 gap-1.5" aria-label={`Step ${step + 1} of 5: ${STEP_LABELS[step]}`}>
            {STEP_LABELS.map((label, index) => (
              <div key={label} className="min-w-0">
                <div className={`h-1 rounded-full ${index <= step ? 'bg-brand' : 'bg-border'}`} />
                <div className={`mt-1.5 hidden truncate font-mono text-[8px] uppercase tracking-[0.12em] sm:block ${index === step ? 'text-brand' : 'text-muted-foreground'}`}>{label}</div>
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
                        className={`h-auto min-h-44 w-full flex-col items-start justify-start whitespace-normal rounded-lg border p-5 text-left ${selected ? 'border-brand/70 bg-brand/7 ring-1 ring-brand/20' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}
                      >
                        <div className="flex w-full items-start justify-between gap-3">
                          <div className={`flex size-9 items-center justify-center rounded-md border ${selected ? 'border-brand/40 bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'}`}>
                            {item.profile_id.includes('custom') ? <Compass className="size-4" /> : <Sparkles className="size-4" />}
                          </div>
                          {selected && <Badge variant="outline" className="rounded-sm border-brand/30 font-mono text-[8px] text-brand">Selected</Badge>}
                        </div>
                        <div className="mt-5 text-base font-semibold">{item.domain_label}</div>
                        <div className="mt-1 text-xs font-medium text-foreground/85">{item.topic_label}</div>
                        <p className="mt-3 text-[11px] font-normal leading-relaxed text-muted-foreground">{item.description}</p>
                      </Button>
                    )
                  })}
              </div>
              <div className="mt-4 flex items-start gap-3 rounded-lg border border-brand/20 bg-brand/5 p-4">
                <BookOpenCheck className="mt-0.5 size-4 shrink-0 text-brand" />
                <div>
                  <div className="text-xs font-medium text-foreground">{profile.display_name} is ready to specialize.</div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">Next, tell ACE what you need to understand or decide. Nothing connects or starts watching until you review the plan.</p>
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
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder="For example: Keep me ahead of meaningful AI capability, cost, policy, and adoption shifts."
                  className="min-h-24 rounded-lg border-border bg-card px-4 py-3 text-sm leading-relaxed"
                />
                {profile.starter_prompts.length > 1 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {profile.starter_prompts.slice(1).map((prompt) => (
                      <Button key={prompt} type="button" variant="outline" size="sm" className="h-auto whitespace-normal rounded-md py-1.5 text-left text-[10px] text-muted-foreground" onClick={() => setSubject(prompt)}>{prompt}</Button>
                    ))}
                  </div>
                )}
              </div>
              <div className="mt-6 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">{profile.prompt}</div>
              <div className="mt-6 grid gap-3 md:grid-cols-2">
                {profile.outcomes.map((item) => {
                  const selected = item.outcome_id === outcomeId
                  return (
                    <Button key={item.outcome_id} type="button" variant="ghost" onClick={() => setOutcomeId(item.outcome_id)} className={`h-auto w-full justify-start gap-4 whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-brand/70 bg-brand/7' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}>
                      <div className={`flex size-9 shrink-0 items-center justify-center rounded-md border ${selected ? 'border-brand/40 bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'}`}><OutcomeIcon outcome={item} /></div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 text-sm font-semibold">{item.label}{selected && <Check className="size-3.5 text-brand" />}</div>
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
                    return <Button key={cadence.cadence_id} type="button" variant="ghost" onClick={() => setCadenceId(cadence.cadence_id)} className={`h-auto w-full flex-col items-start whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-brand/70 bg-brand/7' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}><div className="flex items-center gap-2 text-sm font-semibold"><CircleDot className={`size-3.5 ${selected ? 'text-brand' : 'text-muted-foreground'}`} />{cadence.label}</div><p className="mt-1 pl-5 text-xs font-normal text-muted-foreground">{cadence.description}</p></Button>
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
                          className={`h-auto min-h-40 w-full flex-col items-stretch justify-start whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-brand/70 bg-brand/7' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}
                        >
                          <div className="flex items-start gap-3">
                            <div className={`flex size-9 shrink-0 items-center justify-center rounded-md border ${selected ? 'border-brand/40 bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'}`}><SourceIcon group={group} /></div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 text-sm font-semibold">{group.label}{selected && <Check className="size-3.5 text-brand" />}</div>
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
                    <PlugZap className="size-3.5 text-brand" /> {selectedSourceGroups.length} groups · {proposedSourceCount} sources proposed
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
            <>
              <DialogHeader className="max-w-2xl"><DialogTitle className="text-2xl tracking-tight">Review what ACE will build</DialogTitle><DialogDescription>Public evidence creates the first picture. Private sources remain optional and require explicit permission.</DialogDescription></DialogHeader>
              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                <PlanCard label="Evidence" value={profile.source_groups.length > 0 ? `${proposedSourceCount} proposed sources` : 'Recommended public mix'} detail={selectedSourceGroups.length > 0 ? selectedSourceGroups.map((group) => group.label).join(' · ') : 'Primary records, first-party claims, independent measurement, operational telemetry, and leading indicators.'} />
                <PlanCard label="Concept map" value={`${outcome.recommended_topic_labels.length || 'Custom'} starting concepts`} detail={outcome.recommended_topic_labels.length > 0 ? outcome.recommended_topic_labels.join(' · ') : 'Entities, aliases, attributes, relationships, claims, events, and outcomes.'} />
                <PlanCard label="Watches" value={`${outcome.recommended_topic_labels.length || 'Custom'} starting areas`} detail="Material changes, contradictions, catalysts, and weak signals—scoped to your selected job." />
                <PlanCard label="Briefing" value={profile.cadences.find((item) => item.cadence_id === cadenceId)?.label ?? 'Selected cadence'} detail={outcome.recommended_intelligence_labels.length > 0 ? outcome.recommended_intelligence_labels.join(' · ') : 'ACE will propose intelligence products from your custom questions.'} />
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
                <div className="flex items-start gap-3 rounded-lg border border-brand/25 bg-brand/5 p-4"><Scale className="mt-0.5 size-4 shrink-0 text-brand" /><p className="text-xs leading-relaxed text-muted-foreground"><span className="font-medium text-foreground">Nothing is connected or activated silently.</span> You will see every requested permission, every proposed source that remains unconnected, and every watch before it receives authority.</p></div>
                <div className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3"><BookOpenCheck className="size-4 text-brand" /><div><div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">First value</div><div className="mt-0.5 text-xs font-medium">One cited Brief</div></div></div>
              </div>
            </>
          )}

          {step === 4 && (
            <>
              <DialogHeader className="max-w-2xl">
                <DialogTitle className="text-2xl tracking-tight">{firstBriefReady ? 'Your first picture is ready' : activeSession?.stage === 'blocked' ? 'ACE needs your attention' : activeSession === null ? 'Your governed plan is ready' : 'Your first picture is assembling'}</DialogTitle>
                <DialogDescription>
                  {activeSession === null
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
                {activeSession === null
                  ? 'Reviewing this plan changes nothing until you approve it.'
                  : firstBriefReady
                    ? 'First cited Brief ready · Setup saved'
                    : `Setup saved · Step ${activeSession.sequence}`}
              </div>
            </>
          )}
          {buildError !== null && (
            <div role="alert" className="mt-5 flex items-start gap-3 rounded-lg border border-destructive/45 bg-destructive/5 p-4 text-xs text-destructive">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              <div><div className="font-semibold">ACE paused before changing your intelligence.</div><div className="mt-1 text-destructive/85">{buildError}</div></div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t px-6 py-4 sm:px-8">
          <Button type="button" variant="ghost" disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}><ArrowLeft className="size-4" /> Back</Button>
          {step < 4
            ? <Button type="button" disabled={!canContinue || buildPending} onClick={() => step === 3 ? void build() : setStep((value) => Math.min(3, value + 1))}>{buildPending ? <><LoaderCircle className="size-4 animate-spin" /> Building your first picture</> : <>{step === 0 ? 'Use this intelligence' : step === 1 ? 'Choose evidence' : step === 2 ? 'Review the plan' : 'Build my intelligence'} <ArrowRight className="size-4" /></>}</Button>
            : <Button type="button" onClick={finish}>{firstBriefReady ? profile.completion_label : 'Return to Atrium'} <ArrowRight className="size-4" /></Button>}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function PlanCard({ label, value, detail }: { readonly label: string; readonly value: string | number; readonly detail: string }) {
  return <Card><CardContent className="p-5"><div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">{label}</div><div className="mt-2 text-sm font-semibold">{value}</div><p className="mt-2 text-xs leading-relaxed text-muted-foreground">{detail}</p></CardContent></Card>
}

function BuildStep({ label, result, state }: BuildLane) {
  const Icon = state === 'complete' ? Check : state === 'blocked' ? TriangleAlert : state === 'active' ? LoaderCircle : CircleDot
  const stateLabel = state === 'complete' ? 'Complete' : state === 'blocked' ? 'Needs attention' : state === 'active' ? 'Working' : state === 'waiting' ? 'Waiting' : 'Proposed'
  return (
    <div className={`flex items-center gap-3 rounded-lg border p-4 ${state === 'active' ? 'border-brand/40 bg-brand/7' : state === 'blocked' ? 'border-warning/45 bg-warning/5' : 'bg-card'}`}>
      <div className={`flex size-7 items-center justify-center rounded-full ${state === 'blocked' ? 'bg-warning/15 text-warning' : state === 'complete' || state === 'active' ? 'bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'}`}>
        <Icon className={`size-3.5 ${state === 'active' ? 'animate-spin' : ''}`} />
      </div>
      <div className="min-w-0 flex-1"><div className="text-sm font-medium">{label}</div><div className="mt-0.5 text-xs text-muted-foreground">{result}</div></div>
      <Badge variant="secondary" className="rounded-sm font-mono text-[9px]">{stateLabel}</Badge>
    </div>
  )
}
