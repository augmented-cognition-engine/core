import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Activity,
  ArrowRight,
  Bot,
  BrainCircuit,
  CircleAlert,
  Clock3,
  Crosshair,
  Layers3,
  Network,
  Radio,
  RefreshCw,
  Route,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  TimerReset,
} from 'lucide-react'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import { startIntelligenceBuild, type IntelligenceBuildStartInput } from '@/api/intelligenceBuildsApi'
import { Alert, AlertDescription, AlertTitle } from '@/design/shadcn/ui/alert'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/design/shadcn/ui/sidebar'
import { Skeleton } from '@/design/shadcn/ui/skeleton'

import { KernelNav } from '../ext/defaults/KernelNav'
import { AskAce } from './AskAce'
import { OnboardingPreview } from './OnboardingPreview'
import {
  onboardingProfilesFromResources,
  onboardingSessionFromResources,
} from './onboardingModel'
import { pageFreshness, productDisplayName } from './experienceModel'
import {
  groupResources,
  type ResourceGroups,
} from './intelligenceModel'
import { ResourceCard } from './ResourceCard'
import { useIntelligenceResources } from './useIntelligenceResources'
import { useInstalledIntelligenceCatalog } from './useInstalledIntelligenceCatalog'

type Surface = 'intelligence' | 'opportunities' | 'agents' | 'connections' | 'strategy'

const SURFACE_COPY: Record<Surface, { title: string; subtitle: string }> = {
  intelligence: {
    title: 'Intelligence',
    subtitle: 'What changed, why it matters, and the evidence behind it.',
  },
  opportunities: {
    title: 'Opportunities',
    subtitle: 'Evidence-backed openings that may warrant a decision, response, or new watch.',
  },
  agents: {
    title: 'Agents',
    subtitle: 'The governed team mapping, watching, briefing, and learning.',
  },
  connections: {
    title: 'Connections',
    subtitle: 'Authorized sources and the live evidence entering ACE.',
  },
  strategy: {
    title: 'Strategy',
    subtitle: 'Decisions, actions, outcomes, and the feedback closing the loop.',
  },
}

function activeSurface(pathname: string): Surface {
  const part = pathname.split('/')[2]
  if (part === 'opportunities' || part === 'agents' || part === 'connections' || part === 'strategy') {
    return part
  }
  return 'intelligence'
}

function EmptyBuilder({ onStart }: { readonly onStart: () => void }) {
  const steps = [
    {
      title: 'Tell ACE what matters',
      detail: 'Choose the decision or landscape you need to stay ahead of.',
      icon: Network,
    },
    {
      title: 'Review the recommendation',
      detail: 'ACE proposes evidence, concepts, watches, and cadence for review.',
      icon: BrainCircuit,
    },
    {
      title: 'Open the first Brief',
      detail: 'Watch the system assemble, then land in a populated command center.',
      icon: Activity,
    },
  ]

  return (
    <Card className="border-dashed">
      <CardContent className="p-6 md:p-8">
        <div className="max-w-xl">
          <Badge variant="secondary" className="mb-3">Start here</Badge>
          <h2 className="text-xl font-semibold tracking-tight">What do you need to stay ahead of?</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            Tell ACE the outcome. It recommends the sources, concepts, watches, and briefing system; you review the plan and the first cited Brief assembles itself.
          </p>
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {steps.map((step, index) => (
            <div
              key={step.title}
              className="rounded-xl border bg-card p-4"
            >
              <div className="flex items-center gap-2">
                <div className="flex size-8 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <step.icon className="size-4" />
                </div>
                <span className="font-mono text-[10px] text-muted-foreground">0{index + 1}</span>
                {index < 2 ? <ArrowRight className="ml-auto size-3.5 text-muted-foreground" /> : <ShieldCheck className="ml-auto size-3.5 text-brand" />}
              </div>
              <div className="mt-4 text-sm font-semibold">{step.title}</div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{step.detail}</p>
            </div>
          ))}
        </div>
        <Button type="button" className="mt-5" onClick={onStart}>Build my intelligence <ArrowRight className="size-4" /></Button>
      </CardContent>
    </Card>
  )
}

