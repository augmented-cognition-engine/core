// core/ui/canvas/src/app/DeliberationCanvas.tsx
//
// The partner surface at `/`. JTBD on arrival:
//   "step into the workshop where your partner and your committee are
//    already thinking about your product."
//
// Three columns + a sticky voice line + a persistently-warm composer:
//
//   ┌───────────────────────────────────────────────────────────┐
//   │ Sidebar (ext nav slot)  ·  Topbar (what's on the table)   │
//   ├──────────────┬────────────────────────┬──────────────────┤
//   │ Committee    │ Active deliberation    │ Pinned notes      │
//   │ rail         │ (vertical cascade)     │ (memory surface)  │
//   │ — agents     │ — current stage, past  │ — partner-raised  │
//   │ — scenario   │   collapsed, future    │   questions       │
//   │ — timeline   │   dimmed               │ — captured calls  │
//   ├──────────────┴────────────────────────┴──────────────────┤
//   │ Voice line   ·  always present, says what just shifted    │
//   ├───────────────────────────────────────────────────────────┤
//   │ Composer  ·  always warm, suggestion-as-placeholder       │
//   └───────────────────────────────────────────────────────────┘
//
// Discipline: ONLY canonical shadcn primitives + the voice slot. Semantic
// chart palette for agent identity (chart-1..5 + destructive); primary
// chrome ONLY for the active stage and the steer-pulse on the composer.

import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  CornerUpRight,
  Eye,
  Loader2,
  Pause,
  Pin,
  Play,
  Sparkles,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { Aphorism, ScoreHero } from '@/design/components'
import { Avatar, AvatarFallback } from '@/design/shadcn/ui/avatar'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import { Input } from '@/design/shadcn/ui/input'
import {
  SidebarInset,
  SidebarProvider,
} from '@/design/shadcn/ui/sidebar'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/design/shadcn/ui/tooltip'

import { KernelNav } from './ext/defaults/KernelNav'
import { KernelVoice } from './ext/defaults/KernelVoice'
import { extensionSlot } from './ext/registry'
import { useOrchestrationSession } from './journey/useOrchestrationSession'
import type { DeliberationJourneyState } from '@/types/canvas'

// Chrome slots — an extension may register branded nav/voice through the
// ext seam; the kernel defaults render otherwise.
const Nav = extensionSlot('nav') ?? KernelNav
const Voice = extensionSlot('voice') ?? KernelVoice

/* -------------------------------------------------------------------------- */
/* DEMO DATA — replaced by real committee state once the live wire lands.   */
/* The point of this surface is to land "warm": there is always a            */
/* scenario, always agents at the table, always a stage in motion.           */
/* -------------------------------------------------------------------------- */

// Was a fixed 5-seat union for the demo; loosened to string so live meta-skill tracks (arbitrary slugs)
// can seat the committee. The demo seats below are still valid AgentSlots.
type AgentSlot = string

interface Agent {
  readonly slot: AgentSlot
  readonly name: string
  readonly role: string
  readonly glyph: string
  readonly speaking: boolean
  /** Tailwind-style chart-N text color the agent identifies as. */
  readonly tone: string
  /** Bg color paired with the tone. */
  readonly bg: string
}

const AGENTS: readonly Agent[] = [
  { slot: 'researcher', name: 'Researcher', role: 'reads the buyer', glyph: 'R', speaking: true,  tone: 'text-[var(--chart-2)]', bg: 'bg-[var(--chart-2)]/10' },
  { slot: 'pm',         name: 'PMM',        role: 'owns the story',  glyph: 'P', speaking: false, tone: 'text-[var(--chart-4)]', bg: 'bg-[var(--chart-4)]/10' },
  { slot: 'tech_arch',  name: 'Architect',  role: 'maps the stack',  glyph: 'A', speaking: true,  tone: 'text-[var(--chart-1)]', bg: 'bg-[var(--chart-1)]/10' },
  { slot: 'skeptic',    name: 'Skeptic',    role: 'finds the seam',  glyph: 'S', speaking: false, tone: 'text-[var(--chart-5)]', bg: 'bg-[var(--chart-5)]/10' },
  { slot: 'security',   name: 'Risk',       role: 'guards the gate', glyph: 'R', speaking: false, tone: 'text-destructive',      bg: 'bg-destructive/10' },
]

