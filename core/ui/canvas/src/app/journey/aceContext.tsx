// app/journey/aceContext.tsx
//
// "ACE is not a destination. ACE is a lens."
//
// This module establishes the global Active Context — the page/surface
// ACE is currently reasoning about. Every non-`/` route registers what
// the user is looking at; the PartnerDock and the DeliberationJourney
// both read from this registry so opening the room is always opening
// it WITH context, never cold.
//
// API:
//   const ctx = useAceContext()
//   ctx.set({ surface: 'foresight', label: 'Foresight', question: 'Q3 launch forecast' })
//   ctx.active  // → current ActiveContext | null
//
// A URL-derived fallback is provided for routes that haven't explicitly
// registered yet — better to show "ACE on /foresight" than no
// context at all.

import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export interface ActiveContext {
  /** Stable slug — e.g. 'foresight', 'decisions', 'frameworks'. Drives
   *  the lens label and any future per-surface reasoning seeds. */
  surface: string
  /** Display label — e.g. 'Foresight'. Title-cased. */
  label: string
  /** A reasoning frame derived from the page — e.g. 'Q3 launch forecast'.
   *  Becomes ACE's L1 topic when the room is opened from this page. */
  question?: string
  /** Optional canonical pathname for the surface. Defaults from useLocation. */
  pathname?: string
  /** Page-aware brainstorm suggestions — surfaced in the ACE flyout so the
   *  user gets immediate prompts based on what's on the page, instead of a
   *  blank prompt. */
  suggestions?: string[]
}

interface AceContextValue {
  active: ActiveContext | null
  set: (ctx: ActiveContext) => void
  clear: () => void
}

const AceContextCtx = createContext<AceContextValue | null>(null)

export function AceContextProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<ActiveContext | null>(null)
  const set = useCallback((ctx: ActiveContext) => setActive(ctx), [])
  const clear = useCallback(() => setActive(null), [])
  const value = useMemo(() => ({ active, set, clear }), [active, set, clear])
  return <AceContextCtx.Provider value={value}>{children}</AceContextCtx.Provider>
}

export function useAceContext(): AceContextValue {
  const v = useContext(AceContextCtx)
  if (v === null) {
    // Hook may be called outside provider during route transitions; return
    // a safe no-op rather than throwing.
    return { active: null, set: () => {}, clear: () => {} }
  }
  return v
}

// ---------------------------------------------------------------------------
// URL-derived fallback context
//
// When a page hasn't called `useAceContext().set(...)` yet, fall back to
// pathname-derived metadata so the dock always has *something* to say.
// As pages adopt explicit registration, this fallback becomes redundant
// for them — but it keeps "no cold open" true even for unwired surfaces.
// ---------------------------------------------------------------------------

const SURFACE_LABEL: Record<string, string> = {
  '': 'the room',
  transform: 'Transform',
  changelog: 'Changelog',
  onboard: 'Onboard',
  roadmap: 'Roadmap',
  'tool-matrix': 'Tool Matrix',
  'brief-composer': 'Brief Composer',
  multiplayer: 'the room',
  sentinel: 'Sentinel',
  foresight: 'Foresight',
  calibration: 'Calibration',
  'message-architecture': 'Message Architecture',
  'competitive-tracker': 'Competitive Tracker',
  'persona-variant-generator': 'Persona Variants',
  personas: 'Personas',
  frameworks: 'Frameworks',
  decisions: 'Decisions',
  memory: 'Memory',
  connect: 'Connect',
  voice: 'Voice',
}

const SURFACE_QUESTION: Record<string, string> = {
  foresight: 'predicted outcomes for the in-flight launch',
  decisions: 'what the committee decided — and why',
  personas: 'persona coverage and committee modeling',
  sentinel: 'open findings across the in-flight artifacts',
  calibration: "ACE's recent forecasts vs reality",
  frameworks: 'reasoning frameworks active for this project',
  memory: 'institutional memory across this session',
  'tool-matrix': 'which tools are wired up and what they do',
  'brief-composer': 'briefs in flight + the committee they hit',
  multiplayer: 'parallel committee reasoning on the active brief',
  changelog: 'what shipped recently and what it changed',
  'message-architecture': 'how the message stack is currently composed',
  'competitive-tracker': 'competitor signals worth reacting to',
  'persona-variant-generator': 'persona variants under consideration',
  onboard: "the user's onboarding state and next best surface",
  roadmap: 'planned work, sequencing, dependencies',
  transform: "the org's AI transformation arc",
  connect: 'data connections and what they unlock',
  voice: 'brand voice fidelity — anchor vs. drift across recent samples',
}

