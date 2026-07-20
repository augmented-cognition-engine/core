// core/ui/canvas/src/app/state.ts
//
// Typed state contract for the ACE core surface. Every chrome component
// (Topbar, VisionAnchor, BriefMeBack, CanvasRegion, WorkingPanel,
// Footer) reads from this object. The point: components are reactive
// to state, not predetermined.
//
// The hook `useAceCoreState()` resolves this object — initially from
// `fixtures/multiplayer.ts` so first render looks like the multiplayer.html
// reference (populated, the partner is mid-thought). When the live
// WebSocket subscription lands, the same hook returns real values
// without any component change.
import type { ReactNode } from 'react'

import type { CompositionSelectedPayload, DeliberationJourneyState } from '../types/canvas'

// -- Topbar -----------------------------------------------------------------

export interface CostTickerState {
  tokensUsed: number
  costUsd: number
  /** "this turn" / "this session" — naming the slice this number belongs to */
  scope: string
}

export interface ProgressPhase {
  id: string
  label: string
  status: 'done' | 'active' | 'future'
}

export interface RecipeChipState {
  /** Recipe name, e.g. "Double Diamond", "deep_committee" */
  name: string
  /** Optional model/route hint, e.g. "Opus" */
  modelHint?: string
}

export interface SentinelFindingEntry {
  id: string
  category: string
  severity: 'low' | 'medium' | 'high'
  headline: ReactNode
  detail?: ReactNode
  okr?: string
}

export interface SentinelChipState {
  /** Number of unread findings */
  findingCount: number
  /** Number of engines running (for the drawer header) */
  engineCount?: number
  /** When the last sweep completed */
  lastSweep?: string
  /** Highest severity present — drives the dot tone */
  topSeverity: 'low' | 'medium' | 'high' | 'none'
  /** Detailed findings shown in the drawer when the chip is clicked */
  findings?: SentinelFindingEntry[]
}

export interface MemoryChipState {
  /** Captured patterns about how the user thinks */
  patternCount: number
}

export interface RosterMember {
  /** Discipline id matching disciplineIdentity (e.g. 'architecture') */
  lens: string
  /** Optional explicit role label override */
  role?: string
}

export interface TopbarState {
  title: string
  subtitle: string
  /** "Warm" or "Live" — per the partner-never-asks memory, default is "Warm" */
  warmthLabel: string
  cost: CostTickerState
  phases: ProgressPhase[]
  recipe: RecipeChipState
  sentinel: SentinelChipState
  memory: MemoryChipState
  roster: RosterMember[]
}

// -- Vision anchor ---------------------------------------------------------

export interface OKRCommit {
  id: string
  date: string
  /** What landed (short headline) */
  what: ReactNode
}

export interface OKRState {
  id: string
  label: string
  /** 0..1 progress toward target */
  progress?: number
  /** Optional state — 'advancing' | 'stalled' | 'at-risk' */
  status?: 'advancing' | 'stalled' | 'at-risk'
  /** Long-form description shown in the OKR detail popover */
  detail?: ReactNode
  /** Recent commits / progress notes — render as a timeline */
  recentCommits?: OKRCommit[]
}

export interface VisionAnchorState {
  /** The user's north-star statement */
  goal: string
  okrs: OKRState[]
}

// -- Brief-me-back card ----------------------------------------------------

export interface BriefMeBackBullet {
  id: string
  /** A short line — what changed, what landed, what's worth noticing */
  text: ReactNode
  /** Optional accent — pulls discipline color or warning/success */
  toneVar?: string
}

export interface BriefMeBackState {
  /** Lede sentence: "Since you were last here, …" */
  lede: ReactNode
  bullets: BriefMeBackBullet[]
  /** Optional handle for "tell me more" → opens history view */
  onExpand?: () => void
}

// -- Canvas region (deliberation in flight) --------------------------------
//
// A cog-section is a tagged surface: header + body + status + accent.
// The orchestrating state decides what each section IS — phases of one
// flow (Prep / Frame / Diverge / Converge) or lenses running in parallel
// (architecture / security / data / ux). Same primitive, both models.

export type CogSectionStatus = 'done' | 'active' | 'future'