interface Scenario {
  readonly id: string
  readonly label: string
  readonly question: string
  readonly shape: string
  readonly classification: readonly string[]
}

const ACTIVE_SCENARIO: Scenario = {
  id: 'homepage_hero_pivot',
  label: 'Homepage hero pivot',
  shape: 'positioning · storytelling',
  question:
    'Should the homepage hero pivot from "price-first" to "outcomes-first" for the Q3 launch?',
  classification: ['positioning', 'storytelling', 'deliberative · depth 3'],
}

type StageStatus = 'past' | 'current' | 'future'
interface Stage {
  readonly id: string
  readonly num: number
  readonly name: string
  readonly phase: string
  readonly status: StageStatus
  readonly summary: string
  /** The seats' contributions at this stage (live). Absent on the demo stages — StageBlock falls back to
   *  its scripted lines so the warm demo still reads. */
  readonly contributions?: readonly { readonly agent: Agent; readonly text: string }[]
}

const STAGES: readonly Stage[] = [
  { id: 'frame',  num: 1, name: 'Frame',     phase: 'set the question',   status: 'past',    summary: 'Anchored on the Q3 buyer — the economic buyer, not the practitioner.' },
  { id: 'div1',   num: 2, name: 'Diverge',   phase: 'cast wide',          status: 'past',    summary: '3 framings surfaced — outcomes-first / platform-first / price-first.' },
  { id: 'con1',   num: 3, name: 'Converge',  phase: 'pick a lens',        status: 'current', summary: '' },
  { id: 'div2',   num: 4, name: 'Stress',    phase: 'red-team',           status: 'future',  summary: '' },
  { id: 'con2',   num: 5, name: 'Decide',    phase: 'verdict + receipts', status: 'future',  summary: '' },
]

interface PinnedNote {
  readonly id: string
  readonly kind: 'question' | 'decision' | 'finding'
  readonly text: string
  readonly meta: string
}

const PINS: readonly PinnedNote[] = [
  { id: '1', kind: 'question', text: 'How does the outcomes-first framing hold up against the incumbent\'s reliability claim?', meta: 'Partner · 12m ago' },
  { id: '2', kind: 'decision', text: 'CFO Mode vetoed the unhedged pricing line on the source page.', meta: 'Brief Composer · this morning' },
  { id: '3', kind: 'finding',  text: 'Voice drift on the "outcomes" claim — 3 pages off the canonical pillar.', meta: 'Sentinel · 1h ago' },
]

const SUGGESTED_PROMPTS: readonly string[] = [
  'Ask the Skeptic what would change a CFO\'s mind',
  'Run the outcomes-first framing past the security seat',
  'What did the room miss in the last Diverge stage?',
]

/* -------------------------------------------------------------------------- */
/* LIVE PROJECTION — map the live orchestration session into this surface's    */
/* committee / scenario / stages / pins. The demo consts above are the warm    */
/* fallback shown until a real session streams in (the surface never goes      */
/* cold). Pure, so the mapping is testable without a socket.                   */
/* -------------------------------------------------------------------------- */

interface CommitteeView {
  readonly scenario: Scenario
  readonly agents: readonly Agent[]
  readonly stages: readonly Stage[]
  readonly pins: readonly PinnedNote[]
}

// Identity colors for the live seats — the same semantic chart palette the demo seats use.
const _SEAT_TONES: readonly { tone: string; bg: string }[] = [
  { tone: 'text-[var(--chart-2)]', bg: 'bg-[var(--chart-2)]/10' },
  { tone: 'text-[var(--chart-4)]', bg: 'bg-[var(--chart-4)]/10' },
  { tone: 'text-[var(--chart-1)]', bg: 'bg-[var(--chart-1)]/10' },
  { tone: 'text-[var(--chart-5)]', bg: 'bg-[var(--chart-5)]/10' },
  { tone: 'text-[var(--chart-3)]', bg: 'bg-[var(--chart-3)]/10' },
]

/** One live meta-skill track → a committee seat. Index drives the identity color, consistent across the
 *  rail and per-stage contributions. */