const SURFACE_SUGGESTIONS: Record<string, string[]> = {
  foresight: [
    'What would need to be true for the highest-risk failure mode to not happen?',
    'Which prediction has the weakest evidence — and what would shore it up?',
    'Are we missing a committee seat? Who else should be modeled here?',
  ],
  decisions: [
    'Which recent decision is most likely to be regretted in 6 months?',
    'Where did committee dissent get under-weighted in the verdict?',
    'What patterns are emerging across the last 10 verdicts?',
  ],
  personas: [
    'Which committee seat is most under-represented in our personas?',
    'Where do persona objections cluster — and what does that signal?',
    "What would a contrarian buyer say about this product's positioning?",
  ],
  sentinel: [
    'Which open finding has the largest blast radius if ignored?',
    'Are sentinel findings clustering around a single root cause?',
    'What pattern of misses suggests a calibration gap?',
  ],
  calibration: [
    'Where is ACE most miscalibrated — and what would correct it?',
    'Which class of prediction has the worst Brier score?',
    'What evidence would update the priors most decisively?',
  ],
  frameworks: [
    'Which framework is most overused — and what blind spot does that create?',
    'Which framework is missing for this kind of problem?',
    'Stress-test: pick the riskiest decision and apply the strictest framework.',
  ],
  memory: [
    'What pattern is recurring across this session that I should name?',
    'Which captured memory should be promoted to a standing principle?',
    'What did we conclude that contradicts an older capture?',
  ],
  'tool-matrix': [
    "Which tool is wired but never used — and what's blocking adoption?",
    'What capability is missing from the matrix that the work needs?',
    'How should tool routing change for this project profile?',
  ],
  'brief-composer': [
    'Which brief in flight is most at risk of failing committee?',
    'What committee seat would make this brief stronger?',
    'Where is the brief language fighting the buyer persona?',
  ],
  multiplayer: [
    'Where do committee voices diverge — and which divergence matters most?',
    'Whose voice is dominating the synthesis? Should we re-weight?',
    'What objection is no one in the room raising?',
  ],
  changelog: [
    'Which recent ship changed the most about how we think about the product?',
    'What pattern of changes signals a coming pivot?',
    'Which fix touched the most fragile area of the codebase?',
  ],
  'message-architecture': [
    'Which message pillar is least supported by evidence?',
    'Where does the message stack contradict itself across audiences?',
    'What single message would tighten everything below it?',
  ],
  'competitive-tracker': [
    'Which competitor move would force a roadmap reorder?',
    'Where are we over-reacting to a competitor signal?',
    'What competitor pattern signals a category shift, not a feature gap?',
  ],
  'persona-variant-generator': [
    'Which persona variant most extends the buying committee?',
    'What variant exposes a weakness in the current positioning?',
    'Which variant should be the next first-class persona?',
  ],
  onboard: [
    'Which onboarding step is doing the most work — and which is dead weight?',
    "What's the smallest set of signals that get a new user productive?",
    'Where do new users drop off — and what does that signal about the product?',
  ],
  roadmap: [
    'Which roadmap item has the weakest dependency justification?',
    'What sequencing change would create the most option value?',
    'Which planned work, dropped, would change the least?',
  ],
  transform: [
    "What's the highest-leverage transformation move we're under-resourcing?",
    'Which transformation thesis has aged poorly?',
    'Where is the org pulling against the transformation arc?',
  ],
  connect: [
    'Which connection would unlock the most reasoning?',
    'Where do data connections create new categories of risk?',
    'What integration would let ACE answer a question it currently cannot?',
  ],
  voice: [
    'Which sample drifted the most this week — and what tone vector explains it?',
    "Which tone vector has the widest target/actual gap — what's pulling on it?",
    'Are off-voice samples clustering in one channel or audience?',
    "What's the smallest editorial change that would close the biggest drift?",
  ],
}

/** Derive a default ActiveContext from a pathname (URL fallback). */
export function deriveActiveContext(pathname: string): ActiveContext | null {
  // The room itself — no context, we ARE the room.
  if (pathname === '/' || pathname === '' || pathname === '/atrium' || pathname === '/room') return null

  const segments = pathname.replace(/^\/+|\/+$/g, '').split('/')
  // /<ext>/foresight → ['<ext>', 'foresight'] → 'foresight'
  // /showcase → ['showcase'] → 'showcase'
  const surface = segments[segments.length - 1] ?? ''
  const label = SURFACE_LABEL[surface] ?? surface.replace(/-/g, ' ')
  const question = SURFACE_QUESTION[surface]

  return {
    surface,
    label,
    question,
    pathname,
    suggestions: SURFACE_SUGGESTIONS[surface],
  }
}