export interface CogSectionState {
  /** Stable id (also drives the dom id so deep-links / animations target it) */
  id: string
  /** Big text in the section head */
  title: string
  /** Italic-serif subtitle next to the title (role line or phase hint) */
  subtitle?: string
  /** Single-glyph identity mark — '◯' frame, '◇' diverge, '◆' converge,
   *  or a discipline glyph for per-lens sections */
  glyph: string
  /** Accent color — typically the discipline accent for per-lens sections,
   *  or a phase-specific tone for phase-driven flows */
  accent?: string
  status: CogSectionStatus
  /** The contents of the section — fully polymorphic. Use whatever pattern
   *  fits the section: matrix card, option tree, contribution rows, etc. */
  body: ReactNode
  /** Optional inline caption shown on the connector arrow leading INTO
   *  the next section. */
  arrowCaption?: string
}

// -- Convergence beat — what lands when the committee converges ----------
//
// After the last lens contributes, the deliberation produces three
// artifacts: a decision (the verdict), a prediction (Foresight's
// falsifiable forecast), and a capture summary (what was written to
// memory). These appear as a horizontal cluster of cards below the
// narrative scroll.

export interface DecisionZoneState {
  /** The verdict text — what the committee decided */
  verdict: string
  /** 0..1 mean confidence across the committee */
  confidence: number
  /** Lenses that contributed — used to render the lineage chip row */
  lineage: string[]
  /** "I'd reverse this if…" — the falsifiability anchor */
  reverseIf?: string
  /** When the synthesis landed (ISO or pretty string) */
  synthesizedAt?: string
}

export interface PredictionTileState {
  /** Days out the prediction reconciles */
  horizonDays: number
  /** The forecast — what the committee expects to happen */
  forecast: string
  /** The falsification condition — what makes this prediction wrong */
  falsifyIf: string
  /** Whether the prediction window has closed (then `outcome` is set) */
  reconciled: boolean
  /** Calibration score 0..1 if reconciled */
  calibrationScore?: number
}

export interface CaptureSummaryState {
  decisions: number
  perspectives: number
  contributions: number
  /** What got cited — lens names that fed into the decision */
  cited: string[]
  /** Optional spec id if the decision compiled to a spec artifact */
  specId?: string
}

export interface ConvergenceBeatState {
  /** Whether the committee has actually converged. When false, the
   *  beat surface renders empty / pending. */
  converged: boolean
  decision: DecisionZoneState
  prediction: PredictionTileState
  capture: CaptureSummaryState
}

// -- Closing ask — partner reflects back ----------------------------------
//
// At the end of a converged turn, the partner names what it's most
// uncertain about and invites the user to engage with that gap.
// Editorial reflection + the persistent ask-input pattern.

export interface ClosingAskState {
  /** Italic-serif reflection in the partner's voice. The full
   *  paragraph — components don't compose it. */
  reflection: ReactNode
  /** Lens whose contribution this uncertainty rides on — used to tint
   *  the accent border on the card. */
  uncertainLens?: string
  /** Submit handler for "tell the partner …" */
  onTell: (text: string) => void
  /** Optional quick-action buttons below the input */
  quickActions?: Array<{ id: string; label: string; onClick: () => void }>
}

// -- Proactive panel — what ACE has been doing in the background ----------
//
// Four cards: sentinel finding (L8), new memory (L7), pattern emergence
// (L7), calibration spark (L9). Surfaced after the deliberation so the
// user sees the partner is still working — the loop hasn't closed.

export interface SentinelFindingState {
  /** Short headline of what was noticed */
  headline: ReactNode
  /** Severity — drives the dot tone */
  severity: 'low' | 'medium' | 'high'
  /** When the sweep noticed this (pretty string like "38s ago") */
  noticedAt: string
}

export interface NewMemoryState {
  /** Pattern title — what ACE captured */
  pattern: ReactNode
  /** Provenance line — confirmations, dates, etc. */
  provenance: string
}

export interface PatternEmergeState {
  /** What ACE noticed across prior decisions */
  observation: ReactNode
  /** Provenance + footnote */
  provenance: string
}

export interface CalibrationSparkState {
  /** Recent prediction-accuracy points (0..1) */
  values: number[]
  /** Mean across the window */
  average: number
  /** Optional footnote */
  note?: string
}

export interface ProactivePanelState {
  sentinel?: SentinelFindingState
  newMemory?: NewMemoryState
  patternEmerge?: PatternEmergeState
  calibration?: CalibrationSparkState
}