function _trackToAgent(t: { metaSkill: string; label: string; instrument?: string; inFlight?: boolean }, i: number): Agent {
  const c = _SEAT_TONES[i % _SEAT_TONES.length]!
  return {
    slot: t.metaSkill || `seat-${i}`,
    name: t.label || t.metaSkill,
    role: t.instrument ?? t.metaSkill.replace(/_/g, ' '),
    glyph: (t.label || t.metaSkill || '?').charAt(0).toUpperCase(),
    speaking: t.inFlight ?? false,
    tone: c.tone,
    bg: c.bg,
  }
}

/** Project the live journey state into this surface's committee model. The committee = the meta-skill
 *  TRACKS at the most recent stage that has any (the real seats; the demo's named marketing seats were
 *  placeholders). */
export function projectJourneyToCommittee(j: DeliberationJourneyState): CommitteeView {
  const cls = j.classification
  const classification = [cls.discipline, cls.archetype, `${cls.mode} · depth ${cls.depth}`].filter(
    (c) => c && c.trim().length > 0,
  )
  const scenario: Scenario = {
    id: 'live',
    label: j.topic.length > 72 ? `${j.topic.slice(0, 72)}…` : j.topic,
    shape: [cls.discipline, cls.mode].filter(Boolean).join(' · '),
    question: j.topic,
    classification,
  }

  const seatStage = [...j.stages].reverse().find((s) => s.tracks.length > 0)
  const agents: Agent[] = (seatStage?.tracks ?? []).map(_trackToAgent)

  const stages: Stage[] = j.stages.map((s, i) => ({
    id: s.id,
    num: i + 1,
    name: s.title,
    phase: s.subtitle ?? s.phase,
    status: s.status, // journey + surface StageStatus are the same 'past'|'current'|'future' union
    summary: s.synthesis?.implication ?? '',
    contributions: s.tracks
      .filter((t) => t.contribution && t.contribution.trim().length > 0)
      .map((t, i) => ({ agent: _trackToAgent(t, i), text: t.contribution })),
  }))

  const pins: PinnedNote[] = (j.priorDecisions ?? []).map((d) => ({
    id: d.id,
    kind: 'decision' as const,
    text: d.title,
    meta: d.rationale ?? 'Decision captured',
  }))

  return { scenario, agents, stages, pins }
}

/* -------------------------------------------------------------------------- */
/* SURFACE                                                                    */
/* -------------------------------------------------------------------------- */

const eyebrow = 'text-[10px] uppercase tracking-widest font-semibold text-muted-foreground'
const eyebrowAccent = 'text-[10px] uppercase tracking-widest font-semibold text-primary'
const monoOverline =
  'font-mono text-[10px] tabular-nums tracking-widest text-muted-foreground/80'