function ResourceGrid({
  items,
  empty,
  single = false,
  compact = false,
}: {
  readonly items: readonly IntelligenceResourceRecord[]
  readonly empty: string
  readonly single?: boolean
  readonly compact?: boolean
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed px-5 py-10 text-center text-sm text-muted-foreground">
        {empty}
      </div>
    )
  }
  return (
    <div className={single ? 'grid gap-3' : 'grid gap-3 xl:grid-cols-2'}>
      {items.map((item) => (
        <ResourceCard key={`${item.reference.resource_id}:${item.reference.revision}`} record={item} compact={compact} />
      ))}
    </div>
  )
}

function BriefingHome({ groups, all, onStart }: { readonly groups: ResourceGroups; readonly all: IntelligenceResourceRecord[]; readonly onStart: () => void }) {
  const briefs = groups.intelligence.filter((item) => item.reference.resource_kind === 'brief')
  const latestBrief = briefs[0]
  const stream = groups.intelligence
    .filter((item) => item !== latestBrief && ['signal', 'shift', 'brief'].includes(item.reference.resource_kind))
    .slice(0, 6)

  return (
    <div className="space-y-7">
      <AskAce items={all} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(20rem,0.45fr)]">
        <section id="latest-brief" className="scroll-mt-24 space-y-3">
          <div className="flex items-end justify-between gap-3">
            <div>
              <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.17em] text-brand">Latest briefing</div>
              <h2 className="mt-1 text-lg font-semibold tracking-tight">The situation now</h2>
            </div>
            <Badge variant="outline" className="rounded-sm font-mono text-[9px]">{briefs.length} current</Badge>
          </div>
          {latestBrief === undefined ? (
            <EmptyBuilder onStart={onStart} />
          ) : (
            <ResourceCard record={latestBrief} featured />
          )}
        </section>

        <aside className="space-y-3">
          <div>
            <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.17em] text-muted-foreground">Attention</div>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">What needs a look</h2>
          </div>
          <ResourceGrid items={groups.attention.slice(0, 4)} empty="Nothing needs attention right now." single compact />
        </aside>
      </div>

      <section className="space-y-3 border-t pt-6">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.17em] text-muted-foreground">Live intelligence</div>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">What is moving</h2>
          </div>
          <Badge variant="outline" className="rounded-sm font-mono text-[9px]">{stream.length} updates</Badge>
        </div>
        <ResourceGrid items={stream} empty="No additional signals or shifts have arrived yet." compact />
      </section>
    </div>
  )
}

