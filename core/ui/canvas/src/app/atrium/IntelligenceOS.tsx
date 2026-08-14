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
import {
  prepareIntelligenceBuild,
  type IntelligenceBuildPlanPrepareInput,
} from '@/api/intelligenceBuildsApi'
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
import { briefRevisionStory, pageFreshness, productDisplayName } from './experienceModel'
import {
  groupResources,
  type ResourceGroups,
} from './intelligenceModel'
import { ResourceCard } from './ResourceCard'
import { useIntelligenceResources } from './useIntelligenceResources'
import { useInstalledIntelligenceCatalog } from './useInstalledIntelligenceCatalog'

type Surface = 'intelligence' | 'opportunities' | 'agents' | 'connections' | 'strategy'

const COGNITIVE_NODES = [
  [116, 213], [130, 166], [153, 126], [191, 96], [237, 83], [282, 86],
  [329, 101], [369, 128], [399, 164], [416, 207], [408, 249], [382, 286],
  [344, 313], [298, 327], [250, 325], [204, 312], [165, 285], [136, 251],
  [170, 173], [207, 142], [251, 132], [297, 137], [340, 157], [371, 197],
  [356, 238], [322, 275], [276, 286], [230, 277], [193, 247], [183, 210],
  [224, 189], [270, 173], [315, 193], [314, 234], [271, 248], [229, 232],
] as const

const COGNITIVE_FACETS = [
  [0, 1, 18], [1, 2, 18], [2, 3, 19], [2, 19, 18], [3, 4, 19], [4, 20, 19],
  [4, 5, 20], [5, 21, 20], [5, 6, 21], [6, 22, 21], [6, 7, 22], [7, 8, 22],
  [8, 23, 22], [8, 9, 23], [9, 10, 23], [10, 24, 23], [10, 11, 24],
  [11, 12, 25], [11, 25, 24], [12, 13, 25], [13, 26, 25], [13, 14, 26],
  [14, 27, 26], [14, 15, 27], [15, 16, 27], [16, 28, 27], [16, 17, 28],
  [17, 0, 29], [0, 18, 29], [18, 19, 30], [18, 30, 29], [19, 20, 30],
  [20, 31, 30], [20, 21, 31], [21, 22, 32], [21, 32, 31], [22, 23, 32],
  [23, 24, 33], [23, 33, 32], [24, 25, 33], [25, 26, 34], [25, 34, 33],
  [26, 27, 34], [27, 28, 35], [27, 35, 34], [28, 29, 35], [29, 30, 35],
  [30, 31, 34], [30, 34, 35], [31, 32, 33], [31, 33, 34],
] as const