export function DeliberationCanvas() {
  // Live session — fresh work uses ?topic; durable replay uses ?session + ?run
  // (+ optional ?seq cursor). No complete launch coordinates means no live session.
  const [params, setParams] = useSearchParams()
  const urlTopic = params.get('topic')
  const urlSession = params.get('session')
  const urlRun = params.get('run')
  const rawSeq = params.get('seq')
  const urlSeq = rawSeq !== null && /^\d+$/.test(rawSeq) ? Number(rawSeq) : undefined
  const live = useOrchestrationSession(urlTopic, {
    resumeSessionId: urlSession ?? undefined,
    resumeRunId: urlRun ?? undefined,
    resumeLastSeq: urlSeq,
    autoReconnect: true,
  })

  const [playing, setPlaying] = useState(true)
  const [composer, setComposer] = useState('')
  const [localPins, setLocalPins] = useState<readonly PinnedNote[]>([])
  const [activeAgent, setActiveAgent] = useState<AgentSlot | null>(null)

  // Project the live session into the committee model when it has streamed stages; otherwise the warm
  // demo scenario, so the room is never cold on arrival.
  const isLive = live.journey !== null && live.journey !== undefined && live.journey.stages.length > 0
  const view: CommitteeView = useMemo(() => {
    const j = live.journey
    if (j && j.stages.length > 0) return projectJourneyToCommittee(j)
    return { scenario: ACTIVE_SCENARIO, agents: AGENTS, stages: STAGES, pins: PINS }
  }, [live.journey])

  // Room status for the rail dot + the voice line. Live mode reflects the SESSION (the play/pause
  // toggle only ever governed the demo narration and pauses nothing real, so it's demo-only chrome).
  const roomStatus: { label: string; pulse: boolean } = isLive
    ? live.status === 'streaming'
      ? { label: 'live', pulse: true }
      : live.status === 'done'
        ? { label: 'settled', pulse: false }
        : live.status === 'error'
          ? { label: 'disconnected', pulse: false }
          : { label: 'connecting', pulse: true }
    : playing
      ? { label: 'prepared demo', pulse: false }
      : { label: 'demo paused', pulse: false }

  // The voice line narrates THIS room. Live mode speaks from the projected state — the speaking seat
  // and the current stage — never the demo script.
  const currentStage = view.stages.find((s) => s.status === 'current')
  const speakingSeat = view.agents.find((a) => a.speaking)
  const voiceLine = isLive
    ? live.status === 'error'
      ? 'Connection lost — reconnecting to the room. Nothing is discarded.'
      : live.status === 'done'
        ? 'The room has settled. Read back through the stages, or steer to reopen.'
        : speakingSeat && currentStage
          ? `${speakingSeat.name} is speaking — the room is in ${currentStage.name}.`
          : currentStage
            ? `The room is in ${currentStage.name}.`
            : 'The room is warming up — seats arrive as the committee composes.'
    : playing
      ? 'Prepared demonstration — Architect bridges Researcher\'s framing in this scripted scenario.'
      : 'Prepared demonstration paused. Press play to continue the script.'

  const pins: readonly PinnedNote[] = [...localPins, ...view.pins]

  // Demo prompts name the demo seats; a live room gets a neutral steer suggestion instead.
  const promptPlaceholder = isLive
    ? 'Steer the room — redirect a seat, question a stage, raise a concern'
    : SUGGESTED_PROMPTS[Math.floor(Date.now() / 8000) % SUGGESTED_PROMPTS.length]!

  return (
    <SidebarProvider>
      <Nav />
      <SidebarInset className="h-svh overflow-hidden bg-muted/40">
        {/* Topbar — what the room is currently thinking about */}
        <header className="flex items-center gap-3 h-14 px-6 border-b sticky top-0 z-10 bg-background shrink-0">
          <div className="min-w-0 flex-1">
            <div className={cn(monoOverline, 'mb-0.5')}>on the table</div>
            <div className="text-sm font-semibold tracking-tight truncate">
              {view.scenario.label}
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            {view.scenario.classification.map((c) => (
              <Badge key={c} variant="secondary" className="font-mono text-[10px] tracking-wide">
                {c}
              </Badge>
            ))}
          </div>
          {/* Play/pause governs only the demo narration — a live session can't be paused from here,
              so the control hides rather than lie. */}
          {!isLive && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setPlaying((p) => !p)}
                  aria-label={playing ? 'Pause the room' : 'Resume the room'}
                >
                  {playing ? <Pause /> : <Play />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{playing ? 'Pause the room' : 'Resume the room'}</TooltipContent>
            </Tooltip>
          )}
        </header>

        {/* Three-column body */}
        <div className="flex-1 overflow-hidden grid grid-cols-[280px_minmax(0,1fr)_320px] divide-x divide-border">
          <CommitteeRail
            status={roomStatus}
            activeAgent={activeAgent}
            onPickAgent={setActiveAgent}
            agents={view.agents}
            scenario={view.scenario}
          />
          <ActiveDeliberation
            scenario={view.scenario}
            stages={view.stages}
            onPin={(note) =>
              setLocalPins((prev) => [{ id: `local-${Date.now()}`, kind: 'finding', text: note, meta: 'Pinned just now' }, ...prev])
            }
          />
          <PinnedNotes pins={pins} />
        </div>

        {/* Voice line — always speaking, and always about THIS room (live state or the demo script). */}
        <div className="px-6 pt-3 pb-2 shrink-0 bg-background border-t">
          <Voice>{voiceLine}</Voice>
        </div>

        {/* Composer — always warm */}
        <form
          className="flex items-center gap-2 px-6 py-3 border-t shrink-0 bg-background"
          onSubmit={(e) => {
            e.preventDefault()
            const q = composer.trim()
            if (q.length === 0) return
            if (live.sessionId !== null) {
              live.steer(q) // steer the open room
            } else {
              // warm landing, no session yet — pose the question and START a real
              // committee in place (?topic feeds useOrchestrationSession).
              setParams({ topic: q })
            }
            setComposer('')
          }}
        >
          <span className={cn(eyebrowAccent, 'shrink-0')}>steer</span>
          <Input
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            placeholder={promptPlaceholder}
            className="flex-1"
            aria-label="Steer the room"
          />
          <Button type="submit" disabled={composer.trim().length === 0}>
            <CornerUpRight /> Send
          </Button>
        </form>
      </SidebarInset>
    </SidebarProvider>
  )
}

