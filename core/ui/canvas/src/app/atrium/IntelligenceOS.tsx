import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Check,
  CircleAlert,
  CircleMinus,
  RefreshCw,
  Route,
} from 'lucide-react'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import {
  activateIntelligenceBuilderPlan,
  associateIntelligenceBuildSession,
  approveDomainActivationPlan,
  approveIntelligenceBuildPlan,
  bindIntelligenceBuildPlan,
  configuredIntelligenceBuildActivation,
  prepareDomainActivationPlan,
  prepareIntelligenceBuild,
  projectIntelligenceBuild,
  projectIntelligenceBuildResourceState,
  retryIntelligenceBuildSession,
  startIntelligenceBuild,
  type DomainActivationPlanApproveInput,
  type DomainActivationPlanPrepareInput,
  type IntelligenceBuildPlan,
  type IntelligenceBuildPlanBindInput,
  type IntelligenceBuildPlanPrepareInput,
  type IntelligenceBuildResourceStateInput,
  type IntelligenceBuildStartInput,
  type IntelligenceBuilderPlanActivateInput,
} from '@/api/intelligenceBuildsApi'
import { Alert, AlertDescription, AlertTitle } from '@/design/shadcn/ui/alert'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/design/shadcn/ui/sidebar'
import { Skeleton } from '@/design/shadcn/ui/skeleton'

import { KernelNav } from '../ext/defaults/KernelNav'
import { productDisplayName } from './experienceModel'
import { groupResources, kindLabel, type ResourceGroups } from './intelligenceModel'
import {
  DomainHealthRail,
  ExploreIntelligence,
  LivingBriefOverview,
  SurfacePlaceholder,
} from './LivingIntelligence'
import { OnboardingPreview } from './OnboardingPreview'
import { ConsumerContractLedger, DomainPackLedger, PackActivationReader } from './DomainPackConsumers'
import { EntityIntelligenceExplore } from './EntityIntelligence'
import { ATRIUM_ACTION_ICONS } from './atriumIcons'
import {
  onboardingProfilesFromResources,
  onboardingSessionFromResources,
} from './onboardingModel'
import { useInstalledIntelligenceCatalog } from './useInstalledIntelligenceCatalog'
import { useIntelligenceProductCatalog } from './useIntelligenceProductCatalog'
import { useIntelligenceResources } from './useIntelligenceResources'

type Surface = 'overview' | 'explore' | 'build' | 'operate' | 'consumers'

const BuildIcon = ATRIUM_ACTION_ICONS.build
const CurrentIcon = ATRIUM_ACTION_ICONS.current

const LEGACY_SURFACE_REDIRECTS: Readonly<Record<string, string>> = {
  '/atrium/intelligence': '/atrium',
  '/atrium/opportunities': '/atrium',
  '/atrium/agents': '/atrium/build',
  '/atrium/connections': '/atrium/operate',
  '/atrium/strategy': '/atrium/consumers',
}

const SURFACE_COPY: Record<Surface, { title: string; subtitle: string }> = {
  overview: {
    title: 'Overview',
    subtitle: 'The current answer, material movement, unknowns, and attention.',
  },
  explore: {
    title: 'Explore',
    subtitle: 'Ask the governed world, then inspect its evidence and focused relationships.',
  },
  build: {
    title: 'Build',
    subtitle: 'The proposed intelligence model, source plan, readiness, and reviewable changes.',
  },
  operate: {
    title: 'Operate',
    subtitle: 'Coverage, freshness, confidence, conflicts, source health, and maintenance.',
  },
  consumers: {
    title: 'Consumers',
    subtitle: 'The governed interfaces through which people, applications, and agents consume intelligence.',
  },
}

function activeSurface(pathname: string): Surface {
  const part = pathname.split('/')[2]
  if (part === 'explore' || part === 'build' || part === 'operate' || part === 'consumers') {
    return part
  }

  // Keep earlier deep links useful while the visible IA moves to the brief's five surfaces.
  if (part === 'agents') return 'build'
  if (part === 'connections') return 'operate'
  if (part === 'strategy') return 'consumers'
  return 'overview'
}