// -- Reconciliation banner -------------------------------------------------
//
// Appears above the canvas when a prediction window is closing. Names
// which decision is being reconciled and how. Demo-driver for the +30d
// mode in multiplayer.html.

export interface ReconciliationBannerState {
  active: boolean
  /** Pretty horizon string, e.g. "+30d", "+7d" */
  horizonLabel: string
  /** Which decision is being reconciled */
  decisionTitle: ReactNode
  /** Optional preview of the calibration outcome */
  outcomeHint?: ReactNode
}

// -- Contribution (one voice in the workshop) ------------------------------
//
// A lens's contribution to the deliberation, structured for flowing-prose
// rendering. The team's read renders these as a running narrative — not
// as a stack of uniform cards.

export interface ContributionState {
  /** Stable id (drives deep-link + animation targets) */
  id: string
  /** Discipline id matching disciplineIdentity (e.g. 'architecture') */
  lens: string
  /** How the voice is named in the byline ("Architecture", "Security") */
  speaker: string
  /** Accent color for the byline + edge mark — pulls from disciplineIdentity */
  accent: string
  /** The voice's framing of the problem — plain text, no quotes (TeamReadout
   *  wraps in serif paragraph styling). When inFlight=true, this may be
   *  partial (the text being formed so far). */
  framing: string
  /** 0..1 confidence. Stored for use by the synthesizer; NOT displayed as a
   *  numeric badge on the surface. Uncertainty surfaces through word
   *  choice in the contribution itself, or in the closing-ask reflection. */
  confidence?: number
  /** Whether this contribution is still forming (vs. landed). When true,
   *  TeamReadout renders a blinking caret at the end of the partial text. */
  inFlight?: boolean
  /** Editorial time-since-this-landed phrase: "3 min ago", "just now",
   *  "still thinking…". Surfaces partnership-as-recent-collaboration. */
  landedAt?: string
  /** One-line "thinking about…" note — shown beneath the caret when
   *  inFlight, in the voice's accent. Makes reasoning visible without
   *  waiting for the full contribution to land. */
  thinkingAbout?: string
}

// -- Attention request (the team needs you) --------------------------------
//
// When a voice or the partner needs the user's call on something, it surfaces
// as a callout INSIDE the canvas — not a notification, not a modal. The
// team is addressing him directly. Carries the speaker, the question,
// and an inline ask-back input so the response stays in flow.

export interface AttentionRequestState {
  /** Stable id (drives keying + dismiss tracking) */
  id: string
  /** Who's asking — could be a lens, the partner, or "the team". */
  speaker: string
  /** Accent color for the avatar + edge mark. */
  accent: string
  /** Single-letter or glyph for the avatar. */
  initial: string
  /** The question, in the speaker's voice. Serif body. */
  question: ReactNode
  /** Optional context line — what triggered the ask. Smaller, muted. */
  triggeredBy?: ReactNode
  /** Editorial timestamp ("just now", "1 min ago") */
  askedAt?: string
  /** Quick-action buttons — typically "push back", "proceed", "tell me more". */
  quickActions?: Array<{ id: string; label: string; onClick: () => void }>
  /** Submit handler for the free-form ask-back input. */
  onReply: (text: string) => void
}

// -- Presence (who's in the room) ------------------------------------------
//
// Multiplayer affordance: the canvas always shows the participants — the
// five lens voices, the partner (ACE), and the user. Each has an avatar
// + accent + status. The interface NEVER reads as "empty / waiting" per
// the partner-never-asks thesis.

export type PresenceStatus =
  /** Currently producing — caret blink, active dot fill */
  | 'active'
  /** Just finished — trailing color halo, fades to idle */
  | 'just-spoke'
  /** Warm but not speaking */
  | 'idle'
  /** Reading along (user only, mostly) */
  | 'listening'