/* -------------------------------------------------------------------------- */
/* COMMITTEE RAIL — compact multiplayer view                                  */
/* -------------------------------------------------------------------------- */

interface CommitteeRailProps {
  readonly status: { readonly label: string; readonly pulse: boolean }
  readonly activeAgent: AgentSlot | null
  readonly onPickAgent: (slot: AgentSlot | null) => void
  readonly agents: readonly Agent[]
  readonly scenario: Scenario
}

function CommitteeRail({ status, activeAgent, onPickAgent, agents, scenario }: CommitteeRailProps) {
  return (
    <aside className="flex flex-col gap-4 px-4 py-4 overflow-y-auto bg-background/40">
      <div className="space-y-1">
        <div className={cn(monoOverline, 'flex items-center gap-1.5')}>
          {status.pulse ? (
            <>
              <span className="relative inline-flex size-1.5">
                <span className="absolute inset-0 rounded-full bg-primary/40 animate-ping" />
                <span className="relative size-1.5 rounded-full bg-primary" />
              </span>
              {status.label}
            </>
          ) : (
            <>
              <span className="size-1.5 rounded-full bg-muted-foreground/40" />
              {status.label}
            </>
          )}
        </div>
        <h2 className="text-sm font-semibold tracking-tight">The Committee</h2>
        <p className="text-xs text-muted-foreground leading-snug">
          {agents.length > 0
            ? `${agents.length} ${agents.length === 1 ? 'seat' : 'seats'}. One question. Click a seat to listen in.`
            : 'The seats are forming — the committee arrives with the first stage.'}
        </p>
      </div>

      <ul className="space-y-1.5">
        {agents.map((a) => {
          const isActive = activeAgent === a.slot
          return (
            <li key={a.slot}>
              <button
                type="button"
                onClick={() => onPickAgent(isActive ? null : a.slot)}
                className={cn(
                  'w-full flex items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors',
                  isActive ? 'bg-muted' : 'hover:bg-muted/50',
                )}
              >
                <Avatar className="size-7 shrink-0">
                  <AvatarFallback className={cn('text-xs font-semibold', a.bg, a.tone)}>
                    {a.glyph}
                  </AvatarFallback>
                </Avatar>
                <div className="flex flex-col min-w-0 flex-1">
                  <span className="text-sm font-medium leading-tight">{a.name}</span>
                  <span className="text-[11px] text-muted-foreground leading-tight truncate">
                    {a.role}
                  </span>
                </div>
                {a.speaking && status.pulse && (
                  <span aria-hidden className="shrink-0 inline-flex items-center gap-0.5">
                    <span className="size-1 rounded-full bg-primary animate-pulse" />
                    <span className="size-1 rounded-full bg-primary animate-pulse [animation-delay:120ms]" />
                    <span className="size-1 rounded-full bg-primary animate-pulse [animation-delay:240ms]" />
                  </span>
                )}
              </button>
            </li>
          )
        })}
      </ul>

      <div className="border-t pt-3 mt-1 space-y-1.5">
        <div className={monoOverline}>scenarios</div>
        <button
          type="button"
          className="w-full text-left rounded-md px-2 py-2 bg-primary/5 ring-1 ring-primary/20"
        >
          <div className="text-xs font-semibold text-primary">{scenario.label}</div>
          <div className="text-[10px] text-muted-foreground mt-0.5">{scenario.shape}</div>
        </button>
        <Link
          to="/atrium"
          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
        >
          Open Atrium <ArrowUpRight className="size-3" />
        </Link>
      </div>
    </aside>
  )
}

