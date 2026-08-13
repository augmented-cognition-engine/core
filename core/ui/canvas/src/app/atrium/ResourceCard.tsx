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
}: {
  readonly record: IntelligenceResourceRecord
  readonly featured?: boolean
}) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <button
          type="button"
          className="group w-full rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          aria-label={`Open ${record.title}`}
        >
          <Card className="transition-colors duration-200 group-hover:border-foreground/25">
            <CardContent className={featured ? 'p-6 md:p-7' : 'p-4'}>
              <div className="flex items-start gap-3">
                <div
                  className={
                    record.availability === 'degraded'
                      ? 'mt-1 flex size-8 shrink-0 items-center justify-center rounded-lg bg-warning/15 text-warning-foreground'
                      : 'mt-1 flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand'
                  }
                >
                  {record.availability === 'degraded' ? (
                    <CircleAlert className="size-4" />
                  ) : (
                    <ShieldCheck className="size-4" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge variant="secondary" className="font-mono text-[10px]">
                      {kindLabel(record.reference.resource_kind)}
                    </Badge>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {availabilityLabel(record)} · {relativeTime(record.reference.available_at)}
                    </span>
                  </div>
                  <h3
                    className={
                      featured
                        ? 'text-xl font-semibold leading-tight tracking-tight'
                        : 'text-sm font-semibold leading-snug tracking-tight'
                    }
                  >
                    {record.title}
                  </h3>
                  {record.summary !== null && (
                    <p
                      className={
                        featured
                          ? 'mt-3 max-w-3xl text-sm leading-relaxed text-muted-foreground'
                          : 'mt-1.5 line-clamp-2 text-xs leading-relaxed text-muted-foreground'
                      }
                    >
                      {record.summary}
                    </p>
                  )}
                  <div className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
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
          <SheetDescription className="leading-relaxed">
            {record.summary ?? 'This resource does not include a narrative summary.'}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-6 p-6">
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
