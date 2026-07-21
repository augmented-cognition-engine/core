import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleHelp,
  Compass,
  GitBranch,
  History,
  Layers3,
  LockKeyhole,
  RefreshCcw,
  Scale,
} from 'lucide-react'

import {
  landscapeApi,
  type LandscapeAssertion,
  type LandscapeRecord,
  type LandscapeRelationship,
  type LivingProductSnapshot,
} from '@/api/landscapeApi'
import { Button, Card, Chip, EmptyState, Eyebrow, StatusBadge } from '@/design/components'
import { SidebarInset, SidebarProvider } from '@/design/shadcn/ui/sidebar'

import { extensionSlot } from './ext/registry'
import { KernelNav } from './ext/defaults/KernelNav'
import { projectProductMap } from './productMapProjection'

const Nav = extensionSlot('nav') ?? KernelNav
const MAX_VISIBLE_ROWS = 6
const loadDefaultSnapshot = () => landscapeApi.get()

type AssertionStatus = 'accepted' | 'provisional' | 'contested' | 'rejected' | 'unknown'

export interface ProductMapProps {
  loadSnapshot?: () => Promise<LivingProductSnapshot>
}

function text(record: LandscapeRecord | null | undefined, keys: string[]): string | null {
  if (record === null || record === undefined) return null
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim() !== '') return value.trim()
  }
  return null
}

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter: string) => letter.toUpperCase())
}

function compactId(id: string): string {
  const parts = id.split(':')
  const tail = id.includes(':') ? parts[parts.length - 1] ?? id : id
  return tail.length > 16 ? `${tail.slice(0, 8)}…${tail.slice(-5)}` : tail
}

function recordTitle(record: LandscapeRecord): string {
  const objectType = text(record, ['object_type'])
  if (objectType === 'decision_prediction' && typeof record.decision === 'string') {
    return `Prediction for ${compactId(record.decision)}`
  }
  if (objectType === 'prediction_outcome' && typeof record.prediction === 'string') {
    return `Outcome for ${compactId(record.prediction)}`
  }
  if (objectType === 'outcome_observation' && typeof record.emission_topic === 'string') {
    return `${titleCase(String(record.outcome_label ?? 'Observed'))}: ${record.emission_topic}`
  }
  return (
    text(record, [
      'name',
      'title',
      'statement',
      'summary',
      'description',
      'content',
      'intent',
      'event_type',
      'outcome',
      'code',
    ]) ??
    compactId(record.id)
  )
}

function allRecords(snapshot: LivingProductSnapshot): LandscapeRecord[] {
  const product = snapshot.product === null ? [] : [snapshot.product]
  return [
    ...product,
    ...snapshot.intent.directions,
    ...snapshot.intent.visions,
    ...snapshot.projects,
    ...snapshot.capabilities.items,
    ...snapshot.capabilities.quality,
    ...snapshot.relationships.assertions,
    ...snapshot.relationships.operational,
    ...snapshot.relationships.structural,
    ...snapshot.history.assertion_events,
    ...snapshot.decisions,
    ...snapshot.foresight.predictions,
    ...snapshot.foresight.prediction_outcomes,
    ...snapshot.foresight.outcome_observations,
    ...snapshot.foresight.action_outcomes,
    ...snapshot.intelligence.observations,
    ...snapshot.intelligence.insights,
    ...snapshot.work.tasks,
    ...snapshot.work.initiatives,
    ...snapshot.work.milestones,
    ...snapshot.work.work_items,
  ]
}

function assertionStatus(assertion: LandscapeAssertion): AssertionStatus {
  const status = assertion.status?.toLowerCase()
  if (status === 'accepted' || status === 'provisional' || status === 'contested' || status === 'rejected') {
    return status
  }
  return 'unknown'
}

function statusTone(status: string): string | undefined {
  switch (status.toLowerCase()) {
    case 'complete':
    case 'available':
    case 'accepted':
      return 'var(--color-emerald-600)'
    case 'partial':
    case 'provisional':
      return 'var(--color-amber-600)'
    case 'degraded':
    case 'contested':
      return 'var(--color-orange-600)'
    case 'unknown':
    case 'unavailable':
    case 'rejected':
      return 'var(--color-red-600)'
    default:
      return undefined
  }
}