/* -------------------------------------------------------------------------- */
/* ACTIVE DELIBERATION — vertical cascade (same pattern as Brief Composer)   */
/* -------------------------------------------------------------------------- */

interface ActiveDeliberationProps {
  readonly scenario: Scenario
  readonly stages: readonly Stage[]
  readonly onPin: (note: string) => void
}

function ActiveDeliberation({ scenario, stages, onPin }: ActiveDeliberationProps) {
  const currentIndex = stages.findIndex((s) => s.status === 'current')
  const currentStage = currentIndex >= 0 ? stages[currentIndex] : undefined
  return (
    <section className="overflow-y-auto px-6 py-10">
      <div className="max-w-2xl mx-auto space-y-12">
        {/* Display-tier hero: eyebrow + topic at editorial scale + italic
            clause from the current stage + page-fact on the right. Same
            pattern as the journey TopicHeader for visual cohesion across
            the two ACE base surfaces. */}
        <div className="flex items-start justify-between gap-8">
          <div className="flex flex-col gap-3 min-w-0 flex-1">
            <div className={eyebrow}>The question on the table</div>
            <h1 className="font-heading text-3xl md:text-4xl font-semibold tracking-tight leading-[1.15]">
              {scenario.question}
            </h1>
            {currentStage !== undefined && (
              <Aphorism size="lg">
                <span className="text-muted-foreground">{currentStage.phase}</span>
              </Aphorism>
            )}
          </div>
          {currentStage !== undefined && (
            <div className="shrink-0 pt-2">
              <ScoreHero
                value={
                  <span>
                    <span className="text-foreground">{currentIndex + 1}</span>
                    <span className="text-muted-foreground/50"> / {stages.length}</span>
                  </span>
                }
                caption={`stage · ${currentStage.name.toLowerCase()}`}
                size="md"
              />
            </div>
          )}
        </div>

        {/* Editorial transition — marks the shift from "what we're
            deliberating" (hero) to "how it's unfolding" (stage cascade). */}
        <div>
          <Aphorism size="xl">
            <span className="text-muted-foreground/80">The room, in motion.</span>
          </Aphorism>
        </div>

        <div className="space-y-0">
          {stages.map((s, i) => (
            <div key={s.id}>
              <StageBlock stage={s} onPin={onPin} />
              {i < stages.length - 1 && <Connector />}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Connector() {
  return (
    <div aria-hidden className="flex flex-col items-center py-2">
      <div className="w-px h-6 bg-border" />
      <div className="text-muted-foreground text-xs leading-none">↓</div>
    </div>
  )
}

function stageComposingLabel(stage: Stage): string {
  if (stage.contributions === undefined) return 'Skeptic is composing a response…'
  const speaking = stage.contributions.find((c) => c.agent.speaking)
  return speaking ? `${speaking.agent.name} is composing a response…` : 'The room is composing…'
}

function StageBlock({ stage, onPin }: { stage: Stage; onPin: (note: string) => void }) {
  if (stage.status === 'future') {
    return (
      <Card className="border-dashed bg-muted/20">
        <CardContent>
          <div className="flex items-center gap-3">
            <StageBadge num={stage.num} status="future" />
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-semibold text-muted-foreground">{stage.name}</h3>
              <p className="text-xs text-muted-foreground/70">{stage.phase}</p>
            </div>
            <span className="text-xs text-muted-foreground italic">awaiting…</span>
          </div>
        </CardContent>
      </Card>
    )
  }
  if (stage.status === 'past') {
    return (
      <Card>
        <CardContent>
          <details>
            <summary className="flex items-center gap-3 cursor-pointer list-none">
              <StageBadge num={stage.num} status="past" />
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold">{stage.name}</h3>
                <p className="text-xs text-muted-foreground italic">{stage.summary}</p>
              </div>
              <ChevronDown className="size-4 text-muted-foreground shrink-0" />
            </summary>
          </details>
        </CardContent>
      </Card>
    )
  }
  // current
  return (
    <Card className="shadow-md">
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <StageBadge num={stage.num} status="current" />
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold tracking-tight">{stage.name}</h3>
            <p className="text-xs text-muted-foreground">{stage.phase}</p>
          </div>
          <Badge>active</Badge>
        </div>
        <div className="space-y-2 pl-11 border-l-2 border-border ml-3.5">
          {stage.contributions === undefined ? (
            // Warm demo fallback — scripted seats when there's no live session yet.
            <>
              <ContributionLine
                agent={AGENTS[0]!}
                text="The Q3 buyer is the economic buyer. They've already accepted that the workload is real — what they haven't accepted is the operating model. The hero needs to answer the operating-model question, not the workload question."
                onPin={onPin}
              />
              <ContributionLine
                agent={AGENTS[2]!}
                text="If we land on outcomes-first, the proof point has to be the stack diagram, not a use case. The CTO seat reads use-case-led as marketing fluff."
                onPin={onPin}
              />
            </>
          ) : (
            stage.contributions.map((c, i) => (
              <ContributionLine key={`${c.agent.slot}-${i}`} agent={c.agent} text={c.text} onPin={onPin} />
            ))
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground pt-2 border-t">
          <Loader2 className="size-3 animate-spin [animation-duration:2s]" />
          {stageComposingLabel(stage)}
        </div>
      </CardContent>
    </Card>
  )
}

function StageBadge({ num, status }: { num: number; status: StageStatus }) {
  const cls =
    status === 'current'
      ? 'bg-primary text-primary-foreground'
      : status === 'past'
      ? 'bg-[var(--chart-1)] text-background'
      : 'bg-muted text-muted-foreground'
  return (
    <div className={cn('shrink-0 inline-flex items-center justify-center size-7 rounded-full text-xs font-bold tabular-nums', cls)}>
      {status === 'past' ? '✓' : num}
    </div>
  )
}

function ContributionLine({
  agent,
  text,
  onPin,
}: {
  agent: Agent
  text: string
  onPin: (note: string) => void
}) {
  return (
    <div className="group flex items-start gap-2.5">
      <Avatar className="size-6 shrink-0 mt-0.5">
        <AvatarFallback className={cn('text-[10px] font-semibold', agent.bg, agent.tone)}>
          {agent.glyph}
        </AvatarFallback>
      </Avatar>
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-baseline gap-1.5">
          <span className={cn('text-xs font-semibold', agent.tone)}>{agent.name}</span>
          <span className="text-[10px] text-muted-foreground">{agent.role}</span>
        </div>
        <p className="text-sm leading-snug">{text}</p>
      </div>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => onPin(text)}
            className="shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 hover:bg-muted rounded p-1 transition-opacity"
            aria-label="Pin to notes"
          >
            <Pin className="size-3 text-muted-foreground" />
          </button>
        </TooltipTrigger>
        <TooltipContent>Pin to notes</TooltipContent>
      </Tooltip>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* PINNED NOTES — compounding memory surface                                  */
/* -------------------------------------------------------------------------- */

interface PinnedNotesProps {
  readonly pins: readonly PinnedNote[]
}

const PIN_KIND: Record<PinnedNote['kind'], { Icon: typeof Sparkles; label: string; tone: string }> = {
  question: { Icon: Sparkles,      label: 'Question',  tone: 'text-primary' },
  decision: { Icon: CheckCircle2,  label: 'Decision',  tone: 'text-[var(--chart-1)]' },
  finding:  { Icon: Eye,           label: 'Finding',   tone: 'text-[var(--chart-3)]' },
}

function PinnedNotes({ pins }: PinnedNotesProps) {
  return (
    <aside className="flex flex-col gap-4 px-4 py-4 overflow-y-auto bg-background/40">
      <div className="space-y-1">
        <div className={monoOverline}>memory</div>
        <h2 className="text-sm font-semibold tracking-tight">Pinned</h2>
        <p className="text-xs text-muted-foreground leading-snug">
          What your partner wants you to revisit.
        </p>
      </div>
      <ul className="space-y-2">
        {pins.map((p) => {
          const kind = PIN_KIND[p.kind]
          const Icon = kind.Icon
          return (
            <li key={p.id} className="space-y-1">
              <div className="flex items-center gap-1.5">
                <Icon className={cn('size-3', kind.tone)} />
                <span className={cn('text-[10px] uppercase tracking-widest font-semibold', kind.tone)}>
                  {kind.label}
                </span>
              </div>
              <p className="text-xs leading-snug">{p.text}</p>
              <p className="text-[10px] text-muted-foreground font-mono">{p.meta}</p>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
