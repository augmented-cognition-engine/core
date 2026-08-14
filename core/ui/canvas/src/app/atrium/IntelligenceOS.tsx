import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Activity,
  ArrowRight,
  Bot,
  BrainCircuit,
  CircleAlert,
  Network,
  RefreshCw,
  Route,
  ShieldCheck,
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

type CognitiveZone = 'live' | 'evidence' | 'authority'

interface CognitiveParticle {
  readonly x: number
  readonly y: number
  readonly size: number
  readonly rotation: number
  readonly opacity: number
  readonly zone: CognitiveZone
}

function seededUnit(seed: number): number {
  const value = Math.sin(seed * 12.9898) * 43758.5453
  return value - Math.floor(value)
}

function cognitiveZone(x: number): CognitiveZone {
  if (x < 232) return 'live'
  if (x < 312) return 'evidence'
  return 'authority'
}

function createCognitiveParticles(): readonly CognitiveParticle[] {
  const particles: CognitiveParticle[] = []
  let seed = 1

  for (let row = 0; row < 25; row += 1) {
    for (let column = 0; column < 37; column += 1) {
      const normalizedX = -1 + (column / 36) * 2 + (seededUnit(seed) - 0.5) * 0.045
      const normalizedY = -1 + (row / 24) * 2 + (seededUnit(seed + 1) - 0.5) * 0.055
      const leftLobe = ((normalizedX + 0.27) / 0.77) ** 2 + ((normalizedY + 0.02) / 0.9) ** 2 < 1
      const rightLobe = ((normalizedX - 0.28) / 0.76) ** 2 + ((normalizedY + 0.01) / 0.88) ** 2 < 1
      const topFissure = normalizedY < -0.24 && Math.abs(normalizedX) < 0.045 + Math.abs(normalizedY) * 0.018
      const lowerTrim = normalizedY > 0.68 && Math.abs(normalizedX) > 0.48

      if ((leftLobe || rightLobe) && !topFissure && !lowerTrim) {
        const x = 266 + normalizedX * 181
        const y = 199 + normalizedY * 132
        particles.push({
          x,
          y,
          size: 0.72 + seededUnit(seed + 2) * 1.45,
          rotation: seededUnit(seed + 3) * 360,
          opacity: 0.18 + seededUnit(seed + 4) * 0.62,
          zone: cognitiveZone(x),
        })
      }
      seed += 5
    }
  }

  return particles
}