function SectionHeading({ eyebrow, title, copy }: { eyebrow: string; title: string; copy: string }) {
  return (
    <div className="flex flex-col gap-1">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="text-lg font-semibold tracking-tight text-foreground">{title}</h2>
      <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{copy}</p>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card padding="sm" variant="subtle" className="min-w-0">
      <div className="text-2xl font-semibold tabular-nums text-foreground">{value}</div>
      <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{label}</div>
    </Card>
  )
}

function RecordList({ rows, empty, label }: { rows: LandscapeRecord[]; empty: string; label: string }) {
  if (rows.length === 0) return <EmptyState prompt={empty} />
  return (
    <ul aria-label={label} className="divide-y divide-border">
      {rows.slice(0, MAX_VISIBLE_ROWS).map((row) => (
        <li key={row.id} className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0">
          <div className="min-w-0">
            <div className="text-sm font-medium leading-snug text-foreground">{recordTitle(row)}</div>
            {text(row, ['description', 'rationale', 'summary', 'detail', 'recovery']) !== null && (
              <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                {text(row, ['description', 'rationale', 'summary', 'detail', 'recovery'])}
              </div>
            )}
            {typeof row.recovery === 'string' && text(row, ['detail']) !== null && (
              <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Recovery: {row.recovery}
              </div>
            )}
          </div>
          <code className="shrink-0 text-[10px] text-muted-foreground" title={row.id}>
            {compactId(row.id)}
          </code>
        </li>
      ))}
      {rows.length > MAX_VISIBLE_ROWS && (
        <li className="pt-3 text-xs text-muted-foreground">+ {rows.length - MAX_VISIBLE_ROWS} more in this bounded snapshot</li>
      )}
    </ul>
  )
}

