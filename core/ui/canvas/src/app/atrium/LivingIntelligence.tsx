import { type ReactNode, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Check,
  ChevronDown,
  CircleAlert,
  type LucideIcon,
} from 'lucide-react'

import {
  submitIntelligenceResourceFeedback,
  type IntelligenceResourceCorrectionIntent,
  type IntelligenceResourcePage,
  type IntelligenceResourceRecord,
} from '@/api/intelligenceResourcesApi'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/design/shadcn/ui/sheet'
import { Separator } from '@/design/shadcn/ui/separator'
import { Textarea } from '@/design/shadcn/ui/textarea'

import { AskAce } from './AskAce'
import { ATRIUM_INTELLIGENCE_ICONS } from './atriumIcons'
import {
  kindLabel,
  type ResourceGroups,
} from './intelligenceModel'
import { pageFreshness, payloadText } from './experienceModel'
import {
  challengeProjectionForRecord,
  domainHealthProjection,
  whyProjectionForRecord,
  type TrustSupport,
} from './trustProjection'

const SignalIcon = ATRIUM_INTELLIGENCE_ICONS.signal
const UnknownIcon = ATRIUM_INTELLIGENCE_ICONS.unknown
const AttentionIcon = ATRIUM_INTELLIGENCE_ICONS.attention

interface DomainHealthItem {
  readonly label: string
  readonly value: string
  readonly detail: string
  readonly support: TrustSupport
  readonly literalStatus?: 'healthy' | 'warning'
}

// Dimensions ACE currently backs with measured/derived/observed contract data,
// vs. dimensions it cannot yet claim (not_supported/unavailable). Grouping,
// not scoring: this never becomes a count-based health signal.
const EVIDENCE_BACKED_SUPPORT: ReadonlySet<TrustSupport> = new Set(['measured', 'derived', 'observed'])

interface DomainHealthGroups {
  readonly attention: readonly DomainHealthItem[]
  readonly supported: readonly DomainHealthItem[]
  readonly notMeasured: readonly DomainHealthItem[]
}

export function groupDomainHealth(health: readonly DomainHealthItem[]): DomainHealthGroups {
  const attention = health.filter((item) => item.literalStatus === 'warning')
  const remaining = health.filter((item) => item.literalStatus !== 'warning')
  return {
    attention,
    supported: remaining.filter((item) => EVIDENCE_BACKED_SUPPORT.has(item.support)),
    notMeasured: remaining.filter((item) => !EVIDENCE_BACKED_SUPPORT.has(item.support)),
  }
}

export function domainHealthGroupLabels(
  page: IntelligenceResourcePage | null,
  items: readonly IntelligenceResourceRecord[],
): { readonly attention: string[]; readonly supported: string[]; readonly notMeasured: string[] } {
  const groups = groupDomainHealth(domainHealthFromResources(page, items))
  return {
    attention: groups.attention.map((item) => item.label),
    supported: groups.supported.map((item) => item.label),
    notMeasured: groups.notMeasured.map((item) => item.label),
  }
}

interface WhyStep {
  readonly label: string
  readonly body: string
}

const CORRECTION_INTENTS = {
  'This claim is outdated': 'outdated',
  'The entity mapping is wrong': 'entity_mapping_wrong',
  'ACE missed a source': 'missing_source',
  'A source is over-weighted': 'source_overweighted',
} as const satisfies Record<string, IntelligenceResourceCorrectionIntent>

function correctionRequestKey(): string {
  const randomId = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `feedback-request:${randomId}`
}

function recordsOfKind(
  items: readonly IntelligenceResourceRecord[],
  kind: IntelligenceResourceRecord['reference']['resource_kind'],
): IntelligenceResourceRecord[] {
  return items.filter((item) => item.reference.resource_kind === kind)
}

function linkedRecords(
  record: IntelligenceResourceRecord,
  items: readonly IntelligenceResourceRecord[],
): IntelligenceResourceRecord[] {
  const references = new Set(
    record.provenance.map((reference) => `${reference.resource_id}:${reference.revision}`),
  )
  return items.filter((item) =>
    references.has(`${item.reference.resource_id}:${item.reference.revision}`),
  )
}