function CoverageStrip({ groups, freshness }: { readonly groups: ResourceGroups; readonly freshness: string }) {
  const sources = groups.connections.filter((item) => item.reference.resource_kind === 'source').length
  const monitors = groups.agents.filter((item) => item.reference.resource_kind === 'monitor').length
  const openCases = groups.opportunities.filter((item) => item.reference.resource_kind === 'case').length
  const entries = [
    { icon: Radio, label: 'Sources', value: `${sources} admitted` },
    { icon: Activity, label: 'Watches', value: `${monitors} active` },
    { icon: Layers3, label: 'Decision openings', value: `${openCases} ready` },
    { icon: Clock3, label: 'Freshness', value: freshness },
  ]

  return (
    <div className="mb-7 grid overflow-hidden rounded-lg border bg-card md:grid-cols-4" aria-label="Intelligence coverage">
      {entries.map((entry, index) => (
        <div key={entry.label} className={index === 0 ? 'flex items-center gap-3 px-4 py-3.5' : 'flex items-center gap-3 border-t px-4 py-3.5 md:border-l md:border-t-0'}>
          <entry.icon className="size-3.5 shrink-0 text-brand" />
          <div className="min-w-0">
            <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">{entry.label}</div>
            <div className="mt-0.5 truncate text-xs font-medium text-foreground/90">{entry.value}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

function ConnectionsView({ groups }: { readonly groups: ResourceGroups }) {
  const connections = groups.connections.filter((item) => item.reference.resource_kind === 'connection')
  const sources = groups.connections.filter((item) => item.reference.resource_kind === 'source')
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="Live connections" value={connections.length} detail="authorized pathways" />
        <Metric label="Sources" value={sources.length} detail="admitted evidence origins" />
        <Metric label="Health" value="Pending" detail="failure telemetry is not yet projected" warning />
      </div>
      <ResourceGrid items={groups.connections} empty="No authorized sources have been admitted yet." />
    </div>
  )
}

function AgentsView({ groups }: { readonly groups: ResourceGroups }) {
  const active = groups.agents.filter((item) => item.reference.resource_kind === 'agent')
  const monitors = groups.agents.filter((item) => item.reference.resource_kind === 'monitor')
  return (
    <div className="space-y-6">
      <Card className="bg-muted/25">
        <CardContent className="grid gap-4 p-5 md:grid-cols-3">
          <AgentRole title="Source Scout" detail="Connects and validates permitted evidence." state={active.length > 0 ? 'Ready' : 'Waiting'} />
          <AgentRole title="Ontology Guide" detail="Maps entities and relationships with you." state={active.length > 0 ? 'Ready' : 'Waiting'} />
          <AgentRole title="Intelligence Analyst" detail="Watches, briefs, and preserves citations." state={monitors.length > 0 ? 'Watching' : 'Waiting'} />
        </CardContent>
      </Card>
      <ResourceGrid items={groups.agents} empty="No governed agents or monitors are active yet." />
    </div>
  )
}

function OpportunityStage({
  icon: Icon,
  title,
  detail,
}: {
  readonly icon: typeof Crosshair
  readonly title: string
  readonly detail: string
}) {
  return (
    <div className="flex gap-3 rounded-lg border bg-background p-4">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-brand/20 bg-brand/10 text-brand">
        <Icon className="size-4" />
      </div>
      <div>
        <div className="text-sm font-semibold">{title}</div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{detail}</p>
      </div>
    </div>
  )
}

function OpportunitySection({
  eyebrow,
  title,
  detail,
  items,
  empty,
}: {
  readonly eyebrow: string
  readonly title: string
  readonly detail: string
  readonly items: readonly IntelligenceResourceRecord[]
  readonly empty: string
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.17em] text-brand">{eyebrow}</div>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">{title}</h2>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted-foreground">{detail}</p>
        </div>
        <Badge variant="outline" className="rounded-sm font-mono text-[9px]">{items.length} current</Badge>
      </div>
      <ResourceGrid items={items} empty={empty} compact />
    </section>
  )
}

function OpportunitiesView({ groups }: { readonly groups: ResourceGroups }) {
  const decisionOpenings = groups.opportunities.filter((item) => item.reference.resource_kind === 'case')
  const emergingOpenings = groups.opportunities.filter((item) => item.reference.resource_kind === 'shift')
  const earlySignals = groups.opportunities.filter((item) => item.reference.resource_kind === 'signal')

  return (
    <div className="space-y-7">
      <Card className="border-brand/20 bg-brand/[0.04]">
        <CardContent className="p-5 md:p-6">
          <div className="max-w-3xl">
            <Badge variant="secondary" className="mb-3 border border-brand/15 bg-brand/10 text-brand">Decision openings</Badge>
            <h2 className="text-xl font-semibold tracking-tight">An Opportunity is intelligence awaiting a decision.</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              ACE promotes a signal or shift when the evidence suggests a favorable or avoidable window. It is not a lead, a task, or autonomous Work; it remains a proposal until a person investigates, accepts, dismisses, or turns it into Strategy.
            </p>
          </div>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <OpportunityStage icon={Radio} title="Signal" detail="A relevant observation worth tracking, but not yet a decision opening." />
            <OpportunityStage icon={TimerReset} title="Shift" detail="A material delta from the baseline that may create a time-sensitive opening." />
            <OpportunityStage icon={SearchCheck} title="Case" detail="A bounded, evidence-backed question ready for investigation or decision." />
          </div>
        </CardContent>
      </Card>

      <OpportunitySection
        eyebrow="Ready to investigate"
        title="Decision openings"
        detail="Cases have a bounded question and preserved evidence. Review the record before turning one into Strategy or downstream Work."
        items={decisionOpenings}
        empty="No evidence-backed decision openings are ready yet."
      />
      <OpportunitySection
        eyebrow="Developing"
        title="Emerging openings"
        detail="Material shifts may become Opportunities once their decision window, impact, and evidence are clear."
        items={emergingOpenings}
        empty="No material shifts are currently developing into Opportunities."
      />
      {earlySignals.length > 0 && (
        <OpportunitySection
          eyebrow="Watchlist"
          title="Early signals"
          detail="These observations are relevant, but ACE has not yet established a material shift or bounded decision question."
          items={earlySignals}
          empty="No early signals are being watched."
        />
      )}
    </div>
  )
}

function Metric({ label, value, detail, warning = false }: { readonly label: string; readonly value: number | string; readonly detail: string; readonly warning?: boolean }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="mt-2 flex items-center gap-2">
          <span className="text-2xl font-semibold tracking-tight">{value}</span>
          {warning && <CircleAlert className="size-4 text-warning" />}
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">{detail}</div>
      </CardContent>
    </Card>
  )
}

function AgentRole({ title, detail, state }: { readonly title: string; readonly detail: string; readonly state: string }) {
  return (
    <div className="flex gap-3 rounded-xl border bg-background p-4">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
        <Bot className="size-4" />
      </div>
      <div>
        <div className="flex items-center gap-2 text-sm font-semibold">
          {title}
          <Badge variant="secondary" className="font-mono text-[9px]">{state}</Badge>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{detail}</p>
      </div>
    </div>
  )
}

function PageContent({ surface, groups, all, onStart }: { readonly surface: Surface; readonly groups: ResourceGroups; readonly all: IntelligenceResourceRecord[]; readonly onStart: () => void }) {
  if (surface === 'intelligence') return <BriefingHome groups={groups} all={all} onStart={onStart} />
  if (surface === 'connections') return <ConnectionsView groups={groups} />
  if (surface === 'agents') return <AgentsView groups={groups} />
  if (surface === 'opportunities') return <OpportunitiesView groups={groups} />
  return <ResourceGrid items={groups.strategy} empty="No decisions or outcomes have entered the strategy loop yet." />
}

function LoadingState() {
  return (
    <div className="space-y-4" aria-label="Loading intelligence">
      <Skeleton className="h-40 w-full rounded-xl" />
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-40 rounded-xl" />
        <Skeleton className="h-40 rounded-xl" />
      </div>
    </div>
  )
}

export function IntelligenceOS() {
  const { pathname } = useLocation()
  const surface = activeSurface(pathname)
  const copy = SURFACE_COPY[surface]
  const { page, loading, error, refresh, adoptPage } = useIntelligenceResources()
  const installedCatalog = useInstalledIntelligenceCatalog()
  const groups = useMemo(() => groupResources(page?.items ?? []), [page?.items])
  const productName = productDisplayName(page?.product_id)
  const freshness = pageFreshness(page)
  const [onboardingOpen, setOnboardingOpen] = useState(false)
  const onboardingPresented = useRef(false)
  const onboardingProfiles = useMemo(
    () => onboardingProfilesFromResources(
      page?.items ?? [],
      installedCatalog.map((item) => item.profile),
    ),
    [installedCatalog, page?.items],
  )
  const onboardingSession = useMemo(() => onboardingSessionFromResources(page?.items ?? []), [page?.items])

  useEffect(() => {
    if (
      onboardingPresented.current
      || loading
      || error !== null
      || installedCatalog.length === 0
      || onboardingSession !== null
      || groups.intelligence.length > 0
    ) return
    onboardingPresented.current = true
    setOnboardingOpen(true)
  }, [error, groups.intelligence.length, installedCatalog.length, loading, onboardingSession])

  function openFirstBrief() {
    requestAnimationFrame(() => document.getElementById('latest-brief')?.scrollIntoView({ behavior: 'smooth' }))
  }

  async function buildIntelligence(request: IntelligenceBuildStartInput) {
    const result = await startIntelligenceBuild(request)
    adoptPage(result.resource_page)
  }

  return (
    <div className="atrium-command-center dark min-h-svh bg-background text-foreground">
      <SidebarProvider>
        <KernelNav />
        <SidebarInset className="min-h-svh bg-background">
        <header className="sticky top-0 z-20 flex min-h-[72px] items-center gap-4 border-b bg-background/95 px-5 backdrop-blur md:px-8">
          <SidebarTrigger className="md:hidden" />
          <div className="min-w-0">
            <div className="truncate font-mono text-[8px] font-semibold uppercase tracking-[0.18em] text-brand">
              ACE / {productName}
            </div>
            <div className="mt-1 flex min-w-0 items-baseline gap-3">
              <h1 className="truncate text-base font-semibold tracking-tight">{copy.title}</h1>
              <p className="hidden truncate text-[11px] text-muted-foreground lg:block">{copy.subtitle}</p>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setOnboardingOpen(true)}>
              <Sparkles className="size-3.5" />
              <span className="hidden sm:inline">{onboardingSession === null ? 'Build intelligence' : 'View build'}</span>
            </Button>
            {page !== null && (
              <Badge variant={page.state === 'degraded' ? 'outline' : 'secondary'} className="hidden rounded-sm border border-border/70 bg-card font-mono text-[9px] sm:inline-flex">
                {page.state === 'degraded' ? <CircleAlert className="mr-1 size-3 text-warning" /> : <ShieldCheck className="mr-1 size-3 text-brand" />}
                {page.state === 'degraded' ? 'Partial picture' : 'Picture current'}
              </Badge>
            )}
            <Button type="button" variant="ghost" size="icon" onClick={refresh} aria-label="Refresh intelligence">
              <RefreshCw className={loading ? 'size-4 animate-spin' : 'size-4'} />
            </Button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1500px] p-5 md:p-8">
          {error !== null && (
            <Alert variant="destructive" className="mb-6">
              <CircleAlert className="size-4" />
              <AlertTitle>ACE could not open this intelligence view</AlertTitle>
              <AlertDescription className="mt-1 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <span>{error.message}</span>
                <Button type="button" variant="outline" size="sm" onClick={refresh}>Try again</Button>
              </AlertDescription>
            </Alert>
          )}

          {page?.state === 'degraded' && (
            <Alert className="mb-6 border-warning/45 bg-warning/5">
              <CircleAlert className="size-4" />
              <AlertTitle>Some evidence still needs review</AlertTitle>
              <AlertDescription>
                Some source-health, confidence, conflict, and revision checks are incomplete. Available intelligence and citations remain visible.
              </AlertDescription>
            </Alert>
          )}

          {loading && page === null ? (
            <LoadingState />
          ) : (
            <>
              <CoverageStrip groups={groups} freshness={freshness} />
              <PageContent surface={surface} groups={groups} all={page?.items ?? []} onStart={() => setOnboardingOpen(true)} />
            </>
          )}
        </main>

        <footer className="mx-auto flex w-full max-w-[1500px] flex-wrap items-center gap-2 px-5 pb-6 text-[10px] text-muted-foreground md:px-8">
          <Route className="size-3" />
          <span>One current intelligence picture</span>
          <span>·</span>
          <span>{page?.items.length ?? 0} cited records</span>
          <span>·</span>
          <span>Sources and history preserved</span>
        </footer>
        <OnboardingPreview
          open={onboardingOpen}
          onOpenChange={setOnboardingOpen}
          profiles={onboardingProfiles}
          session={onboardingSession}
          onStartBuild={buildIntelligence}
          onOpenBrief={openFirstBrief}
        />
        </SidebarInset>
      </SidebarProvider>
    </div>
  )
}