function RecordStatus({ record }: { readonly record: IntelligenceResourceRecord }) {
  if (record.availability === 'degraded') {
    return <span className="inline-flex items-center gap-1.5 text-warning"><CircleAlert className="size-3" aria-hidden="true" />Degraded</span>
  }
  if (record.availability === 'tombstoned') {
    return <span className="inline-flex items-center gap-1.5 text-destructive"><CircleMinus className="size-3" aria-hidden="true" />Tombstoned</span>
  }
  return <span className="inline-flex items-center gap-1.5 text-foreground/80"><Check className="size-3 text-success" aria-hidden="true" />Available</span>
}

function RecordLedger({
  items,
  empty,
}: {
  readonly items: readonly IntelligenceResourceRecord[]
  readonly empty: string
}) {
  if (items.length === 0) {
    return (
      <div className="border-y border-border px-4 py-9 text-sm text-muted-foreground">
        {empty}
      </div>
    )
  }

  return (
    <ol className="border-y border-border" aria-label="Projected intelligence records">
      {items.map((item) => (
        <li
          key={`${item.reference.resource_id}:${item.reference.revision}`}
          className="grid gap-3 border-t border-border px-0 py-4 first:border-t-0 md:grid-cols-[7rem_minmax(0,1fr)_7rem_9rem] md:items-start md:gap-5"
        >
          <div>
            <Badge variant="outline" className="rounded-sm font-mono text-[7px] uppercase tracking-[0.1em]">
              {kindLabel(item.reference.resource_kind)}
            </Badge>
            <div className="mt-2 font-mono text-[7px] text-muted-foreground">r{item.reference.revision}</div>
          </div>
          <div className="min-w-0">
            <h4 className="text-xs font-medium leading-5 text-foreground">{item.title}</h4>
            <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted-foreground">
              {item.summary ?? 'No summary is projected for this record.'}
            </p>
          </div>
          <div className="font-mono text-[8px] uppercase tracking-[0.08em]">
            <div className="mb-1 text-[7px] text-muted-foreground md:hidden">Availability</div>
            <RecordStatus record={item} />
          </div>
          <div className="text-[9px] leading-4 text-muted-foreground">
            <div className="font-mono text-[7px] uppercase tracking-[0.1em]">Evidence basis</div>
            <div className="mt-1 text-foreground/75">
              {item.provenance.length === 0
                ? 'No upstream record projected'
                : `${item.provenance.length} linked record${item.provenance.length === 1 ? '' : 's'}`}
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}

function BuildSurface({
  groups,
  packs,
  onStart,
}: {
  readonly groups: ResourceGroups
  readonly packs: ReturnType<typeof useIntelligenceProductCatalog>['packs']
  readonly onStart: () => void
}) {
  return (
    <SurfacePlaceholder
      eyebrow="Build · the intelligence model"
      title="Review what ACE maintains."
      description="Tell ACE what you want to understand. ACE proposes the blueprint, exact source roles, watches, readiness, and changes; you review them before activation."
    >
      <div className="grid gap-7 xl:grid-cols-[minmax(0,1fr)_19rem]">
        <section>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
                Current model resources
              </div>
              <h3 className="mt-2 text-lg font-medium tracking-tight">Maintainers and authorized source roles</h3>
            </div>
            <Button type="button" onClick={onStart}>
              Review intelligence build <ArrowRight className="size-4" aria-hidden="true" />
            </Button>
          </div>
          <div className="mt-5 space-y-6">
            <section>
              <div className="mb-2 font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Maintenance model</div>
              <RecordLedger
                items={groups.agents}
                empty="No governed maintainer or watch resources are projected yet."
              />
            </section>
            <section>
              <div className="mb-2 font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Source model</div>
              <RecordLedger
                items={groups.connections}
                empty="No authorized source or connection resources are projected yet."
              />
            </section>
          </div>
        </section>
        <aside className="border-t border-border pt-5 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
          <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
            Review boundary
          </div>
          <ol className="mt-4 space-y-0">
            {[
              'Intent and domain proposal',
              'Blueprint and reviewable changes',
              'Exact source plan and predicted coverage',
              'Permission and readiness',
              'Initialization and first cited Brief',
            ].map((item, index) => (
              <li key={item} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2 border-t border-border py-3 first:border-t-0">
                <span className="font-mono text-[8px] text-muted-foreground">0{index + 1}</span>
                <span className="text-[10px] leading-4 text-foreground/80">{item}</span>
              </li>
            ))}
          </ol>
          <p className="mt-4 border-t border-border pt-4 text-[9px] leading-4 text-muted-foreground">
            Custom Intelligence remains proposal-only Preview in v1. Readiness and coverage appear only when the current contracts project them.
          </p>
        </aside>
      </div>
      <div className="mt-10 border-t border-border pt-8">
        <DomainPackLedger packs={packs} onReviewBuild={onStart} />
      </div>
      <PackActivationReader />
    </SurfacePlaceholder>
  )
}

function OperateSurface({
  page,
  groups,
  items,
}: {
  readonly page: ReturnType<typeof useIntelligenceResources>['page']
  readonly groups: ResourceGroups
  readonly items: readonly IntelligenceResourceRecord[]
}) {
  return (
    <SurfacePlaceholder
      eyebrow="Operate · the trust layer"
      title="Know what the picture can support."
      description="Domain Health separates literal status from unscored quality. Raw traces remain operator detail; customer-visible limits remain visible here and in every Why?"
    >
      <DomainHealthRail page={page} items={items} compact />
      <div className="mt-8 space-y-8">
        <section>
          <div className="mb-3 font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Source records</div>
          <RecordLedger items={groups.connections} empty="No source or connection health records are projected." />
        </section>
        <section>
          <div className="mb-3 font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Maintenance records</div>
          <RecordLedger items={groups.agents} empty="No maintenance resources are projected." />
        </section>
      </div>
    </SurfacePlaceholder>
  )
}

function ConsumersSurface({
  groups,
  catalog,
}: {
  readonly groups: ResourceGroups
  readonly catalog: ReturnType<typeof useIntelligenceProductCatalog>['consumers']
}) {
  return (
    <SurfacePlaceholder
      eyebrow="Consumers · interfaces out"
      title="Intelligence goes where decisions happen."
      description="ACE maintains the intelligence system and exposes governed interfaces out. It does not replace downstream execution engines, create work silently, or imply a second handoff framework."
    >
      <ConsumerContractLedger catalog={catalog} />
      <div className="mt-10 border-t border-border pt-8">
      <div className="grid gap-7 xl:grid-cols-[minmax(0,1fr)_19rem]">
        <section>
          <div className="mb-3 font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
            Current decision and outcome records
          </div>
          <RecordLedger
            items={groups.strategy}
            empty="No consumer-facing decision or outcome record is projected yet."
          />
        </section>
        <aside className="border-t border-border pt-5 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
          <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Downstream interface</div>
          <h3 className="mt-3 text-sm font-medium">Investigation Board</h3>
          <p className="mt-2 text-[10px] leading-5 text-muted-foreground">
            The existing bounded handoff for focused investigation. ACE preserves the cited intelligence record; downstream work remains downstream.
          </p>
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link to="/board">Open Investigation Board</Link>
          </Button>
        </aside>
      </div>
      </div>
    </SurfacePlaceholder>
  )
}

function PageContent({
  surface,
  page,
  groups,
  items,
  productCatalog,
  onStart,
}: {
  readonly surface: Surface
  readonly page: ReturnType<typeof useIntelligenceResources>['page']
  readonly groups: ResourceGroups
  readonly items: readonly IntelligenceResourceRecord[]
  readonly productCatalog: ReturnType<typeof useIntelligenceProductCatalog>
  readonly onStart: () => void
}) {
  if (surface === 'overview') {
    return <LivingBriefOverview page={page} groups={groups} items={items} onStart={onStart} />
  }
  if (surface === 'explore') {
    return (
      <div className="space-y-12">
        <ExploreIntelligence items={items} />
        <section aria-labelledby="focused-entity-intelligence" className="border-t border-border pt-10">
          <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
            Focused entity intelligence
          </div>
          <h2 id="focused-entity-intelligence" className="mt-2 text-2xl font-normal tracking-[-0.03em]">
            Inspect the supported world behind the answer.
          </h2>
          <p className="mt-2 max-w-3xl text-xs leading-5 text-muted-foreground">
            State, movement, time, evidence, unknowns, and exact depth-one lineage appear only when the current resource contracts support them.
          </p>
          <div className="mt-6">
            <EntityIntelligenceExplore items={items} embedded />
          </div>
        </section>
      </div>
    )
  }
  if (surface === 'build') return <BuildSurface groups={groups} packs={productCatalog.packs} onStart={onStart} />
  if (surface === 'operate') return <OperateSurface page={page} groups={groups} items={items} />
  return <ConsumersSurface groups={groups} catalog={productCatalog.consumers} />
}

function LoadingState() {
  return (
    <div role="status" aria-label="Loading intelligence" aria-live="polite">
      <span className="sr-only">ACE is loading the cited intelligence picture.</span>
      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_17rem] xl:gap-0">
        <div className="min-w-0 xl:pr-8">
          <section className="border-b border-border pb-10 pt-4">
            <Skeleton className="h-2.5 w-40 rounded-none" />
            <Skeleton className="mt-7 h-12 w-[min(46rem,88%)] rounded-none md:h-16" />
            <Skeleton className="mt-3 h-12 w-[min(40rem,76%)] rounded-none md:h-16" />
            <Skeleton className="mt-6 h-3 w-[min(34rem,72%)] rounded-none" />
            <Skeleton className="mt-2 h-3 w-[min(27rem,58%)] rounded-none" />
            <Skeleton className="mt-7 h-9 w-36 rounded-full" />
          </section>
          <section className="border-b border-border py-7">
            <Skeleton className="h-2.5 w-32 rounded-none" />
            <Skeleton className="mt-4 h-7 w-64 rounded-none" />
            <div className="mt-6 grid gap-4 border-t border-border pt-5 md:grid-cols-[2rem_minmax(0,1fr)_14rem]">
              <Skeleton className="h-3 w-5 rounded-none" />
              <div>
                <Skeleton className="h-6 w-[min(30rem,90%)] rounded-none" />
                <Skeleton className="mt-3 h-3 w-[min(24rem,75%)] rounded-none" />
              </div>
              <Skeleton className="h-14 w-full rounded-none" />
            </div>
          </section>
          <section className="grid md:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <div key={index} className="border-t border-border py-5 md:border-l md:border-t-0 md:px-5 first:md:border-l-0 first:md:pl-0 last:md:pr-0">
                <Skeleton className="h-2.5 w-24 rounded-none" />
                <Skeleton className="mt-4 h-4 w-36 rounded-none" />
                <Skeleton className="mt-3 h-10 w-full rounded-none" />
              </div>
            ))}
          </section>
        </div>
        <aside aria-hidden="true" className="border-t border-border pt-5 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0">
          <Skeleton className="h-2.5 w-24 rounded-none" />
          <Skeleton className="mt-3 h-5 w-40 rounded-none" />
          <div className="mt-4 space-y-3">
            {[0, 1, 2, 3, 4, 5].map((index) => (
              <div key={index} className="border-t border-border pt-3">
                <Skeleton className="h-2.5 w-full rounded-none" />
                <Skeleton className="mt-2 h-2 w-4/5 rounded-none" />
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  )
}

function UnavailableState() {
  return (
    <section aria-label="Unavailable intelligence" className="border-y border-border py-10 md:py-14">
      <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
        Picture unavailable
      </div>
      <h2 className="mt-3 max-w-2xl text-2xl font-normal tracking-[-0.025em]">
        No intelligence picture is available in this view.
      </h2>
      <p className="mt-3 max-w-2xl text-xs leading-5 text-muted-foreground">
        ACE has not substituted inferred, cached, or presentation-only content. Retry the resource request above to restore the cited picture.
      </p>
    </section>
  )
}

export function IntelligenceOS() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const surface = activeSurface(pathname)
  const copy = SURFACE_COPY[surface]
  const { page, loading, error, refresh } = useIntelligenceResources()
  const installedCatalog = useInstalledIntelligenceCatalog()
  const productCatalog = useIntelligenceProductCatalog()
  const items = page?.items ?? []
  const degradedRecordCount = items.filter((item) => item.availability === 'degraded').length
  const groups = useMemo(() => groupResources(items), [items])
  const productName = productDisplayName(page?.product_id)
  const [onboardingOpen, setOnboardingOpen] = useState(false)
  const onboardingTrigger = useRef<HTMLElement | null>(null)
  const [sidebarDefaultOpen] = useState(() => (
    typeof window === 'undefined'
    || typeof window.matchMedia !== 'function'
    || window.matchMedia('(min-width: 1024px)').matches
  ))
  const onboardingPresented = useRef(false)
  const onboardingProfiles = useMemo(
    () => onboardingProfilesFromResources(
      items,
      installedCatalog.map((item) => item.profile),
    ),
    [installedCatalog, items],
  )
  const onboardingSession = useMemo(() => onboardingSessionFromResources(items), [items])
  const activationSetup = useMemo(() => configuredIntelligenceBuildActivation(), [])

  useEffect(() => {
    const canonicalPath = LEGACY_SURFACE_REDIRECTS[pathname]
    if (canonicalPath !== undefined) navigate(canonicalPath, { replace: true })
  }, [navigate, pathname])

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [surface])

  useEffect(() => {
    document.title = `${copy.title} — ACE`
  }, [copy.title])

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
    requestAnimationFrame(() => document.getElementById('latest-brief')?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    }))
  }

  async function prepareIntelligence(request: IntelligenceBuildPlanPrepareInput) {
    return prepareIntelligenceBuild(request)
  }

  async function projectIntelligence(plan: IntelligenceBuildPlan) {
    return projectIntelligenceBuild(plan)
  }

  async function bindIntelligence(request: IntelligenceBuildPlanBindInput) {
    return bindIntelligenceBuildPlan(request)
  }

  async function approveIntelligence(boundPlan: Parameters<typeof approveIntelligenceBuildPlan>[0]) {
    return approveIntelligenceBuildPlan(boundPlan)
  }

  async function associateBuilderSession(
    boundPlan: Parameters<typeof associateIntelligenceBuildSession>[0],
    approvalReceiptRef: Parameters<typeof associateIntelligenceBuildSession>[1],
  ) {
    return associateIntelligenceBuildSession(boundPlan, approvalReceiptRef)
  }

  async function startIntelligence(request: IntelligenceBuildStartInput) {
    return startIntelligenceBuild(request)
  }

  async function projectIntelligenceResourceState(input: IntelligenceBuildResourceStateInput) {
    return projectIntelligenceBuildResourceState(input)
  }

  async function prepareIntelligenceActivationPlan(input: DomainActivationPlanPrepareInput) {
    return prepareDomainActivationPlan(input)
  }

  async function approveIntelligenceActivationPlan(input: DomainActivationPlanApproveInput) {
    return approveDomainActivationPlan(input)
  }

  async function activateIntelligenceBuilderActivationPlan(input: IntelligenceBuilderPlanActivateInput) {
    return activateIntelligenceBuilderPlan(input)
  }

  async function retryIntelligence(current: Readonly<Record<string, unknown>>) {
    return retryIntelligenceBuildSession(current)
  }

  function openOnboarding() {
    const activeElement = document.activeElement
    onboardingTrigger.current = activeElement instanceof HTMLElement ? activeElement : null
    setOnboardingOpen(true)
  }

  function changeOnboardingOpen(nextOpen: boolean) {
    setOnboardingOpen(nextOpen)
    if (nextOpen) return
    const trigger = onboardingTrigger.current
    onboardingTrigger.current = null
    if (trigger?.isConnected) requestAnimationFrame(() => trigger.focus())
  }

  return (
    <div className="atrium-command-center dark min-h-svh bg-background text-foreground">
      <a
        href="#atrium-main"
        className="fixed left-3 top-3 z-50 -translate-y-20 bg-foreground px-3 py-2 text-xs font-semibold text-background transition-transform focus:translate-y-0 focus:outline-none focus:ring-2 focus:ring-brand motion-reduce:transition-none"
      >
        Skip to intelligence
      </a>
      <SidebarProvider defaultOpen={sidebarDefaultOpen}>
        <KernelNav productName={productName} />
        <SidebarInset className="min-h-svh bg-background">
          <header className="sticky top-0 z-20 flex min-h-16 items-center gap-4 border-b bg-background/95 px-5 backdrop-blur md:px-8">
            <SidebarTrigger className="lg:hidden" />
            <div className="min-w-0">
              <div className="truncate font-mono text-[8px] uppercase tracking-[0.18em] text-muted-foreground">
                ACE / {productName}
              </div>
              <div className="mt-1 flex min-w-0 items-baseline gap-3">
                <h1 className="truncate text-sm font-medium tracking-tight">{copy.title}</h1>
                <p className="hidden truncate text-[10px] text-muted-foreground lg:block">{copy.subtitle}</p>
              </div>
            </div>
            <div className="ml-auto flex items-center gap-1.5">
              {surface !== 'explore' && (
                <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
                  <Link to="/atrium/explore">Ask ACE</Link>
                </Button>
              )}
              <Button type="button" variant="outline" size="sm" onClick={openOnboarding}>
                <BuildIcon className="size-3.5" aria-hidden="true" />
                <span className="hidden sm:inline">{onboardingSession === null ? 'Build' : 'Review build'}</span>
              </Button>
              {page !== null && (
                <Badge
                  variant="outline"
                  role="status"
                  aria-live="polite"
                  className="hidden rounded-sm border-border bg-card font-mono text-[8px] font-normal sm:inline-flex"
                >
                  {error !== null
                    ? <CircleAlert className="mr-1 size-3 text-warning" aria-hidden="true" />
                    : page.state === 'degraded'
                    ? <CircleAlert className="mr-1 size-3 text-warning" aria-hidden="true" />
                    : <CurrentIcon className="mr-1 size-3 text-success" aria-hidden="true" />}
                  {error !== null
                    ? 'Last loaded picture'
                    : page.state === 'degraded'
                      ? 'Partial picture'
                      : 'Picture current'}
                </Badge>
              )}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={refresh}
                aria-label={loading ? 'Refreshing intelligence' : 'Refresh intelligence'}
                aria-busy={loading}
              >
                <RefreshCw className={loading ? 'size-4 animate-spin motion-reduce:animate-none' : 'size-4'} aria-hidden="true" />
              </Button>
            </div>
          </header>

          <main id="atrium-main" tabIndex={-1} className="mx-auto w-full max-w-[1560px] p-5 outline-none md:p-8">
            {error !== null && (
              <Alert variant="destructive" className="mb-6">
                <CircleAlert className="size-4" aria-hidden="true" />
                <AlertTitle>
                  {page === null
                    ? 'ACE could not open this intelligence view'
                    : 'ACE could not refresh this intelligence view'}
                </AlertTitle>
                <AlertDescription className="mt-1 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <span>
                    {error.message}
                    {page !== null && ' The last loaded cited picture remains visible.'}
                  </span>
                  <Button type="button" variant="outline" size="sm" onClick={refresh}>Try again</Button>
                </AlertDescription>
              </Alert>
            )}

            {page?.state === 'degraded' && (
              <Alert className="mb-6 border-warning/45 bg-warning/[0.04]">
                <CircleAlert className="size-4 text-warning" aria-hidden="true" />
                <AlertTitle>Some evidence still needs review</AlertTitle>
                <AlertDescription>
                  <span className="block">Available intelligence and citations remain visible. Open Operate for the dimensions the current contracts can and cannot support.</span>
                  <span className="mt-1 block font-mono text-[9px] uppercase tracking-[0.1em]">
                    {degradedRecordCount > 0
                      ? `${degradedRecordCount} cited record${degradedRecordCount === 1 ? ' is' : 's are'} marked degraded.`
                      : 'The page reports a degraded state without a degraded record projection.'}
                  </span>
                </AlertDescription>
              </Alert>
            )}

            {error !== null && page === null ? (
              <UnavailableState />
            ) : loading && page === null ? (
              <LoadingState />
            ) : (
              <PageContent
                surface={surface}
                page={page}
                groups={groups}
                items={items}
                productCatalog={productCatalog}
                onStart={openOnboarding}
              />
            )}
          </main>

          <footer className="mx-auto flex w-full max-w-[1560px] flex-wrap items-center gap-2 px-5 pb-6 text-[9px] text-muted-foreground md:px-8">
            <Route className="size-3" aria-hidden="true" />
            <span>One maintained intelligence picture</span>
            <span>·</span>
            <span>{loading && page === null ? 'Loading cited records' : `${items.length} cited records`}</span>
            <span>·</span>
            <span>Sources, limits, and history preserved</span>
          </footer>
          <OnboardingPreview
            open={onboardingOpen}
            onOpenChange={changeOnboardingOpen}
            profiles={onboardingProfiles}
            session={onboardingSession}
            onPrepareBuild={prepareIntelligence}
            onProjectBuild={projectIntelligence}
            activationSetup={activationSetup}
            onBindBuild={bindIntelligence}
            onApproveBuild={approveIntelligence}
            onAssociateBuilderSession={associateBuilderSession}
            onPrepareActivationPlan={prepareIntelligenceActivationPlan}
            onApproveActivationPlan={approveIntelligenceActivationPlan}
            onActivatePlan={activateIntelligenceBuilderActivationPlan}
            onStartBuild={startIntelligence}
            onProjectResourceState={projectIntelligenceResourceState}
            onRetryBuild={retryIntelligence}
            onBuildStarted={() => refresh()}
            onOpenBrief={openFirstBrief}
          />
        </SidebarInset>
      </SidebarProvider>
    </div>
  )
}
