import { useMemo, useState } from 'react'
import { ArrowRight, CircleAlert, Clock3, Search } from 'lucide-react'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Input } from '@/design/shadcn/ui/input'

import { answerQuestionFromResources } from './askAceModel'
import { ATRIUM_ACTION_ICONS } from './atriumIcons'
import { kindLabel } from './intelligenceModel'

const AskIcon = ATRIUM_ACTION_ICONS.ask
const GovernedEvidenceIcon = ATRIUM_ACTION_ICONS.governedEvidence
const EvidenceLineageIcon = ATRIUM_ACTION_ICONS.evidenceLineage

const SUGGESTIONS = [
  'What changed most recently?',
  'Which opportunities need attention?',
  'What evidence supports the latest brief?',
]

export function AskAce({ items }: { readonly items: readonly IntelligenceResourceRecord[] }) {
  const [draft, setDraft] = useState('')
  const [question, setQuestion] = useState('')
  const answer = useMemo(
    () => answerQuestionFromResources(question, items),
    [items, question],
  )

  function ask(nextQuestion = draft) {
    const normalized = nextQuestion.trim()
    if (normalized.length === 0) return
    setDraft(normalized)
    setQuestion(normalized)
  }

  return (
    <section className="border-y border-border bg-anchor text-anchor-foreground">
      <div className="p-4 md:p-5">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-md border border-brand/30 bg-brand/10 text-brand">
            <AskIcon className="size-3.5" aria-hidden="true" />
          </div>
          <div>
            <div className="text-sm font-semibold">Ask ACE</div>
            <div className="text-[11px] text-muted-foreground">A sourced answer from the intelligence currently in view</div>
          </div>
          <Badge variant="outline" className="ml-auto hidden border-border bg-background/35 text-muted-foreground sm:inline-flex">
            <GovernedEvidenceIcon className="mr-1 size-3" aria-hidden="true" />
            governed sources
          </Badge>
        </div>

        <div className="mt-3 flex gap-2">
          <div className="relative min-w-0 flex-1">
            <Search aria-hidden="true" className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') ask()
              }}
              placeholder="Ask about competitors, shifts, evidence, or decisions"
              aria-label="Ask ACE about current intelligence"
              className="h-11 border-border bg-background pl-10 text-foreground placeholder:text-muted-foreground focus-visible:border-brand/50"
            />
          </div>
          <Button
            type="button"
            size="icon"
            className="size-11 shrink-0 rounded-md"
            onClick={() => ask()}
            disabled={draft.trim().length === 0}
            aria-label="Ask ACE"
          >
            <ArrowRight className="size-4" aria-hidden="true" />
          </Button>
        </div>

        {question.length === 0 ? (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((suggestion) => (
              <Button
                key={suggestion}
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 rounded-md border border-border/70 bg-background/35 px-2.5 text-[10px] text-muted-foreground hover:bg-background hover:text-foreground"
                onClick={() => ask(suggestion)}
              >
                {suggestion}
              </Button>
            ))}
          </div>
        ) : (
          <div
            role="region"
            aria-label="Ask ACE answer"
            className="mt-4 border-t border-border bg-background/50 pt-4 text-foreground"
          >
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Intelligence answer · {answer?.evidence.length ?? 0} cited record{answer?.evidence.length === 1 ? '' : 's'}
            </div>
            {answer === null ? (
              <p className="mt-2 text-sm leading-relaxed">
                I do not have enough governed evidence to answer that yet. Add a source or broaden a monitor; ACE will not fill the gap with an unsupported claim.
              </p>
            ) : (
              <div className="mt-3 grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)]">
                <div className="space-y-4">
                  <div>
                    <div className="font-mono text-[8px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">Answer</div>
                    <p className="mt-2 border-l-2 border-foreground/35 pl-3 text-[15px] font-medium leading-6 text-foreground">
                      {answer.conclusion}
                    </p>
                  </div>

                  {(answer.whyItMatters !== null || answer.whenItChanged !== null) && (
                    <div className="space-y-3 border-t border-border pt-3">
                      {answer.whyItMatters !== null && (
                        <div>
                          <div className="font-mono text-[8px] font-semibold uppercase tracking-[0.15em] text-foreground/70">Why it matters</div>
                          <p className="mt-1.5 text-xs leading-5 text-foreground/85">{answer.whyItMatters}</p>
                        </div>
                      )}
                      {answer.whenItChanged !== null && (
                        <div className="flex items-start gap-2 border-t border-border/70 pt-3">
                          <div className="flex shrink-0 items-center gap-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
                            <Clock3 className="size-3" aria-hidden="true" /> When
                          </div>
                          <p className="text-[10px] leading-4 text-foreground/75">{answer.whenItChanged}</p>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex items-start gap-2 border-t border-border/70 pt-3 text-[11px] leading-5 text-muted-foreground">
                    <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                    <span>{answer.limitation}</span>
                  </div>
                </div>

                <aside className="border-t border-border pt-4 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0" aria-label="Evidence used for this answer">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-1.5 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
                      <EvidenceLineageIcon className="size-3" aria-hidden="true" /> Evidence used
                    </div>
                    <Badge variant="outline" className="rounded-sm font-mono text-[8px]">{answer.evidence.length} records</Badge>
                  </div>
                  <div className="divide-y divide-border/70">
                    {answer.evidence.slice(0, 4).map((match, index) => (
                      <div key={`${match.reference.resource_id}:${match.reference.revision}`} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                        <span className="font-mono text-[10px] text-foreground/65">[{index + 1}]</span>
                        <div className="min-w-0">
                          <div className="text-xs font-medium leading-snug">{match.title}</div>
                          <div className="mt-1.5 font-mono text-[9px] text-muted-foreground">
                            {kindLabel(match.reference.resource_kind)} · r{match.reference.revision} · {match.provenance.length} links
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </aside>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