function cognitiveZone(x: number): 'live' | 'evidence' | 'authority' {
  if (x < 220) return 'live'
  if (x < 315) return 'evidence'
  return 'authority'
}

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
      tone: 'text-live border-live/20 bg-live/[0.06]',
    },
    {
      title: 'Review the recommendation',
      detail: 'ACE proposes evidence, concepts, watches, and cadence for review.',
      icon: BrainCircuit,
      tone: 'text-evidence border-evidence/20 bg-evidence/[0.06]',
    },
    {
      title: 'Open the first Brief',
      detail: 'Watch the system assemble, then land in a populated command center.',
      icon: Activity,
      tone: 'text-foreground/70 border-border bg-muted/60',
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
                <div className={`flex size-8 items-center justify-center rounded-lg border ${step.tone}`}>
                  <step.icon className="size-4" />
                </div>
                <span className="font-mono text-[10px] text-muted-foreground">0{index + 1}</span>
                {index < 2 ? <ArrowRight className="ml-auto size-3.5 text-muted-foreground" /> : <ShieldCheck className="ml-auto size-3.5 text-live" />}
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

function CognitiveField({
  sourceCount,
  movementCount,
  evidenceCount,
  decisionCount,
  active,
}: {
  readonly sourceCount: number
  readonly movementCount: number
  readonly evidenceCount: number
  readonly decisionCount: number
  readonly active: boolean
}) {
  return (
    <div
      className={`atrium-cognitive-field relative hidden min-h-[470px] overflow-hidden lg:block ${active ? 'is-current' : ''}`}
      aria-label="ACE cognitive field"
    >
      <div className="absolute inset-x-8 top-7 z-10 flex items-center justify-between font-mono text-[8px] uppercase tracking-[0.18em] text-white/35">
        <span>Cognitive field</span>
        <span className="flex items-center gap-2">
          <span className="atrium-field-heartbeat size-1 rounded-full bg-live" />
          {active ? 'Current picture' : 'Awaiting intelligence'}
        </span>
      </div>

      <svg className="absolute inset-0 size-full" viewBox="0 0 520 430" fill="none" aria-hidden="true">
        <defs>
          <radialGradient id="ace-cognition-core">
            <stop stopColor="var(--foreground)" stopOpacity="0.86" />
            <stop offset="0.24" stopColor="var(--evidence)" stopOpacity="0.42" />
            <stop offset="0.68" stopColor="var(--brand)" stopOpacity="0.12" />
            <stop offset="1" stopColor="var(--brand)" stopOpacity="0" />
          </radialGradient>
          <filter id="ace-cognition-soften" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="9" />
          </filter>
        </defs>

        <ellipse className="atrium-cognitive-aura" cx="270" cy="210" rx="178" ry="142" fill="url(#ace-cognition-core)" filter="url(#ace-cognition-soften)" />

        <g className="atrium-cognitive-facets">
          {COGNITIVE_FACETS.map((facet, index) => {
            const points = facet.map((nodeIndex) => COGNITIVE_NODES[nodeIndex])
            const averageX = points.reduce((sum, point) => sum + point[0], 0) / points.length
            return (
              <polygon
                key={facet.join('-')}
                points={points.map((point) => point.join(',')).join(' ')}
                data-zone={cognitiveZone(averageX)}
                style={{ animationDelay: `${(index % 9) * -0.47}s` }}
              />
            )
          })}
        </g>

        <path className="atrium-cognitive-spine" d="M258 86C247 133 277 160 263 204C249 247 280 278 270 326" />
        <circle className="atrium-cognitive-core" cx="270" cy="211" r="31" />
        <circle cx="270" cy="211" r="3.5" fill="var(--foreground)" />

        <g className="atrium-cognitive-nodes">
          {COGNITIVE_NODES.map(([x, y], index) => (
            <circle
              key={`${x}-${y}`}
              cx={x}
              cy={y}
              r={index > 29 ? 2.25 : 1.6}
              data-zone={cognitiveZone(x)}
              style={{ animationDelay: `${(index % 12) * -0.38}s` }}
            />
          ))}
        </g>

        <g className="atrium-field-particles">
          <circle cx="76" cy="106" r="1" /><circle cx="92" cy="304" r="1.2" />
          <circle cx="447" cy="121" r="1" /><circle cx="462" cy="278" r="1.2" />
          <circle cx="101" cy="220" r="0.8" /><circle cx="435" cy="211" r="0.8" />
        </g>
      </svg>

      <div className="absolute bottom-8 left-8 right-8 z-10 grid grid-cols-4 gap-4 border-t border-white/[0.08] pt-4">
        <div>
          <div className="font-mono text-[8px] uppercase tracking-[0.15em] text-white/35">Sources</div>
          <div className="mt-1 font-mono text-[11px] text-live">{sourceCount} admitted</div>
        </div>
        <div>
          <div className="font-mono text-[8px] uppercase tracking-[0.15em] text-white/35">Movement</div>
          <div className="mt-1 font-mono text-[11px] text-live">{movementCount} detected</div>
        </div>
        <div>
          <div className="font-mono text-[8px] uppercase tracking-[0.15em] text-white/35">Evidence</div>
          <div className="mt-1 font-mono text-[11px] text-evidence">{evidenceCount} linked</div>
        </div>
        <div>
          <div className="font-mono text-[8px] uppercase tracking-[0.15em] text-white/35">Openings</div>
          <div className="mt-1 font-mono text-[11px] text-brand">{decisionCount} ready</div>
        </div>
      </div>
    </div>
  )
}

function BriefingHome({ groups, all, onStart }: { readonly groups: ResourceGroups; readonly all: IntelligenceResourceRecord[]; readonly onStart: () => void }) {
  const briefs = groups.intelligence.filter((item) => item.reference.resource_kind === 'brief')
  const latestBrief = briefs[0]
  const latestBriefStory = latestBrief === undefined ? undefined : briefRevisionStory(latestBrief, briefs[1])
  const sourceCount = groups.connections.filter((item) => item.reference.resource_kind === 'source').length
  const movementCount = groups.intelligence.filter((item) => ['signal', 'shift'].includes(item.reference.resource_kind)).length
  const decisionCount = groups.opportunities.filter((item) => item.reference.resource_kind === 'case').length
  const stream = groups.intelligence
    .filter((item) => item !== latestBrief && ['signal', 'shift', 'brief'].includes(item.reference.resource_kind))
    .slice(0, 6)

  return (
    <div className="space-y-10">
      <section id="latest-brief" className="atrium-horizon scroll-mt-24 overflow-hidden rounded-xl border">
        <div className="relative z-10 flex items-center justify-between border-b border-white/[0.08] px-5 py-3 md:px-7">
          <div className="flex items-center gap-2 font-mono text-[9px] font-semibold uppercase tracking-[0.19em] text-live">
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-live opacity-50 motion-reduce:animate-none" />
              <span className="relative inline-flex size-1.5 rounded-full bg-live" />
            </span>
            Current intelligence
          </div>
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-white/45">
            {briefs.length} immutable revision{briefs.length === 1 ? '' : 's'}
          </span>
        </div>
        <div className="relative z-10 grid min-h-[470px] lg:grid-cols-[minmax(0,1.16fr)_minmax(29rem,0.84fr)]">
          <div className="flex min-w-0 flex-col justify-center px-5 py-10 md:px-9 md:py-14 lg:pr-8">
            {latestBrief === undefined ? (
              <EmptyBuilder onStart={onStart} />
            ) : (
              <ResourceCard record={latestBrief} featured horizon storySections={latestBriefStory} />
            )}
          </div>
          <CognitiveField
            sourceCount={sourceCount}
            movementCount={movementCount}
            evidenceCount={latestBrief?.provenance.length ?? 0}
            decisionCount={decisionCount}
            active={latestBrief !== undefined}
          />
        </div>
      </section>

      <AskAce items={all} />

      <aside className="grid gap-5 border-y py-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <div>
          <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.17em] text-muted-foreground">Attention queue</div>
          <h2 className="mt-2 text-xl font-medium tracking-[-0.02em]">What needs a look</h2>
          <p className="mt-2 max-w-xs text-xs leading-5 text-muted-foreground">Material records that crossed the line from background movement into human attention.</p>
        </div>
        <ResourceGrid items={groups.attention.slice(0, 4)} empty="Nothing needs attention right now." compact />
      </aside>

      <section className="space-y-4">
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
    { icon: Radio, label: 'Sources', value: `${sources} admitted`, tone: 'text-live' },
    { icon: Activity, label: 'Watches', value: `${monitors} active`, tone: 'text-live' },
    { icon: Layers3, label: 'Decision openings', value: `${openCases} ready`, tone: 'text-brand' },
    { icon: Clock3, label: 'Freshness', value: freshness, tone: 'text-white/35' },
  ]

  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-6 gap-y-2 border-b pb-4" aria-label="Intelligence coverage">
      {entries.map((entry) => (
        <div key={entry.label} className="flex min-w-0 items-center gap-2">
          <entry.icon className={`size-3 shrink-0 ${entry.tone}`} />
          <span className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">{entry.label}</span>
          <span className="truncate font-mono text-[9px] text-foreground/80">{entry.value}</span>
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
  count,
  active = false,
  tone = 'neutral',
}: {
  readonly icon: typeof Crosshair
  readonly title: string
  readonly detail: string
  readonly count: number
  readonly active?: boolean
  readonly tone?: 'live' | 'evidence' | 'neutral'
}) {
  const inactiveTone = tone === 'live'
    ? 'border-live/20 bg-live/[0.05] text-live'
    : tone === 'evidence'
      ? 'border-evidence/20 bg-evidence/[0.05] text-evidence'
      : 'border-white/10 bg-white/[0.035] text-muted-foreground'
  return (
    <div className="group relative grid grid-cols-[2.75rem_minmax(0,1fr)_auto] items-center gap-3 py-4">
      <div className={active
        ? 'relative z-10 flex size-11 items-center justify-center rounded-full border border-brand/40 bg-brand/15 text-brand shadow-[0_0_36px_color-mix(in_oklab,var(--brand)_22%,transparent)]'
        : `relative z-10 flex size-11 items-center justify-center rounded-full border ${inactiveTone}`}>
        <Icon className="size-4" />
      </div>
      <div className="min-w-0">
        <div className={active ? 'text-sm font-semibold text-foreground' : 'text-sm font-medium text-foreground/80'}>{title}</div>
        <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{detail}</p>
      </div>
      <div className={active ? 'font-mono text-2xl font-medium tabular-nums text-brand' : 'font-mono text-2xl font-medium tabular-nums text-foreground/55'}>{count}</div>
    </div>
  )
}

function OpportunitySection({
  eyebrow,
  title,
  detail,
  items,
  empty,
  tone,
}: {
  readonly eyebrow: string
  readonly title: string
  readonly detail: string
  readonly items: readonly IntelligenceResourceRecord[]
  readonly empty: string
  readonly tone: 'live' | 'evidence' | 'authority'
}) {
  const eyebrowTone = tone === 'live' ? 'text-live' : tone === 'evidence' ? 'text-evidence' : 'text-brand'
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className={`font-mono text-[9px] font-semibold uppercase tracking-[0.17em] ${eyebrowTone}`}>{eyebrow}</div>
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
    <div className="space-y-10">
      <section className="atrium-opportunity-aperture overflow-hidden rounded-xl border border-white/10">
        <div className="grid min-h-[360px] lg:grid-cols-[minmax(0,1.1fr)_minmax(22rem,0.9fr)]">
          <div className="flex flex-col justify-between px-6 py-7 md:px-9 md:py-9">
            <div>
              <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.19em] text-brand">Decision aperture</div>
              <h2 className="mt-5 max-w-3xl text-[clamp(2.25rem,4.2vw,4.5rem)] font-[420] leading-[0.98] tracking-[-0.05em]">
                Intelligence becomes an opportunity when a decision window opens.
              </h2>
            </div>
            <p className="mt-8 max-w-2xl text-sm leading-6 text-muted-foreground">
              ACE promotes a signal or shift when the evidence suggests a favorable or avoidable window. It is not a lead, a task, or autonomous Work; it remains a proposal until a person investigates, accepts, dismisses, or turns it into Strategy.
            </p>
          </div>
          <div className="relative border-t border-white/[0.08] px-6 py-6 lg:border-l lg:border-t-0 lg:px-9">
            <div className="absolute bottom-[4.6rem] left-[3.72rem] top-[4.65rem] w-px bg-gradient-to-b from-live/30 via-[var(--evidence)] to-brand/45 lg:left-[4.72rem]" />
            <div className="flex h-full flex-col justify-center divide-y divide-white/[0.07]">
              <OpportunityStage icon={Radio} title="Signal" count={earlySignals.length} detail="Relevant evidence enters the watch field." tone="live" />
              <OpportunityStage icon={TimerReset} title="Shift" count={emergingOpenings.length} detail="A material delta changes the current baseline." tone="evidence" />
              <OpportunityStage icon={SearchCheck} title="Decision opening" count={decisionOpenings.length} detail="A bounded question is ready for human judgment." active />
            </div>
          </div>
        </div>
      </section>

      <OpportunitySection
        eyebrow="Ready to investigate"
        title="Decision openings"
        detail="Cases have a bounded question and preserved evidence. Review the record before turning one into Strategy or downstream Work."
        items={decisionOpenings}
        empty="No evidence-backed decision openings are ready yet."
        tone="authority"
      />
      <OpportunitySection
        eyebrow="Developing"
        title="Emerging openings"
        detail="Material shifts may become Opportunities once their decision window, impact, and evidence are clear."
        items={emergingOpenings}
        empty="No material shifts are currently developing into Opportunities."
        tone="evidence"
      />
      {earlySignals.length > 0 && (
        <OpportunitySection
          eyebrow="Watchlist"
          title="Early signals"
          detail="These observations are relevant, but ACE has not yet established a material shift or bounded decision question."
          items={earlySignals}
          empty="No early signals are being watched."
          tone="live"
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
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-muted/60 text-foreground/65">
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
  const { page, loading, error, refresh } = useIntelligenceResources()
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

  async function prepareIntelligence(request: IntelligenceBuildPlanPrepareInput) {
    return prepareIntelligenceBuild(request)
  }

  return (
    <div className="atrium-command-center dark min-h-svh bg-background text-foreground">
      <SidebarProvider>
        <KernelNav />
        <SidebarInset className="min-h-svh bg-background">
        <header className="sticky top-0 z-20 flex min-h-[72px] items-center gap-4 border-b bg-background/95 px-5 backdrop-blur md:px-8">
          <SidebarTrigger className="md:hidden" />
          <div className="min-w-0">
            <div className="truncate font-mono text-[8px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
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
                {page.state === 'degraded' ? <CircleAlert className="mr-1 size-3 text-warning" /> : <ShieldCheck className="mr-1 size-3 text-live" />}
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
          onPrepareBuild={prepareIntelligence}
          onOpenBrief={openFirstBrief}
        />
        </SidebarInset>
      </SidebarProvider>
    </div>
  )
}