function recordsLinkedTo(
  record: IntelligenceResourceRecord,
  items: readonly IntelligenceResourceRecord[],
): IntelligenceResourceRecord[] {
  return items.filter((item) => item.provenance.some((reference) =>
    reference.resource_id === record.reference.resource_id
      && reference.revision === record.reference.revision,
  ))
}

function formattedDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.valueOf())) return 'Recalculation time unavailable'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(parsed)
}

export function domainHealthFromResources(
  page: IntelligenceResourcePage | null,
  items: readonly IntelligenceResourceRecord[],
): DomainHealthItem[] {
  return domainHealthProjection(page, items).dimensions.map((dimension) => ({
    label: dimension.label,
    value: dimension.value,
    detail: dimension.detail,
    support: dimension.support,
    literalStatus: dimension.attention ? 'warning' : undefined,
  }))
}

export function whyStepsForRecord(
  record: IntelligenceResourceRecord,
  items: readonly IntelligenceResourceRecord[],
): WhyStep[] {
  return whyProjectionForRecord(record, items, null).stages.map(({ label, body }) => ({ label, body }))
}

function StatusMark({ status }: { readonly status: DomainHealthItem['literalStatus'] }) {
  if (status === 'healthy') return <Check className="size-3 text-success" aria-hidden="true" />
  if (status === 'warning') return <CircleAlert className="size-3 text-warning" aria-hidden="true" />
  return <span className="size-1.5 rounded-full bg-muted-foreground/45" aria-hidden="true" />
}

function DomainHealthRow({ item }: { readonly item: DomainHealthItem }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 border-t border-border/70 py-2.5 first:border-t-0">
      <dt className="text-[10px] text-muted-foreground">{item.label}</dt>
      <dd className="flex items-center gap-1.5 text-right font-mono text-[9px] text-foreground">
        <StatusMark status={item.literalStatus} />
        {item.value}
      </dd>
      <dd className="col-span-2 mt-1 text-[9px] leading-4 text-muted-foreground/75">
        {item.detail}
      </dd>
    </div>
  )
}

function DomainHealthSection({
  title,
  items,
  tone = 'neutral',
  compact,
}: {
  readonly title: string
  readonly items: readonly DomainHealthItem[]
  readonly tone?: 'attention' | 'neutral'
  readonly compact: boolean
}) {
  if (items.length === 0) return null
  return (
    <div className={compact ? 'mt-5 first:mt-0' : 'mt-4 first:mt-0'}>
      <div className={tone === 'attention'
        ? 'flex items-center gap-1.5 font-mono text-[8px] font-medium uppercase tracking-[0.14em] text-warning'
        : 'font-mono text-[8px] font-medium uppercase tracking-[0.14em] text-muted-foreground'}
      >
        {tone === 'attention' && <CircleAlert className="size-3" aria-hidden="true" />}
        {title}
      </div>
      <dl className={compact ? 'mt-2 grid gap-0 sm:grid-cols-2 sm:gap-x-8' : 'mt-2'}>
        {items.map((item) => <DomainHealthRow key={item.label} item={item} />)}
      </dl>
    </div>
  )
}

function NotMeasuredSection({
  items,
  compact,
}: {
  readonly items: readonly DomainHealthItem[]
  readonly compact: boolean
}) {
  if (items.length === 0) return null
  const title = `Not currently measured · ${items.length}`
  const rows = (
    <dl className={compact ? 'mt-2 grid gap-0 sm:grid-cols-2 sm:gap-x-8' : 'mt-2'}>
      {items.map((item) => <DomainHealthRow key={item.label} item={item} />)}
    </dl>
  )
  // Compact (Operate) keeps every dimension expanded with full basis/reason.
  // Non-compact (Overview) subordinates this group behind a native, keyboard-
  // accessible <details> — depth changes, the exact reasons stay reachable.
  if (compact) {
    return (
      <div className="mt-5 first:mt-0">
        <div className="font-mono text-[8px] font-medium uppercase tracking-[0.14em] text-muted-foreground/80">
          {title}
        </div>
        {rows}
      </div>
    )
  }
  return (
    <details className="group mt-4 first:mt-0">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-mono text-[8px] font-medium uppercase tracking-[0.14em] text-muted-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span>{title}</span>
        <ChevronDown className="size-3 transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
      </summary>
      {rows}
    </details>
  )
}

