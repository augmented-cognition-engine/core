import { useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  Braces,
  CheckCircle2,
  GitBranch,
  Network,
  RefreshCw,
  SearchCode,
  ShieldCheck,
  TestTube2,
} from 'lucide-react'

import {
  inspectCodeJourney,
  sanitizeErrorDetail,
  type AtriumCodeJourneyResponse,
  type CodeJourneyInput,
} from '@/api/codeIntelligenceApi'
import { Alert, AlertDescription, AlertTitle } from '@/design/shadcn/ui/alert'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/design/shadcn/ui/card'
import { Input } from '@/design/shadcn/ui/input'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/design/shadcn/ui/sidebar'

import { KernelNav } from '../ext/defaults/KernelNav'

const DEFAULT_TARGET = 'core/engine/mcp/tools.py'
const DEFAULT_QUERY = 'What breaks if core.engine.mcp.tools.ace_impact changes, and why does this path exist?'
// Mirrors the backend's bounded query/target_path (min_length=3, max_length=500
// on CodeIntelligenceJourneyRequest) so the UI never submits an input the
// backend would reject on length alone.
const MAX_INSPECTION_INPUT_LENGTH = 500

function PathList({ items, empty }: { readonly items: readonly string[]; readonly empty: string }) {
  if (items.length === 0) return <p className="text-xs text-muted-foreground">{empty}</p>
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item} className="rounded border bg-muted/20 px-2.5 py-1.5 font-mono text-[10px] break-all">{item}</li>
      ))}
    </ul>
  )
}

function Metric({ label, value, detail }: { readonly label: string; readonly value: string | number; readonly detail: string }) {
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <div className="font-mono text-[8px] uppercase tracking-[0.15em] text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tracking-tight">{value}</div>
      <div className="mt-0.5 text-[10px] text-muted-foreground">{detail}</div>
    </div>
  )
}