export interface PresenceParticipant {
  /** Stable id for keying + tooltip */
  id: string
  /** What to label this participant. For lenses: discipline name.
   *  For the partner: "Partner" or "ACE". For the user: "You". */
  name: string
  /** Single-letter or glyph initial. Avatar shows this on top of the
   *  accent ring. */
  initial: string
  /** Accent color — lens accent for voices, --ace-accent for partner,
   *  --ace-ink for the user. */
  accent: string
  /** Current activity status. Drives visual treatment. */
  status: PresenceStatus
  /** What they're doing right now (only set when status === 'active').
   *  Surfaces on hover. */
  activity?: string
  /** Editorial last-spoken time, e.g. "3 min ago". */
  lastAt?: string
  /** Marks the partner (ACE) — gets the partner-status pill treatment. */
  isPartner?: boolean
  /** Marks the user — gets the "You" label and ink accent. */
  isUser?: boolean
}

export interface PresenceState {
  /** Ordered participants — usually [user, partner, ...lenses]. */
  participants: PresenceParticipant[]
  /** What the partner is doing globally — drives the partner-status pill.
   *  "warm" is the default at rest; never undefined per partner-never-asks. */
  partnerStatus: 'warm' | 'listening' | 'thinking' | 'synthesizing'
  /** Optional editorial phrase for the partner-status pill, e.g.
   *  "Synthesizing the cache-layer call" — appears next to the status. */
  partnerActivity?: string
}

export interface CanvasState {
  /** Whether a deliberation is currently in motion */
  inFlight: boolean
  /** Optional banner above the canvas (reconciliation mode, etc.) */
  banner?: ReconciliationBannerState
  /** Multiplayer presence — always set, even at idle. Drives the
   *  PresenceRibbon + partner-status pill. */
  presence?: PresenceState
  /** Ordered sections — render top to bottom as a narrative scroll.
   *  Legacy / phase-driven mode (Frame → Diverge → Converge). */
  sections: CogSectionState[]
  /** Multi-voice contributions — render as a flowing brief, not a card
   *  stack. Used by the team-deliberation mode. When set, TeamReadout
   *  renders these and `sections` is ignored. */
  contributions?: ContributionState[]
  /** Editorial intro for the team's read — one sentence before the
   *  contributions, naming what the team converged on at a glance. */
  readoutHeader?: ReactNode
  /** Active attention requests from the team — surfaces inside the
   *  canvas as callouts. The partnership-as-conversation channel. */
  attention?: AttentionRequestState[]
  /** What lands after the sections converge. */
  convergence?: ConvergenceBeatState
  /** Partner-reflects-back surface; renders after convergence. */
  closingAsk?: ClosingAskState
  /** Background activity — sentinel/memory/pattern/calibration. */
  proactive?: ProactivePanelState
  /** Optional fallback when the deliberation isn't in flight yet. */
  placeholder?: ReactNode
}

// -- Working panel (right rail) --------------------------------------------

export interface WorkingPanelState {
  /** Agents currently working in the background, oldest first */
  agentsInFlight: Array<{ lens: string; activity: string }>
  /** "Captured this turn" surface — what's been written to memory */
  capturedThisTurn?: {
    decisions: number
    perspectives: number
    contributions: number
  }
}

// -- Footer (persistent "ask the team") ------------------------------------

export interface FooterState {
  placeholder: string
  onAsk: (text: string) => void
}

// -- Full state object -----------------------------------------------------

export interface AceCoreState {
  topbar: TopbarState
  vision: VisionAnchorState
  briefMeBack: BriefMeBackState
  canvas: CanvasState
  workingPanel: WorkingPanelState
  footer: FooterState
  /** L3 composition snapshot — the orchestra of meta-intelligences self-nominating
   *  for the current task. Populated by the canvas.composition.selected event
   *  via useLiveComposition(); null when no composition is in flight.
   *  Consumed by <CompositionLens payload={state.composition} />. */
  composition?: CompositionSelectedPayload | null
  /** The Deliberation Journey — the canvas's primary surface. Renders the
   *  substrate's full L1→L9 stack visibly: topic, classification, parallel
   *  meta-intelligence tracks per stage, L6 synthesis, L7 decisions, L8
   *  sentinel marks, L9 predictions. When set, the App renders this in
   *  place of the legacy multi-panel layout. */
  journey?: DeliberationJourneyState
  /** Active canvas session id (e.g. "canvas_session:abc"). When set, Main
   *  subscribes to the session's WebSocket for the L9 prediction lifecycle
   *  via usePredictionOutcomes() — the reconciliation banner follows the
   *  latest prediction.outcome.closed instead of fixture state. */
  sessionId?: string | null
}