const COGNITIVE_PARTICLES = createCognitiveParticles()
const COGNITIVE_SILHOUETTE = 'M94 218C82 185 99 151 130 136C128 105 157 79 191 82C214 57 253 55 280 76C309 59 351 73 366 101C401 101 426 128 423 159C450 179 453 215 431 237C438 268 415 296 383 302C365 330 326 338 298 320C270 342 230 337 210 315C177 324 144 307 136 279C109 270 92 246 94 218Z'

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
          <clipPath id="ace-brain-silhouette">
            <path d={COGNITIVE_SILHOUETTE} />
          </clipPath>
        </defs>

        <ellipse className="atrium-cognitive-aura" cx="266" cy="199" rx="194" ry="152" fill="url(#ace-cognition-core)" filter="url(#ace-cognition-soften)" />
        <path className="atrium-cognitive-contour" d={COGNITIVE_SILHOUETTE} />

        <g className="atrium-cognitive-streams" clipPath="url(#ace-brain-silhouette)">
          <path data-zone="live" d="M127 222C171 178 205 202 245 171C277 146 306 147 350 167" />
          <path data-zone="evidence" d="M132 259C177 238 210 263 253 230C294 198 326 218 386 195" />
          <path data-zone="authority" d="M170 304C213 275 250 299 292 266C329 238 360 257 397 226" />
        </g>

        <g className="atrium-cognitive-particles" clipPath="url(#ace-brain-silhouette)">
          {(['live', 'evidence', 'authority'] as const).map((zone) => (
            <g key={zone} data-zone={zone}>
              {COGNITIVE_PARTICLES.filter((particle) => particle.zone === zone).map((particle, index) => (
              <polygon
                  key={`${zone}-${index}`}
                  points={`${particle.x},${particle.y - particle.size} ${particle.x + particle.size * 0.88},${particle.y + particle.size * 0.55} ${particle.x - particle.size * 0.88},${particle.y + particle.size * 0.55}`}
                  transform={`rotate(${particle.rotation} ${particle.x} ${particle.y})`}
                  fillOpacity={particle.opacity}
              />
              ))}
            </g>
          ))}
        </g>

        <path className="atrium-cognitive-fissure" d="M267 90C255 129 273 157 264 192C253 234 278 264 267 312" />
        <g className="atrium-cognitive-pulses">
          <circle data-zone="live" cx="198" cy="176" r="3" />
          <circle data-zone="evidence" cx="272" cy="224" r="3.2" />
          <circle data-zone="authority" cx="344" cy="249" r="3" />
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
      <section id="latest-brief" className="atrium-horizon scroll-mt-24 overflow-hidden border-y border-white/[0.08]">
        <div className="relative z-10 grid min-h-[470px] lg:grid-cols-[minmax(0,1.16fr)_minmax(29rem,0.84fr)]">
          <div className="flex min-w-0 flex-col justify-center px-5 py-10 md:px-9 md:py-14 lg:pr-8">
            <div className="mb-8 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2 font-mono text-[9px] font-semibold uppercase tracking-[0.18em] text-live">
                <span className="relative flex size-1.5">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-live opacity-45 motion-reduce:animate-none" />
                  <span className="relative inline-flex size-1.5 rounded-full bg-live" />
                </span>
                Current intelligence
              </div>
              <span className="font-mono text-[8px] uppercase tracking-[0.14em] text-white/35">
                {briefs.length} immutable revision{briefs.length === 1 ? '' : 's'}
              </span>
            </div>
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
    { label: 'Sources', value: `${sources} admitted`, tone: 'bg-live' },
    { label: 'Watches', value: `${monitors} active`, tone: 'bg-live' },
    { label: 'Decision openings', value: `${openCases} ready`, tone: 'bg-brand' },
    { label: 'Freshness', value: freshness, tone: 'bg-foreground/25' },
  ]

  return (
    <div className="mb-5 grid gap-x-6 gap-y-3 border-b pb-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Intelligence coverage">
      {entries.map((entry) => (
        <div key={entry.label} className="flex min-w-0 items-center gap-2.5">
          <span className={`size-1 shrink-0 rounded-full ${entry.tone}`} aria-hidden="true" />
          <span className="font-mono text-[8px] uppercase tracking-[0.13em] text-muted-foreground">{entry.label}</span>
          <span className="ml-auto truncate font-mono text-[9px] text-foreground/75">{entry.value}</span>
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
  title,
  detail,
  count,
  active = false,
  tone = 'neutral',
}: {
  readonly title: string
  readonly detail: string
  readonly count: number
  readonly active?: boolean
  readonly tone?: 'live' | 'evidence' | 'neutral'
}) {
  const inactiveTone = tone === 'live'
    ? 'bg-live'
    : tone === 'evidence'
      ? 'bg-evidence'
      : 'bg-foreground/35'
  return (
    <div className="group relative grid grid-cols-[1rem_minmax(0,1fr)_auto] items-center gap-4 py-4">
      <span className={active
        ? 'relative z-10 size-2 rounded-full bg-brand shadow-[0_0_18px_color-mix(in_oklab,var(--brand)_45%,transparent)]'
        : `relative z-10 size-1.5 rounded-full ${inactiveTone}`}
        aria-hidden="true"
      />
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
      <section className="atrium-opportunity-aperture overflow-hidden border-y border-white/[0.08]">
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
            <div className="absolute bottom-[5.5rem] left-[2.45rem] top-[5.5rem] w-px bg-gradient-to-b from-live/25 via-[var(--evidence)] to-brand/35 lg:left-[3.72rem]" />
            <div className="flex h-full flex-col justify-center divide-y divide-white/[0.07]">
              <OpportunityStage title="Signal" count={earlySignals.length} detail="Relevant evidence enters the watch field." tone="live" />
              <OpportunityStage title="Shift" count={emergingOpenings.length} detail="A material delta changes the current baseline." tone="evidence" />
              <OpportunityStage title="Decision opening" count={decisionOpenings.length} detail="A bounded question is ready for human judgment." active />
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
        <header className="sticky top-0 z-20 flex min-h-16 items-center gap-4 border-b bg-background/95 px-5 backdrop-blur md:px-8">
          <SidebarTrigger className="md:hidden" />
          <div className="min-w-0">
            <div className="truncate font-mono text-[8px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              ACE / {productName}
            </div>
            <h1 className="mt-1 truncate text-base font-semibold tracking-tight">{copy.title}</h1>
            <p className="sr-only">{copy.subtitle}</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setOnboardingOpen(true)}>
              <span className="hidden sm:inline">{onboardingSession === null ? 'Build intelligence' : 'View build'}</span>
            </Button>
            {page !== null && (
              <Badge variant={page.state === 'degraded' ? 'outline' : 'secondary'} className="hidden rounded-sm border border-border/70 bg-card font-mono text-[9px] sm:inline-flex">
                {page.state === 'degraded'
                  ? <CircleAlert className="mr-1 size-3 text-warning" />
                  : <span className="mr-1.5 size-1 rounded-full bg-live" aria-hidden="true" />}
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
