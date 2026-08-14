import { ArrowUpRight, CircleAlert, GitBranch, ShieldCheck } from 'lucide-react'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/design/shadcn/ui/sheet'
import { Separator } from '@/design/shadcn/ui/separator'

import { compactReference, kindLabel } from './intelligenceModel'
import {
  type IntelligenceStorySection,
  intelligenceStoryForRecord,
  payloadNumber,
  payloadText,
} from './experienceModel'

function availabilityLabel(record: IntelligenceResourceRecord): string {
  if (record.availability === 'degraded') return 'Needs context'
  if (record.availability === 'tombstoned') return 'Closed'
  return 'Current'
}

function relativeTime(value: string): string {
  const elapsed = Date.now() - Date.parse(value)
  const minutes = Math.max(1, Math.floor(elapsed / 60_000))
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export function ResourceCard({
  record,
  featured = false,
  horizon = false,
  compact = false,
  storySections,
}: {
  readonly record: IntelligenceResourceRecord
  readonly featured?: boolean
  readonly horizon?: boolean
  readonly compact?: boolean
  readonly storySections?: readonly IntelligenceStorySection[]
}) {
  const whyItMatters = payloadText(record.payload, 'why_it_matters')
  const resolvedStorySections = storySections ?? intelligenceStoryForRecord(record)
  const whatChanged = resolvedStorySections.find((section) => section.id === 'what_changed')
  const confidence = payloadNumber(record.payload, 'confidence')
  const confidencePercent = confidence !== null && confidence >= 0 && confidence <= 1
    ? Math.round(confidence * 100)
    : null

  return (
    <Sheet>
      <SheetTrigger asChild>
        <button
          type="button"
          className="group w-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          aria-label={`Open ${record.title}`}
        >
          <Card className={horizon ? 'border-0 bg-transparent shadow-none' : featured ? 'border-brand/25 bg-card transition-colors duration-200 group-hover:border-brand/45' : 'transition-colors duration-200 group-hover:border-foreground/25'}>
            <CardContent className={horizon ? 'p-0' : featured ? 'p-6 md:p-7' : compact ? 'p-3.5' : 'p-4'}>
              <div className="flex items-start gap-3">
                <div
                  className={
                    record.availability === 'degraded'
                      ? 'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-warning/15 text-warning'
                      : 'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border border-brand/20 bg-brand/10 text-brand'
                  }
                >
                  {record.availability === 'degraded' ? <CircleAlert className="size-3.5" /> : <ShieldCheck className="size-3.5" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className={compact ? 'mb-1.5 flex flex-wrap items-center gap-2' : 'mb-2 flex flex-wrap items-center gap-2'}>
                    <Badge variant="secondary" className="h-5 rounded-sm border border-border/70 bg-muted px-1.5 font-mono text-[9px] uppercase tracking-wide">
                      {kindLabel(record.reference.resource_kind)}
                    </Badge>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {availabilityLabel(record)} · {relativeTime(record.reference.available_at)}
                    </span>
                    {confidencePercent !== null && (
                      <span className="font-mono text-[10px] text-muted-foreground">
                        · {confidencePercent}% confidence
                      </span>
                    )}
                  </div>
                  <h3
                    className={
                      featured
                        ? horizon
                          ? 'max-w-4xl text-[clamp(2rem,3.3vw,3.45rem)] font-[430] leading-[1.02] tracking-[-0.045em] text-white'
                          : 'max-w-3xl text-2xl font-semibold leading-[1.12] tracking-[-0.025em]'
                        : 'text-sm font-semibold leading-snug tracking-tight'
                    }
                  >
                    {record.title}
                  </h3>
                  {record.summary !== null && resolvedStorySections.length === 0 && (
                    <p
                      className={
                        featured
                          ? 'mt-3 line-clamp-6 max-w-3xl text-sm leading-6 text-muted-foreground md:line-clamp-none'
                          : 'mt-1.5 line-clamp-2 text-xs leading-relaxed text-muted-foreground'
                      }
                    >
                      {record.summary}
                    </p>
                  )}
                  {resolvedStorySections.length > 0 && (
                    <div className={featured
                      ? horizon
                        ? 'mt-7 grid border-y border-white/[0.08] sm:grid-cols-2'
                        : 'mt-5 grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2'
                      : 'mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-md border bg-border'}>
                      {resolvedStorySections.map((section) => (
                        <div key={section.id} className={featured ? horizon ? 'border-white/[0.08] py-3 pr-5 even:border-l even:pl-5' : 'bg-card p-4' : 'min-w-0 bg-card p-2.5'}>
                          <div className={featured
                            ? 'font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-brand'
                            : 'font-mono text-[8px] font-semibold uppercase tracking-[0.14em] text-brand'}>
                            {section.label}
                          </div>
                          <p className={featured
                            ? 'mt-1.5 text-xs leading-5 text-foreground/85'
                            : 'mt-1 line-clamp-2 text-[10px] leading-4 text-foreground/80'}>
                            {section.body}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                  {featured && resolvedStorySections.length === 0 && whyItMatters !== null && (
                    <div className="mt-5 border-l-2 border-brand/70 pl-3">
                      <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-brand">Why it matters</div>
                      <p className="mt-1 max-w-3xl text-xs leading-5 text-foreground/85">{whyItMatters}</p>
                    </div>
                  )}
                  <div className={compact ? 'mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground' : 'mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground'}>
                    <GitBranch className="size-3" />
                    <span>{record.provenance.length} evidence link{record.provenance.length === 1 ? '' : 's'}</span>
                    <ArrowUpRight className="ml-auto size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </button>
      </SheetTrigger>
      <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-xl">
        <SheetHeader className="border-b p-6 text-left">
          <div className="mb-2 flex items-center gap-2">
            <Badge variant="secondary">{kindLabel(record.reference.resource_kind)}</Badge>
            <Badge variant={record.availability === 'degraded' ? 'outline' : 'default'}>
              {availabilityLabel(record)}
            </Badge>
          </div>
          <SheetTitle className="text-xl leading-tight">{record.title}</SheetTitle>
          <SheetDescription className={resolvedStorySections.length > 0 ? 'sr-only' : 'leading-relaxed'}>
            {whatChanged?.body ?? record.summary ?? 'This resource does not include a narrative summary.'}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-6 p-6">
          {resolvedStorySections.length > 0 && (
            <section className="grid gap-3 sm:grid-cols-2">
              {resolvedStorySections.map((section) => (
                <div key={section.id} className="rounded-lg border border-brand/15 bg-brand/[0.035] p-4">
                  <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-brand">
                    {section.label}
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-foreground/90">{section.body}</p>
                </div>
              ))}
            </section>
          )}

          {resolvedStorySections.length === 0 && whyItMatters !== null && (
            <section className="rounded-lg border border-brand/20 bg-brand/5 p-4">
              <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-brand">
                Why it matters
              </div>
              <p className="mt-2 text-sm leading-relaxed text-foreground/90">{whyItMatters}</p>
            </section>
          )}

          <section>
            <div className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Resource receipt
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-xs">
              <dt className="text-muted-foreground">Revision</dt>
              <dd className="font-mono">{record.reference.revision}</dd>
              <dt className="text-muted-foreground">Available</dt>
              <dd>{new Date(record.reference.available_at).toLocaleString()}</dd>
              <dt className="text-muted-foreground">Identity</dt>
              <dd className="truncate font-mono" title={record.reference.resource_id}>
                {compactReference(record.reference.resource_id)}
              </dd>
              {confidencePercent !== null && (
                <>
                  <dt className="text-muted-foreground">Confidence</dt>
                  <dd className="font-mono">{confidencePercent}%</dd>
                </>
              )}
            </dl>
          </section>

          <Separator />

          <section>
            <div className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Evidence lineage
            </div>
            {record.provenance.length === 0 ? (
              <p className="text-xs leading-relaxed text-muted-foreground">
                This is a root resource. It has no upstream projected resources.
              </p>
            ) : (
              <ol className="space-y-2">
                {record.provenance.map((reference) => (
                  <li
                    key={`${reference.resource_id}:${reference.revision}`}
                    className="rounded-lg border bg-muted/30 p-3"
                  >
                    <div className="flex items-center gap-2">
                      <GitBranch className="size-3.5 text-brand" />
                      <span className="text-xs font-medium">{kindLabel(reference.resource_kind)}</span>
                      <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                        r{reference.revision}
                      </span>
                    </div>
                    <div className="mt-1 truncate font-mono text-[10px] text-muted-foreground">
                      {reference.resource_id}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {record.degraded_reason_refs.length > 0 && (
            <>
              <Separator />
              <section>
                <div className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  What is missing
                </div>
                <ul className="space-y-2">
                  {record.degraded_reason_refs.map((reason) => (
                    <li key={reason} className="flex items-start gap-2 text-xs text-muted-foreground">
                      <CircleAlert className="mt-0.5 size-3.5 shrink-0" />
                      <span>{compactReference(reason)}</span>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}

          <Button variant="outline" className="w-full" asChild>
            <a href={`/deliberation?topic=${encodeURIComponent(`Investigate ${record.title}`)}`}>
              Open an investigation
            </a>
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