function RelationshipList({
  rows,
  index,
  empty,
}: {
  rows: LandscapeRelationship[]
  index: Map<string, LandscapeRecord>
  empty: string
}) {
  if (rows.length === 0) return <EmptyState prompt={empty} />
  return (
    <ul aria-label="Operational relationships" className="flex flex-col gap-3">
      {rows.slice(0, MAX_VISIBLE_ROWS).map((row) => {
        const subject = row.subject ?? row.source_id ?? ''
        const object = row.object ?? row.target_id ?? ''
        const predicate = row.predicate ?? row.relationship_type ?? 'relates to'
        return (
          <li key={row.id} className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 rounded-lg border bg-muted/20 px-3 py-3">
            <span className="truncate text-sm font-medium text-foreground" title={subject}>
              {index.has(subject) ? recordTitle(index.get(subject)!) : compactId(subject)}
            </span>
            <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              {titleCase(predicate)} <ArrowRight className="size-3" />
            </span>
            <span className="truncate text-sm font-medium text-foreground" title={object}>
              {index.has(object) ? recordTitle(index.get(object)!) : compactId(object)}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function AssertionCard({ assertion, index }: { assertion: LandscapeAssertion; index: Map<string, LandscapeRecord> }) {
  const subject = assertion.subject ?? ''
  const object = assertion.object ?? ''
  const status = assertionStatus(assertion)
  const confidence = assertion.proposal_confidence
  return (
    <Card padding="sm" variant="subtle" dataTest={`assertion-${status}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 text-sm font-medium leading-snug text-foreground">
          {index.has(subject) ? recordTitle(index.get(subject)!) : compactId(subject)}{' '}
          <span className="font-normal text-muted-foreground">{titleCase(assertion.predicate ?? 'relates to')}</span>{' '}
          {index.has(object) ? recordTitle(index.get(object)!) : compactId(object)}
        </div>
        <StatusBadge label={status} tone={statusTone(status)} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
        {typeof confidence === 'number' && <Chip variant="ghost">confidence {Math.round(confidence * 100)}%</Chip>}
        <Chip variant="ghost">evidence {assertion.evidence_refs?.length ?? 0}</Chip>
        {(assertion.contradicting_assertions?.length ?? 0) > 0 && (
          <Chip variant="ghost">contradictions {assertion.contradicting_assertions!.length}</Chip>
        )}
        <code title={assertion.id}>{compactId(assertion.id)}</code>
      </div>
      {assertion.explanation !== undefined && (
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{assertion.explanation}</p>
      )}
    </Card>
  )
}

function AssertionLane({
  label,
  rows,
  index,
  empty,
}: {
  label: string
  rows: LandscapeAssertion[]
  index: Map<string, LandscapeRecord>
  empty: string
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">{label}</h3>
        <span className="text-xs tabular-nums text-muted-foreground">{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">{empty}</p>
      ) : (
        rows.slice(0, MAX_VISIBLE_ROWS).map((assertion) => (
          <AssertionCard key={assertion.id} assertion={assertion} index={index} />
        ))
      )}
    </div>
  )
}

function SummaryCard({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <Card padding="md" className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">{icon}</span>
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      </div>
      {children}
    </Card>
  )
}

function SourceReceiptRows({ snapshot }: { snapshot: LivingProductSnapshot }) {
  const unavailable = snapshot.source_states.filter((source) => source.status !== 'available')
  const available = snapshot.source_states.filter((source) => source.status === 'available')

  const rows = (sources: LivingProductSnapshot['source_states']) => (
    <ul aria-label="Source receipts" className="divide-y divide-border">
      {sources.map((source) => (
        <li key={source.source} className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0">
          <div>
            <div className="text-sm font-medium text-foreground">{titleCase(source.source)}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {source.record_count} records · {source.required ? 'required' : 'optional'} ·{' '}
              {source.limit === null ? 'bound not reported' : `limit ${source.limit}`}
            </div>
            {source.reason !== null && source.reason !== undefined && (
              <div className="mt-1 text-xs text-muted-foreground">{source.reason}</div>
            )}
          </div>
          <StatusBadge label={source.status} tone={statusTone(source.status)} />
        </li>
      ))}
    </ul>
  )

  if (snapshot.source_states.length === 0) {
    return <EmptyState prompt="No source receipts were returned; completeness is unknown." />
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Chip variant="ghost">{available.length} available</Chip>
        {unavailable.length > 0 && <Chip variant="ghost">{unavailable.length} need attention</Chip>}
      </div>
      {unavailable.length > 0 && rows(unavailable)}
      {available.length > 0 && (
        <details className="rounded-lg border bg-muted/20 px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium text-foreground">
            Inspect {available.length} available source receipts
          </summary>
          <div className="mt-4">{rows(available)}</div>
        </details>
      )}
    </div>
  )
}

function ProductMapContent({ snapshot }: { snapshot: LivingProductSnapshot }) {
  const projection = useMemo(() => projectProductMap(snapshot), [snapshot])
  const index = useMemo(() => new Map(allRecords(snapshot).map((record) => [record.id, record])), [snapshot])
  const unresolvedAssertions = [
    ...projection.assertions.provisional,
    ...projection.assertions.contested,
    ...projection.assertions.unknown,
  ]
  const unavailableSources = snapshot.source_states.filter((source) => source.status !== 'available')
  const statusNeedsAttention = projection.status !== 'complete'

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 py-8 md:px-8 md:py-10" data-test="product-map">
      <header className="flex flex-col gap-5">
        <div className="flex flex-wrap items-center gap-2">
          <Eyebrow>Living Product Graph</Eyebrow>
          <Chip variant="ghost"><LockKeyhole className="mr-1 size-3" /> read-only</Chip>
          <StatusBadge label={projection.status} tone={statusTone(projection.status)} />
        </div>
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div className="flex max-w-3xl flex-col gap-2">
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">Product map</h1>
            <p className="text-base leading-relaxed text-muted-foreground">
              See what exists, how it connects, why it is believed, what changed, and what happened next.
              This surface inspects a bounded snapshot and cannot write, dispatch, or run models.
            </p>
          </div>
          <div className="text-left md:text-right">
            <div className="text-sm font-semibold text-foreground">{projection.productName}</div>
            <code className="text-[10px] text-muted-foreground" title={projection.productId ?? undefined}>
              {projection.productId === null ? 'product identity unavailable' : projection.productId}
            </code>
          </div>
        </div>
        {statusNeedsAttention && (
          <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3" role="status">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-700" />
            <div className="text-sm text-foreground">
              <span className="font-semibold">Snapshot is {projection.status}.</span>{' '}
              Missing or degraded sources stay visible below; absent data is not treated as empty truth.
            </div>
          </div>
        )}
      </header>

      <section aria-labelledby="map-at-a-glance" className="flex flex-col gap-4">
        <SectionHeading
          eyebrow="Orientation"
          title="At a glance"
          copy="Counts reflect this snapshot only. They are an index into the sections below, not a health score."
        />
        <div id="map-at-a-glance" className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="projects" value={projection.counts.projects} />
          <Stat label="capabilities" value={projection.counts.capabilities} />
          <Stat label="decisions" value={projection.counts.decisions} />
          <Stat label="current links" value={projection.counts.relationships} />
          <Stat label="need attention" value={projection.counts.attention} />
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <SectionHeading
          eyebrow="1 · Inventory"
          title="What exists"
          copy="Product intent and delivered or planned structure, grouped by the objects operators look for first."
        />
        <div className="grid gap-4 md:grid-cols-3">
          <SummaryCard icon={<Compass className="size-4" />} title="Intent">
            <RecordList rows={[...snapshot.intent.directions, ...snapshot.intent.visions]} empty="No direction or vision is present in this snapshot." label="Product intent" />
          </SummaryCard>
          <SummaryCard icon={<Layers3 className="size-4" />} title="Projects">
            <RecordList rows={snapshot.projects} empty="No projects are present in this snapshot." label="Projects" />
          </SummaryCard>
          <SummaryCard icon={<CheckCircle2 className="size-4" />} title="Capabilities">
            <RecordList rows={snapshot.capabilities.items} empty="No capabilities are present in this snapshot." label="Capabilities" />
          </SummaryCard>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <SectionHeading
          eyebrow="2 · Structure"
          title="How it connects"
          copy="Only accepted, projection-eligible relationships appear as current product truth. Structural links remain separate from assertion status."
        />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(18rem,0.5fr)]">
          <SummaryCard icon={<GitBranch className="size-4" />} title="Current relationships">
            <RelationshipList rows={snapshot.relationships.operational} index={index} empty="No accepted operational relationships are present." />
          </SummaryCard>
          <SummaryCard icon={<Scale className="size-4" />} title="Assertion states">
            <div className="grid grid-cols-2 gap-3">
              {(['accepted', 'provisional', 'contested', 'rejected'] as const).map((status) => (
                <div key={status} className="rounded-lg border bg-muted/20 p-3">
                  <div className="text-xl font-semibold tabular-nums text-foreground">{projection.assertions[status].length}</div>
                  <StatusBadge label={status} tone={statusTone(status)} />
                </div>
              ))}
            </div>
          </SummaryCard>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <SectionHeading
          eyebrow="3 · Grounds"
          title="Why we believe it"
          copy="Evidence, confidence, contradictions, and stable assertion identity stay attached. Dissent is displayed, never collapsed into operational truth."
        />
        <div className="grid gap-5 lg:grid-cols-2">
          <AssertionLane label="Accepted grounds" rows={projection.assertions.accepted} index={index} empty="No accepted assertions are present." />
          <AssertionLane label="Unresolved or disputed" rows={unresolvedAssertions} index={index} empty="No provisional, contested, or unknown assertions are present." />
        </div>
        {projection.assertions.rejected.length > 0 && (
          <SummaryCard icon={<CircleHelp className="size-4" />} title="Ruled out">
            <div className="grid gap-3 md:grid-cols-2">
              {projection.assertions.rejected.slice(0, MAX_VISIBLE_ROWS).map((assertion) => (
                <AssertionCard key={assertion.id} assertion={assertion} index={index} />
              ))}
            </div>
          </SummaryCard>
        )}
      </section>

      <section className="flex flex-col gap-4">
        <SectionHeading
          eyebrow="4 · History"
          title="What changed"
          copy="Binding decisions, explicit corrections, and assertion history remain distinct so an operator can follow the trail without rewriting it."
        />
        <div className="grid gap-4 md:grid-cols-3">
          <SummaryCard icon={<Scale className="size-4" />} title="Decisions">
            <RecordList rows={snapshot.decisions} empty="No decisions are present in this snapshot." label="Decisions" />
          </SummaryCard>
          <SummaryCard icon={<RefreshCcw className="size-4" />} title="Corrections">
            <RecordList rows={projection.corrections} empty="No explicit corrections are present in this snapshot." label="Corrections" />
          </SummaryCard>
          <SummaryCard icon={<History className="size-4" />} title="Assertion history">
            <RecordList rows={snapshot.history.assertion_events} empty="No assertion events are present in this snapshot." label="Assertion history" />
          </SummaryCard>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <SectionHeading
          eyebrow="5 · Consequences"
          title="What happened next"
          copy="Predictions remain separate from observed outcomes; an unobserved prediction is not presented as a result."
        />
        <div className="grid gap-4 md:grid-cols-2">
          <SummaryCard icon={<Compass className="size-4" />} title="Predictions">
            <RecordList rows={snapshot.foresight.predictions} empty="No predictions are present in this snapshot." label="Predictions" />
          </SummaryCard>
          <SummaryCard icon={<CheckCircle2 className="size-4" />} title="Observed outcomes">
            <RecordList rows={projection.outcomes} empty="No observed outcomes are present in this snapshot." label="Observed outcomes" />
          </SummaryCard>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <SectionHeading
          eyebrow="6 · Reliability"
          title="What needs attention"
          copy="Projection issues and source receipts stay explicit, including recovery guidance supplied by the read contract."
        />
        <div className="grid gap-4 md:grid-cols-2">
          <SummaryCard icon={<AlertTriangle className="size-4" />} title="Projection issues">
            <RecordList rows={snapshot.issues} empty="No projection issues were reported." label="Projection issues" />
          </SummaryCard>
          <SummaryCard icon={<LockKeyhole className="size-4" />} title="Source receipts">
            <SourceReceiptRows snapshot={snapshot} />
            {unavailableSources.length > 0 && (
              <p className="text-xs text-muted-foreground">{unavailableSources.length} source receipt(s) are not available.</p>
            )}
          </SummaryCard>
        </div>
      </section>

      <footer className="flex flex-col gap-2 border-t pt-5 text-xs text-muted-foreground md:flex-row md:items-center md:justify-between">
        <span>Snapshot <code title={snapshot.snapshot_id}>{compactId(snapshot.snapshot_id)}</code></span>
        <span>{snapshot.schema_version} · {snapshot.projection_version}</span>
      </footer>
    </div>
  )
}

export function ProductMap({ loadSnapshot = loadDefaultSnapshot }: ProductMapProps) {
  const [snapshot, setSnapshot] = useState<LivingProductSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => setAttempt((value) => value + 1), [])

  useEffect(() => {
    let active = true
    setSnapshot(null)
    setError(null)
    loadSnapshot()
      .then((result) => {
        if (active) setSnapshot(result)
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : 'Landscape read failed')
      })
    return () => {
      active = false
    }
  }, [attempt, loadSnapshot])

  return (
    <SidebarProvider>
      <Nav />
      <SidebarInset className="h-svh overflow-y-auto bg-muted/40">
        {snapshot === null && error === null && (
          <div className="flex min-h-svh items-center justify-center px-6" role="status">
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <RefreshCcw className="size-4 animate-spin" /> Reading the product map…
            </div>
          </div>
        )}
        {error !== null && (
          <div className="flex min-h-svh items-center justify-center px-6">
            <Card padding="lg" className="max-w-lg text-center">
              <AlertTriangle className="mx-auto size-6 text-destructive" />
              <h1 className="mt-3 text-lg font-semibold text-foreground">Product map unavailable</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                The read-only snapshot could not be loaded. No state was changed.
              </p>
              <code className="mt-3 block text-xs text-muted-foreground">{error}</code>
              <div className="mt-5">
                <Button variant="secondary" onClick={retry}>
                  <RefreshCcw className="mr-2 size-4" /> Retry read
                </Button>
              </div>
            </Card>
          </div>
        )}
        {snapshot !== null && <ProductMapContent snapshot={snapshot} />}
      </SidebarInset>
    </SidebarProvider>
  )
}