function AuthorityBoundary({ result }: { readonly result: AtriumCodeJourneyResponse }) {
  const boundaries = [
    ['Source', result.lens.source_authority],
    ['Reasoning', result.lens.reasoning_authority],
    ['Delivery', result.lens.delivery_authority],
    ['Effect', result.lens.effect_authority],
    ['Execution', result.manifest.execution_authority],
  ] as const
  return (
    <Card>
      <CardHeader className="pb-3"><CardTitle className="text-sm">Authority boundary</CardTitle></CardHeader>
      <CardContent>
        <div className="grid gap-2 sm:grid-cols-5">
          {boundaries.map(([label, granted]) => (
            <div key={label} className="rounded-md border px-3 py-2">
              <div className="text-[10px] text-muted-foreground">{label}</div>
              <div className="mt-1 flex items-center gap-1.5 text-xs font-medium">
                <ShieldCheck className="size-3.5 text-brand" />
                {granted ? 'Granted' : 'Not granted'}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[10px] leading-4 text-muted-foreground">
          A coding agent must independently revalidate its execution authority. Atrium exposes manifest receipts, not source bodies.
        </p>
      </CardContent>
    </Card>
  )
}

function JourneyResult({
  result,
  submittedTarget,
  submittedQuery,
}: {
  readonly result: AtriumCodeJourneyResponse
  readonly submittedTarget: string
  readonly submittedQuery: string
}) {
  const { lens, manifest, handoff } = result
  const visibleNodes = lens.nodes.slice(0, 18)
  const visibleEvidence = lens.evidence.slice(0, 12)
  return (
    <div className="space-y-6">
      <div data-testid="journey-heading" className="flex flex-wrap items-baseline gap-2 text-xs text-muted-foreground">
        <span className="font-mono text-foreground">{submittedTarget}</span>
        <span aria-hidden="true">·</span>
        <span>{submittedQuery}</span>
      </div>

      {lens.index.dirty && (
        <Alert className="border-warning/45 bg-warning/5">
          <AlertTriangle className="size-4" />
          <AlertTitle>Working tree differs from the recorded revision</AlertTitle>
          <AlertDescription>Impact applies to the exact dirty-tree digest shown below, not just the Git revision.</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Files indexed" value={result.scanner_stats.files ?? 0} detail={`generation ${result.index_generation} · ${result.index_reopened ? 'reopened' : 'captured'}`} />
        <Metric label="Direct dependents" value={lens.impact.direct_dependents.length} detail={lens.impact.confidence} />
        <Metric label="Transitive dependents" value={lens.impact.transitive_dependents.length} detail="static graph" />
        <Metric label="Affected tests" value={lens.impact.affected_tests.length} detail="candidate verification" />
        <Metric label="Handoff context" value={manifest.blocks.length} detail={`${manifest.total_bytes.toLocaleString()} bytes`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm"><GitBranch className="size-4 text-brand" />Change impact</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div><div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Direct dependents</div><PathList items={lens.impact.direct_dependents} empty="No direct static dependents found." /></div>
            <div><div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Downstream</div><PathList items={lens.impact.transitive_dependents} empty="No additional transitive dependents found." /></div>
            <p className="border-t pt-3 text-[10px] leading-4 text-muted-foreground">{lens.impact.basis}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm"><TestTube2 className="size-4 text-brand" />Affected tests</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <PathList items={lens.impact.affected_tests} empty="No affected tests were found by the bounded analysis." />
            {lens.impact.known_coverage_gaps.map((gap) => <p key={gap} className="text-[10px] leading-4 text-warning">{gap}</p>)}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Card>
          <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-sm"><Network className="size-4 text-brand" />Repository connections</CardTitle></CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2">
            {visibleNodes.map((node) => (
              <div key={node.node_id} className="rounded-md border p-3">
                <div className="flex items-center justify-between gap-2"><Badge variant="outline" className="rounded-sm font-mono text-[8px]">{node.kind}</Badge><span className="text-[9px] text-muted-foreground">{node.confidence}</span></div>
                <div className="mt-2 truncate text-xs font-medium" title={node.label}>{node.label}</div>
                {node.path && <div className="mt-1 truncate font-mono text-[9px] text-muted-foreground" title={node.path}>{node.path}</div>}
                {node.detail && <p className="mt-2 text-[10px] leading-4 text-muted-foreground">{node.detail}</p>}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-sm"><Braces className="size-4 text-brand" />Disconnected candidates</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {lens.disconnected_symbols.slice(0, 12).map((candidate) => (
              <div key={candidate.symbol_id} className="rounded-md border p-3">
                <div className="flex items-center justify-between gap-2"><span className="font-mono text-[10px] font-medium">{candidate.symbol}</span><Badge variant="outline" className="rounded-sm text-[8px]">inferred</Badge></div>
                <div className="mt-1 font-mono text-[9px] text-muted-foreground">{candidate.path}:{candidate.line_start}</div>
                <p className="mt-2 text-[10px] leading-4 text-muted-foreground">{candidate.reason}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-sm"><SearchCode className="size-4 text-brand" />Evidence and provenance</CardTitle></CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {visibleEvidence.map((anchor) => (
            <div key={`${anchor.path}:${anchor.line_start}:${anchor.content_digest}`} className="rounded-md border p-3">
              <div className="font-mono text-[9px] break-all">{anchor.path}:{anchor.line_start}-{anchor.line_end}</div>
              <div className="mt-1 text-[9px] text-muted-foreground">{anchor.derivation} · {anchor.confidence}</div>
              <p className="mt-2 text-[10px] leading-4 text-muted-foreground">{anchor.explanation}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <AuthorityBoundary result={result} />

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm">Bounded coding-agent handoff</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-3">
            <div className="rounded border p-3"><div className="text-[9px] text-muted-foreground">Receiver</div><div className="mt-1 font-mono text-[10px] break-all">{handoff.receiver_ref}</div></div>
            <div className="rounded border p-3"><div className="text-[9px] text-muted-foreground">Manifest</div><div className="mt-1 font-mono text-[10px] break-all">{handoff.manifest_id}</div></div>
            <div className="rounded border p-3"><div className="text-[9px] text-muted-foreground">Bounds</div><div className="mt-1 text-xs">{manifest.blocks.length}/{manifest.max_files} files · {manifest.total_token_estimate.toLocaleString()} est. tokens</div></div>
          </div>
          <PathList items={handoff.included_paths} empty="No files entered the bounded handoff." />
        </CardContent>
      </Card>

      <Alert>
        <CheckCircle2 className="size-4" />
        <AlertTitle>Calibrated limitations remain visible</AlertTitle>
        <AlertDescription><ul className="mt-2 list-disc space-y-1 pl-4">{lens.omissions.slice(0, 6).map((item) => <li key={item}>{item}</li>)}</ul></AlertDescription>
      </Alert>
    </div>
  )
}

export function CodeIntelligenceOS({
  runJourney = inspectCodeJourney,
}: {
  readonly runJourney?: (input: CodeJourneyInput) => Promise<AtriumCodeJourneyResponse>
}) {
  const [targetPath, setTargetPath] = useState(DEFAULT_TARGET)
  const [query, setQuery] = useState(DEFAULT_QUERY)
  const [result, setResult] = useState<AtriumCodeJourneyResponse | null>(null)
  // The exact target/query an in-flight or displayed result was submitted
  // with — immutable once inspect() captures it, so a result can never be
  // shown labeled by input text the user typed after submission.
  const [submitted, setSubmitted] = useState<{ readonly target: string; readonly query: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function inspect() {
    const submission = { target: targetPath, query }
    setLoading(true)
    setError(null)
    // Clear any prior result up front — a failed reinspection must never
    // leave a stale (and now unverified) journey on screen.
    setResult(null)
    setSubmitted(submission)
    try {
      setResult(
        await runJourney({
          query: submission.query,
          target_path: submission.target,
          receiver_ref: 'coding-agent:provider-neutral',
        }),
      )
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Code Intelligence could not inspect this journey.'
      setError(sanitizeErrorDetail(message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="atrium-command-center dark min-h-svh bg-background text-foreground">
      <SidebarProvider>
        <KernelNav />
        <SidebarInset className="min-h-svh bg-background">
          <header className="sticky top-0 z-20 flex min-h-[72px] items-center gap-4 border-b bg-background/95 px-5 backdrop-blur md:px-8">
            <SidebarTrigger className="md:hidden" />
            <div className="min-w-0">
              <div className="font-mono text-[8px] font-semibold uppercase tracking-[0.18em] text-brand">ACE / Code Intelligence</div>
              <h1 className="mt-1 text-base font-semibold tracking-tight">Atrium Code lens</h1>
            </div>
            <Badge variant="outline" className="ml-auto rounded-sm font-mono text-[9px]">Read-only · Python static profile</Badge>
          </header>

          <main className="mx-auto w-full max-w-[1500px] space-y-6 p-5 md:p-8">
            <Card className="border-brand/20 bg-brand/[0.025]">
              <CardContent className="p-5 md:p-6">
                <div className="max-w-3xl">
                  <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-brand">Repository journey</div>
                  <h2 className="mt-2 text-xl font-semibold tracking-tight">Understand a change before handing it off</h2>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">Inspect static connections, downstream impact, affected tests, decisions, provenance, uncertainty, and a bounded provider-neutral coding-agent manifest.</p>
                </div>
                <div className="mt-5 grid gap-3 lg:grid-cols-[0.85fr_1.5fr_auto]">
                  <Input
                    aria-label="Target path"
                    value={targetPath}
                    maxLength={MAX_INSPECTION_INPUT_LENGTH}
                    disabled={loading}
                    onChange={(event) => {
                      // Immutable once submitted: an in-flight inspection must never
                      // let an edit relabel the result it is about to return.
                      if (loading) return
                      setTargetPath(event.target.value.slice(0, MAX_INSPECTION_INPUT_LENGTH))
                    }}
                    className="font-mono text-xs"
                  />
                  <Input
                    aria-label="Change question"
                    value={query}
                    maxLength={MAX_INSPECTION_INPUT_LENGTH}
                    disabled={loading}
                    onChange={(event) => {
                      if (loading) return
                      setQuery(event.target.value.slice(0, MAX_INSPECTION_INPUT_LENGTH))
                    }}
                  />
                  <Button type="button" onClick={inspect} disabled={loading || targetPath.trim().length < 3 || query.trim().length < 3}>
                    {loading ? <RefreshCw className="size-4 animate-spin" /> : <SearchCode className="size-4" />}
                    {loading ? 'Inspecting' : 'Inspect'}
                    {!loading && <ArrowRight className="size-4" />}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {error && <Alert variant="destructive"><AlertTriangle className="size-4" /><AlertTitle>Journey unavailable</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
            {result && submitted ? (
              <JourneyResult result={result} submittedTarget={submitted.target} submittedQuery={submitted.query} />
            ) : (
              <div className="rounded-xl border border-dashed px-6 py-16 text-center text-sm text-muted-foreground">Choose a Python target and inspect the repository journey.</div>
            )}
          </main>
        </SidebarInset>
      </SidebarProvider>
    </div>
  )
}
