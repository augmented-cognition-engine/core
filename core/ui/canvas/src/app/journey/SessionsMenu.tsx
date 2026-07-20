// app/journey/SessionsMenu.tsx
//
// Previous-sessions switcher. Lives in the pipeline/step strip rather than
// the page header — re-entering a past deliberation is a move *through the
// work*, so it sits with the stage track, not the surface chrome.
//
// Demo fixture for now — the same shape the live session index will return
// (topic + when + how it ended). The current session is marked so the list
// reads as "where you are + where you've been". `topic` is the question;
// re-opening seeds the room with it (same path the ACE flyout uses).

import { CaretDown, ClockCounterClockwise } from '@phosphor-icons/react'
import { useLocation, useNavigate } from 'react-router-dom'

import { cn } from '@/lib/utils'
import { Button } from '@/design/shadcn/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/design/shadcn/ui/popover'

type SessionOutcome = 'in motion' | 'decided' | 'shelved' | 'archived'

interface RecentSession {
  readonly id: string
  readonly topic: string
  readonly when: string
  readonly outcome: SessionOutcome
  readonly current?: boolean
}

const RECENT_SESSIONS: readonly RecentSession[] = [
  {
    id: 'homepage_hero_pivot',
    topic: 'Should we pivot the homepage hero from price-first to outcomes-first for the Q3 launch?',
    when: 'now',
    outcome: 'in motion',
    current: true,
  },
  {
    id: 'edge_sovereignty',
    topic: 'Does the "sovereign edge" claim survive the hyperscalers\' sovereignty positioning?',
    when: '2 days ago',
    outcome: 'decided',
  },
  {
    id: 'private_cloud_proof',
    topic: 'What proof points does the private-cloud page need to convince a skeptical CISO?',
    when: '4 days ago',
    outcome: 'decided',
  },
  {
    id: 'cfo_usage_pricing',
    topic: 'Can we defend usage-based pricing language to a risk-averse CFO?',
    when: '5 days ago',
    outcome: 'shelved',
  },
  {
    id: 'storage_vs_incumbent',
    topic: 'How should the storage page answer the incumbent on guaranteed efficiency?',
    when: '1 week ago',
    outcome: 'decided',
  },
  {
    id: 'sustainability_claim_audit',
    topic: 'Do our sustainability claims hold up to a procurement-led ESG review?',
    when: '10 days ago',
    outcome: 'archived',
  },
  {
    id: 'ai_factory_pillar',
    topic: 'Is "AI factory" the right canonical pillar, or does it drift from the buyer\'s job?',
    when: '2 weeks ago',
    outcome: 'archived',
  },
]

// Outcome -> dot color. State semantics: in motion = live (brand green),
// decided = success, shelved/archived = neutral (a category, not an alarm).
const OUTCOME_DOT: Record<SessionOutcome, string> = {
  'in motion': 'bg-live animate-pulse',
  decided: 'bg-[var(--success)]',
  shelved: 'bg-muted-foreground/50',
  archived: 'bg-muted-foreground/30',
}

export function SessionsMenu() {
  const navigate = useNavigate()
  const location = useLocation()

  function openSession(session: RecentSession) {
    if (session.current === true) return
    // Re-enter the room seeded with the session's question — same path the
    // ACE flyout uses for a fresh kick-off, so the room reflects the topic.
    navigate('/atrium', {
      state: { from: location.pathname, label: 'Sessions', topic: session.topic },
    })
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          aria-label="Previous sessions"
          className="cursor-pointer gap-1.5 h-7 font-normal text-muted-foreground hover:text-foreground"
        >
          <ClockCounterClockwise className="size-4" />
          Sessions
          <CaretDown className="size-3 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="w-[24rem] p-0 overflow-hidden">
        <div className="px-4 pt-4 pb-2 border-b border-border">
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Sessions
          </span>
        </div>
        <ul className="py-1 max-h-[60vh] overflow-y-auto">
          {RECENT_SESSIONS.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => openSession(s)}
                disabled={s.current === true}
                className={cn(
                  'group flex w-full items-start gap-2.5 px-4 py-2.5 text-left transition-colors duration-200',
                  s.current === true
                    ? 'cursor-default bg-muted/40'
                    : 'cursor-pointer hover:bg-muted/60 focus-visible:outline-none focus-visible:bg-muted/60',
                )}
              >
                <span
                  aria-hidden
                  className={cn('mt-1.5 size-1.5 shrink-0 rounded-full', OUTCOME_DOT[s.outcome])}
                />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-sm leading-snug text-foreground/90 line-clamp-2 group-hover:text-foreground">
                    {s.topic}
                  </span>
                  <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                    <span>{s.outcome}</span>
                    <span aria-hidden className="text-muted-foreground/40">·</span>
                    <span>{s.when}</span>
                    {s.current === true && (
                      <span className="ml-auto text-live normal-case tracking-normal">
                        you are here
                      </span>
                    )}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  )
}