export function DomainHealthRail({
  page,
  items,
  compact = false,
}: {
  readonly page: IntelligenceResourcePage | null
  readonly items: readonly IntelligenceResourceRecord[]
  readonly compact?: boolean
}) {
  const health = domainHealthFromResources(page, items)
  const groups = groupDomainHealth(health)
  const evidenceBackedCount = groups.attention.length + groups.supported.length
  return (
    <section
      aria-label="Domain Health"
      className={compact
        ? 'border-t border-border/80 pt-4'
        : 'border-t border-border/80 pt-5 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0'}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-mono text-[9px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
            Domain Health
          </div>
          <h2 className="mt-1 text-sm font-medium tracking-tight">Maintained with limits</h2>
          <div className="mt-1 font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground/60">
            Contract support · {evidenceBackedCount} available · {groups.notMeasured.length} not measured
          </div>
        </div>
        <Link
          to="/atrium/operate"
          className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Operate →
        </Link>
      </div>
      <DomainHealthSection title="Needs attention" items={groups.attention} tone="attention" compact={compact} />
      <DomainHealthSection title="Currently supported" items={groups.supported} compact={compact} />
      <NotMeasuredSection items={groups.notMeasured} compact={compact} />
    </section>
  )
}

function MaintenanceWeave({ items }: { readonly items: readonly IntelligenceResourceRecord[] }) {
  const sourceCount = recordsOfKind(items, 'source').length
  const signalCount = recordsOfKind(items, 'signal').length
  const briefCount = recordsOfKind(items, 'brief').length
  const active = sourceCount + signalCount + briefCount > 0

  return (
    <div className="atrium-maintenance-weave" data-active={active ? 'true' : 'false'} aria-hidden="true">
      <svg viewBox="0 0 260 180" role="presentation">
        <path d="M12 112C38 32 151 8 222 51c49 30 32 91-22 108-68 21-155-13-166-68-8-39 35-69 82-66 50 3 91 35 86 70-5 32-47 52-87 42-34-9-53-36-41-59 12-22 49-28 77-13" />
        <path d="M28 126C52 57 142 28 206 60c45 23 38 72-3 94-52 28-128 10-150-34-18-36 11-69 50-76 43-8 86 15 91 46 4 27-27 50-62 49-30-1-55-20-52-41 3-18 28-31 53-25" />
        <path d="M48 137C69 83 132 53 184 70c38 12 46 49 20 75-32 32-94 31-124 2-26-25-14-55 17-68 34-14 74-3 86 21 11 21-8 43-35 48-23 4-48-6-53-23-5-14 10-28 30-30" />
        <path d="M76 142C91 105 130 82 164 88c28 5 40 29 26 50-17 25-58 34-84 17-22-14-21-37-1-52 21-15 51-12 62 4 10 14-1 30-19 37" />
      </svg>
    </div>
  )
}

function WhySheet({
  record,
  items,
  children,
}: {
  readonly record: IntelligenceResourceRecord
  readonly items: readonly IntelligenceResourceRecord[]
  readonly children: ReactNode
}) {
  const projection = whyProjectionForRecord(record, items, null)
  const challenge = challengeProjectionForRecord(record, items)
  const steps = projection.stages
  const evidence = projection.supportingEvidence
  const conflicts = projection.conflictingEvidence
  const [selectedReason, setSelectedReason] = useState(challenge.reasons[0])
  const [correctionNote, setCorrectionNote] = useState('')
  const [correctionRequestId] = useState(correctionRequestKey)
  const [submissionState, setSubmissionState] = useState<
    | { readonly status: 'idle' | 'submitting' }
    | { readonly status: 'recorded'; readonly receiptId: string }
    | { readonly status: 'error'; readonly message: string }
  >({ status: 'idle' })

  async function submitCorrection() {
    const note = correctionNote.trim()
    if (note.length === 0 || selectedReason === undefined) return
    setSubmissionState({ status: 'submitting' })
    try {
      const admission = await submitIntelligenceResourceFeedback({
        requestKey: correctionRequestId,
        target: record.reference,
        correctionIntent: CORRECTION_INTENTS[selectedReason],
        note,
        evidence: record.provenance,
      })
      setSubmissionState({
        status: 'recorded',
        receiptId: admission.feedback.receipt_id,
      })
    } catch (error) {
      setSubmissionState({
        status: 'error',
        message: error instanceof Error ? error.message : 'The correction proposal could not be recorded.',
      })
    }
  }

  return (
    <Sheet>
      <SheetTrigger asChild>{children}</SheetTrigger>
      <SheetContent className="atrium-command-center dark overflow-y-auto border-l border-border bg-popover p-0 text-foreground motion-reduce:transition-none data-[side=right]:w-full data-[side=right]:sm:max-w-lg">
        <SheetHeader className="border-b border-border p-6 text-left">
          <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
            Why this assessment
          </div>
          <SheetTitle className="mt-2 text-xl font-medium leading-tight tracking-tight">
            {record.title}
          </SheetTitle>
          <SheetDescription className="text-xs leading-5">
            {payloadText(record.payload, 'why_it_matters')
              ?? record.summary
              ?? 'The current record does not project a plain-language assessment.'}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-6 p-6">
          <ol className="space-y-0" aria-label="Evidence-to-conclusion derivation">
            {steps.map((step, index) => (
              <li key={step.label} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3">
                <div className="relative flex justify-center">
                  <span className="relative z-10 flex size-6 items-center justify-center rounded-full border border-border bg-popover font-mono text-[8px] text-muted-foreground">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  {index < steps.length - 1 && <span className="absolute bottom-0 top-6 w-px bg-border" />}
                </div>
                <div className="pb-5">
                  <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
                    {step.label}
                  </div>
                  <p className="mt-1.5 text-[11px] leading-5 text-foreground/85">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>

          <Separator />

          <section>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
              Supporting evidence
            </div>
            {evidence.length === 0 ? (
              <p className="mt-3 text-xs leading-5 text-muted-foreground">
                No upstream resource is projected for this record.
              </p>
            ) : (
              <ol className="mt-3 divide-y divide-border border-y border-border">
                {evidence.map((item, index) => (
                  <li key={`${item.kind}:${item.title}:${index}`} className="flex gap-3 py-3">
                    <span className="font-mono text-[9px] text-foreground/65">[{index + 1}]</span>
                    <div className="min-w-0">
                      <div className="text-xs font-medium">{item.title}</div>
                      <div className="mt-1 font-mono text-[8px] text-muted-foreground">
                        {kindLabel(item.kind)} · {item.availability === 'not_loaded' ? 'exact reference not loaded' : item.availability}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="border border-warning/35 bg-warning/[0.04] p-4">
            <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.14em] text-warning">
              <CircleAlert className="size-3.5" aria-hidden="true" /> Limits and conflicts
            </div>
            <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
              {projection.confidence.support === 'measured'
                ? `The record reports ${projection.confidence.value} confidence.`
                : projection.confidence.value}
              {' '}
              {conflicts.length === 0
                ? 'No exact conflict record is loaded; this does not claim none exists.'
                : `${conflicts.length} exact conflict record${conflicts.length === 1 ? ' is' : 's are'} admitted.`}
            </p>
            {projection.unknowns.length > 0 && (
              <ul className="mt-3 space-y-1.5 text-[10px] leading-4 text-muted-foreground">
                {projection.unknowns.slice(0, 4).map((unknown) => <li key={unknown}>{unknown}</li>)}
              </ul>
            )}
          </section>

          <section className="border-t border-border pt-5">
            <details className="group">
              <summary className="cursor-pointer list-none text-[11px] font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                Challenge or correct this conclusion
              </summary>
              <p className="mt-3 text-[10px] leading-5 text-muted-foreground">
                ACE distinguishes four correction intents before any future model effect is considered.
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2" role="group" aria-label="Supported correction intents">
                {challenge.reasons.map((reason) => (
                  <button
                    key={reason}
                    type="button"
                    aria-pressed={selectedReason === reason}
                    className="border border-border px-3 py-2 text-left text-[9px] leading-4 text-foreground/80 transition-colors hover:border-foreground/30 aria-pressed:border-foreground/55 aria-pressed:bg-muted/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => setSelectedReason(reason)}
                  >
                    {reason}
                  </button>
                ))}
              </div>
              {challenge.existingProposals.length > 0 && (
                <div className="mt-4">
                  <div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">
                    Existing governed proposals
                  </div>
                  <ul className="mt-2 space-y-1.5 text-[9px] leading-4 text-foreground/80">
                    {challenge.existingProposals.map((proposal, index) => (
                      <li key={`${proposal.kind}:${proposal.title}:${index}`}>{proposal.title}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="mt-4 border border-border bg-card/40 p-3">
                <label
                  htmlFor={`correction-note-${record.reference.resource_id}`}
                  className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground"
                >
                  What should ACE review?
                </label>
                <Textarea
                  id={`correction-note-${record.reference.resource_id}`}
                  value={correctionNote}
                  onChange={(event) => setCorrectionNote(event.target.value)}
                  maxLength={4000}
                  placeholder="Describe what is wrong and point to the better evidence."
                  className="mt-2 min-h-24 rounded-sm border-border bg-background text-[11px] leading-5"
                />
                <div className="mt-2 text-[9px] leading-4 text-muted-foreground">
                  Targets {record.reference.resource_kind} · r{record.reference.revision} · {record.reference.resource_digest.slice(0, 18)}…
                  {record.provenance.length > 0 && ` · includes ${record.provenance.length} direct evidence reference${record.provenance.length === 1 ? '' : 's'}`}
                </div>
                <p className="mt-2 text-[9px] leading-4 text-muted-foreground">
                  {challenge.submission.reason}
                </p>
                <p className="mt-2 text-[9px] leading-4 text-muted-foreground">
                  {challenge.futureEffect}
                </p>
                <div className="mt-3 flex items-center gap-3">
                  <Button
                    type="button"
                    size="sm"
                    disabled={
                      correctionNote.trim().length === 0
                      || submissionState.status === 'submitting'
                      || submissionState.status === 'recorded'
                    }
                    onClick={() => void submitCorrection()}
                  >
                    {submissionState.status === 'submitting' ? 'Recording…' : 'Record proposal'}
                  </Button>
                  <div aria-live="polite" className="min-w-0 text-[9px] leading-4 text-muted-foreground">
                    {submissionState.status === 'recorded' && (
                      <span className="text-success">Recorded · {submissionState.receiptId}</span>
                    )}
                    {submissionState.status === 'error' && (
                      <span className="text-destructive">{submissionState.message}</span>
                    )}
                  </div>
                </div>
              </div>
            </details>
          </section>

          <div className="grid gap-4 border-t border-border pt-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto] sm:items-end">
            <div className="min-w-0">
              <div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">Record available</div>
              <div className="mt-1 text-[10px] text-foreground/80">{formattedDate(record.reference.available_at)}</div>
            </div>
            <div className="min-w-0">
              <div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">Recalculation</div>
              <div className="mt-1 text-[9px] leading-4 text-foreground/80">{projection.recalculation}</div>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link to="/atrium/operate">Open trust layer</Link>
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function EmptyLivingBrief({ onStart }: { readonly onStart: () => void }) {
  return (
    <section className="border-y border-border py-12 md:py-16">
      <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Start here</div>
      <h2 className="mt-4 max-w-3xl text-4xl font-normal leading-[1.04] tracking-[-0.035em] md:text-5xl">
        What should ACE understand?
      </h2>
      <p className="mt-4 max-w-2xl text-sm leading-6 text-muted-foreground">
        Describe the changing world you need to understand. ACE will propose the model, exact source plan, watches, and first cited intelligence state for review.
      </p>
      <Button type="button" className="mt-6" onClick={onStart}>
        Propose my intelligence system <ArrowRight className="size-4" aria-hidden="true" />
      </Button>
      <p className="mt-3 text-[10px] text-muted-foreground">
        Nothing is connected or activated until the reviewed plan crosses the existing authority boundary.
      </p>
    </section>
  )
}

function MovementBlock({
  eyebrow,
  record,
  items,
  fallback,
  icon: Icon,
}: {
  readonly eyebrow: string
  readonly record: IntelligenceResourceRecord | undefined
  readonly items: readonly IntelligenceResourceRecord[]
  readonly fallback: string
  readonly icon: LucideIcon
}) {
  return (
    <article className="min-h-36 border-t border-border py-5 md:border-l md:border-t-0 md:px-5 first:md:border-l-0 first:md:pl-0 last:md:pr-0">
      <div className="flex items-center gap-2 font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
        <Icon className="size-3" aria-hidden="true" /> {eyebrow}
      </div>
      {record === undefined ? (
        <p className="mt-4 max-w-sm text-[11px] leading-5 text-muted-foreground">{fallback}</p>
      ) : (
        <>
          <h3 className="mt-3 text-sm font-medium leading-snug tracking-tight">{record.title}</h3>
          <p className="mt-2 line-clamp-3 text-[10px] leading-4 text-muted-foreground">
            {record.summary ?? 'No summary is projected for this record.'}
          </p>
          <WhySheet record={record} items={items}>
            <button
              type="button"
              className="mt-4 inline-flex items-center gap-1.5 text-[10px] text-foreground underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Inspect <ArrowRight className="size-3" aria-hidden="true" />
            </button>
          </WhySheet>
        </>
      )}
    </article>
  )
}

export function LivingBriefOverview({
  page,
  groups,
  items,
  onStart,
}: {
  readonly page: IntelligenceResourcePage | null
  readonly groups: ResourceGroups
  readonly items: readonly IntelligenceResourceRecord[]
  readonly onStart: () => void
}) {
  const briefs = recordsOfKind(groups.intelligence, 'brief')
  const brief = briefs[0]
  const shift = recordsOfKind(groups.intelligence, 'shift')[0]
  const signal = recordsOfKind(groups.intelligence, 'signal')[0]
  const opening = recordsOfKind(groups.opportunities, 'case')[0]
  const unknown = items.find((item) => item.availability === 'degraded')

  if (brief === undefined) return <EmptyLivingBrief onStart={onStart} />

  const primaryWhy = shift ?? brief
  return (
    <div className="space-y-0">
      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_17rem] xl:gap-0">
        <div className="min-w-0 xl:pr-8">
          <section id="latest-brief" className="relative overflow-hidden border-b border-border pb-9 pt-3 md:pb-11 md:pt-5">
            <div className="relative z-10 max-w-4xl xl:pr-40">
              <div className="flex flex-wrap items-center gap-3 font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">
                <span>Brief · current</span>
                <span className="h-3 w-px bg-border" />
                <span>{pageFreshness(page)}</span>
              </div>
              <h2 className="mt-6 max-w-4xl text-[2.7rem] font-normal leading-[0.99] tracking-[-0.045em] text-balance md:text-[3.25rem]">
                {brief.title}
              </h2>
              <p className="mt-5 max-w-3xl text-sm leading-6 text-foreground/75 md:text-[15px]">
                {brief.summary ?? 'The current Brief does not project a narrative summary.'}
              </p>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <Button asChild>
                  <Link to="/atrium/explore">Explore the evidence <ArrowRight className="size-4" /></Link>
                </Button>
                <WhySheet record={primaryWhy} items={items}>
                  <Button type="button" variant="ghost">Why this conclusion?</Button>
                </WhySheet>
              </div>
            </div>
            <MaintenanceWeave items={items} />
          </section>

          <section className="border-b border-border py-7">
            <div className="flex items-end justify-between gap-4">
              <div>
                <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">
                  Material movement · 01
                </div>
                <h2 className="mt-2 text-xl font-normal tracking-[-0.025em]">What changed the picture</h2>
              </div>
              <Link to="/atrium/explore" className="hidden text-[10px] text-muted-foreground hover:text-foreground sm:inline">
                View focused timeline →
              </Link>
            </div>
            {shift === undefined ? (
              <p className="mt-5 text-xs text-muted-foreground">No material Shift is projected in the current page.</p>
            ) : (
              <div className="mt-5 grid gap-5 border-t border-border pt-5 md:grid-cols-[2rem_minmax(0,1.25fr)_minmax(16rem,0.75fr)]">
                <span className="font-mono text-[9px] text-muted-foreground">01</span>
                <div>
                  <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Shift · supported</div>
                  <h3 className="mt-2 text-2xl font-normal leading-tight tracking-[-0.025em]">{shift.title}</h3>
                  <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                    {payloadText(shift.payload, 'what_changed') ?? shift.summary ?? 'No change summary is projected.'}
                  </p>
                </div>
                <div className="border-t border-border pt-4 md:border-l md:border-t-0 md:pl-5 md:pt-0">
                  <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Implication</div>
                  <p className="mt-2 text-[11px] leading-5 text-foreground/80">
                    {payloadText(shift.payload, 'why_it_matters') ?? 'No implication is projected for this Shift.'}
                  </p>
                  <WhySheet record={shift} items={items}>
                    <button
                      type="button"
                      className="mt-4 inline-flex items-center gap-1.5 text-[10px] text-foreground underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      Open Why? <ArrowRight className="size-3" aria-hidden="true" />
                    </button>
                  </WhySheet>
                </div>
              </div>
            )}
          </section>

          <section className="grid md:grid-cols-3">
            <MovementBlock
              eyebrow="Signal · watching"
              record={signal}
              items={items}
              fallback="No Signal is projected in the current page."
              icon={SignalIcon}
            />
            <MovementBlock
              eyebrow="Unknown · explicit"
              record={unknown}
              items={items}
              fallback="Predicted coverage by entity, event, and signal is not projected by the current contract."
              icon={UnknownIcon}
            />
            <MovementBlock
              eyebrow="Attention · decision opening"
              record={opening}
              items={items}
              fallback="No evidence-backed decision opening is projected."
              icon={AttentionIcon}
            />
          </section>
        </div>

        <DomainHealthRail page={page} items={items} />
      </div>
    </div>
  )
}

function ResultSummary({ items }: { readonly items: readonly IntelligenceResourceRecord[] }) {
  const entries = [
    ['Answer', recordsOfKind(items, 'brief').length],
    ['Shifts', recordsOfKind(items, 'shift').length],
    ['Signals', recordsOfKind(items, 'signal').length],
    ['Entities', recordsOfKind(items, 'entity').length],
    ['Evidence', recordsOfKind(items, 'source').length],
    ['Unknowns', items.filter((item) => item.availability === 'degraded').length],
  ] as const
  return (
    <aside aria-label="Explore result summary" className="border-b border-border p-3 lg:border-b-0 lg:border-r">
      <div className="px-2 pb-3 font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Result summary</div>
      <ol className="grid grid-cols-3 gap-1 lg:grid-cols-1">
        {entries.map(([label, count], index) => (
          <li
            key={label}
            aria-current={index === 0 ? 'true' : undefined}
            className={index === 0
              ? 'flex items-center justify-between bg-accent px-2 py-2 text-[9px] text-foreground'
              : 'flex items-center justify-between px-2 py-2 text-[9px] text-muted-foreground'}
          >
            {label}<span className="font-mono text-[8px]">{count}</span>
          </li>
        ))}
      </ol>
    </aside>
  )
}

function FocusedRelationship({
  record,
  items,
}: {
  readonly record: IntelligenceResourceRecord
  readonly items: readonly IntelligenceResourceRecord[]
}) {
  const upstream = linkedRecords(record, items)[0]
  const downstream = recordsLinkedTo(record, items)[0]
  const nodes = [upstream, record, downstream].filter(
    (item): item is IntelligenceResourceRecord => item !== undefined,
  )
  return (
    <section className="mt-7 border border-border" aria-label="Focused relationships">
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Focused relationships</div>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px]">Depth 1</Badge>
      </header>
      <div className="flex min-h-36 flex-col items-stretch justify-center gap-2 p-4 sm:flex-row sm:items-center">
        {nodes.map((node, index) => (
          <div key={`${node.reference.resource_id}:${node.reference.revision}`} className="contents">
            <div className={node === record
              ? 'border border-brand/70 bg-brand/[0.08] px-3 py-2 text-center text-[9px] text-foreground'
              : 'border border-border bg-card px-3 py-2 text-center text-[9px] text-muted-foreground'}>
              <div className="font-mono text-[7px] uppercase tracking-[0.12em]">{kindLabel(node.reference.resource_kind)}</div>
              <div className="mt-1 max-w-40 truncate">{node.title}</div>
            </div>
            {index < nodes.length - 1 && <ArrowRight className="mx-auto size-3.5 rotate-90 text-muted-foreground sm:rotate-0" aria-hidden="true" />}
          </div>
        ))}
      </div>
      <footer className="border-t border-border px-4 py-2 text-[8px] text-muted-foreground">
        Only the selected record’s immediate evidence closure is shown.
      </footer>
    </section>
  )
}

export function ExploreIntelligence({
  items,
}: {
  readonly items: readonly IntelligenceResourceRecord[]
}) {
  const shift = recordsOfKind(items, 'shift')[0]
    ?? recordsOfKind(items, 'brief')[0]
  const evidence = shift === undefined ? [] : linkedRecords(shift, items)

  return (
    <div className="space-y-6">
      <div>
        <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Explore the world</div>
        <h2 className="mt-2 text-3xl font-normal tracking-[-0.035em]">Ask, then inspect the basis.</h2>
        <p className="mt-2 max-w-2xl text-xs leading-5 text-muted-foreground">
          Search the governed picture. ACE shows the answer, evidence, unknowns, and only the focused relationships needed to understand it.
        </p>
      </div>

      <AskAce items={items} />

      {shift === undefined ? (
        <div className="border-y border-border py-10 text-sm text-muted-foreground">
          No supported Brief or Shift is available to explore yet.
        </div>
      ) : (
        <section className="grid overflow-hidden border border-border lg:grid-cols-[9rem_minmax(0,1fr)_15rem]">
          <ResultSummary items={items} />
          <article className="min-w-0 p-5 md:p-7">
            <div className="flex items-center justify-between gap-3 font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
              <span>Supported answer</span>
              <span>{formattedDate(shift.reference.available_at)}</span>
            </div>
            <h3 className="mt-5 max-w-2xl text-3xl font-normal leading-[1.04] tracking-[-0.035em]">
              {shift.title}
            </h3>
            <p className="mt-4 max-w-2xl text-xs leading-5 text-muted-foreground">
              {payloadText(shift.payload, 'what_changed') ?? shift.summary ?? 'No answer summary is projected.'}
              {' '}
              {payloadText(shift.payload, 'why_it_matters') ?? ''}
            </p>
            <WhySheet record={shift} items={items}>
              <Button type="button" className="mt-5">Open Why? <ArrowRight className="size-4" /></Button>
            </WhySheet>
            <FocusedRelationship record={shift} items={items} />
          </article>
          <aside className="border-t border-border bg-card/35 p-4 lg:border-l lg:border-t-0">
            <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Evidence basis</div>
            {evidence.length === 0 ? (
              <p className="mt-4 text-[10px] leading-4 text-muted-foreground">No upstream evidence record is projected.</p>
            ) : (
              <ol className="mt-4 divide-y divide-border border-y border-border">
                {evidence.map((item, index) => (
                  <li key={`${item.reference.resource_id}:${item.reference.revision}`} className="py-3">
                    <div className="font-mono text-[8px] text-foreground/65">[{index + 1}]</div>
                    <div className="mt-2 text-[11px] font-medium leading-snug">{item.title}</div>
                    <p className="mt-1.5 text-[9px] leading-4 text-muted-foreground">
                      {item.summary ?? 'No source summary is projected.'}
                    </p>
                    <div className="mt-2 font-mono text-[7px] uppercase tracking-[0.1em] text-muted-foreground">
                      {kindLabel(item.reference.resource_kind)} · admitted
                    </div>
                  </li>
                ))}
              </ol>
            )}
            <div className="mt-4 border border-warning/35 bg-warning/[0.04] p-3">
              <div className="flex items-center gap-2 font-mono text-[8px] uppercase tracking-[0.12em] text-warning">
                <CircleAlert className="size-3" aria-hidden="true" /> Limit
              </div>
              <p className="mt-2 text-[9px] leading-4 text-muted-foreground">
                Confidence and predicted coverage remain unscored unless projected by the current contracts.
              </p>
            </div>
          </aside>
        </section>
      )}
    </div>
  )
}

export function SurfacePlaceholder({
  eyebrow,
  title,
  description,
  children,
}: {
  readonly eyebrow: string
  readonly title: string
  readonly description: string
  readonly children: ReactNode
}) {
  return (
    <div>
      <div className="border-b border-border pb-6">
        <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">{eyebrow}</div>
        <h2 className="mt-2 text-3xl font-normal tracking-[-0.035em]">{title}</h2>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-muted-foreground">{description}</p>
      </div>
      <div className="pt-6">{children}</div>
    </div>
  )
}
