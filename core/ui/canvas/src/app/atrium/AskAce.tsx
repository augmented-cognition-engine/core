import { useMemo, useState } from 'react'
import { ArrowRight, CircleAlert, Clock3, GitBranch, Search, ShieldCheck, Sparkles } from 'lucide-react'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import { Input } from '@/design/shadcn/ui/input'

import { answerQuestionFromResources } from './askAceModel'
import { kindLabel } from './intelligenceModel'

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
    <Card className="overflow-hidden border-white/[0.1] bg-anchor text-anchor-foreground shadow-2xl">
      <CardContent className="p-3 md:p-3.5">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-md border border-brand/25 bg-brand/[0.08] text-brand">
            <Sparkles className="size-3.5" />
          </div>
          <div className="hidden shrink-0 md:block">
            <div className="text-xs font-semibold">Ask ACE</div>
            <div className="text-[10px] text-muted-foreground">Grounded in this picture</div>
          </div>
          <div className="relative min-w-0 flex-1 md:ml-2">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') ask()
              }}
              placeholder="Ask about competitors, shifts, evidence, or decisions"
              aria-label="Ask ACE about current intelligence"
              className="h-11 border-white/[0.09] bg-white/[0.035] pl-10 text-foreground placeholder:text-muted-foreground focus-visible:border-brand/50"
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
            <ArrowRight className="size-4" />
          </Button>
          <Badge variant="outline" className="ml-1 hidden border-live/15 bg-live/[0.04] text-live xl:inline-flex">
            <ShieldCheck className="mr-1 size-3" />
            cited picture
          </Badge>
        </div>

        {question.length === 0 ? (
          <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-white/[0.06] pt-2.5">
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
            className="mt-4 rounded-lg border border-brand/20 bg-background/75 p-4 text-foreground"
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
                    <div className="font-mono text-[8px] font-semibold uppercase tracking-[0.15em] text-brand">Answer</div>
                    <p className="mt-2 border-l-2 border-brand pl-3 text-[15px] font-medium leading-6 text-foreground">
                      {answer.conclusion}
                    </p>
                  </div>

                  {answer.whyItMatters !== null && (
                    <div className="border-l-2 border-brand/55 pl-3">
                      <div className="font-mono text-[8px] font-semibold uppercase tracking-[0.15em] text-brand">Why it matters</div>
                      <p className="mt-1.5 text-xs leading-5 text-foreground/80 text-pretty">{answer.whyItMatters}</p>
                    </div>
                  )}

                  <div className="flex items-start gap-2 border-t border-border/70 pt-3 text-[11px] leading-5 text-muted-foreground">
                    <CircleAlert className="mt-0.5 size-3.5 shrink-0" />
                    <span>{answer.limitation}</span>
                  </div>
                </div>

                <aside className="rounded-lg border bg-card/70 p-3.5" aria-label="Evidence trail for this answer">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-1.5 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
                      <GitBranch className="size-3" /> Evidence trail
                    </div>
                    <Badge variant="outline" className="rounded-sm font-mono text-[8px]">{answer.evidence.length} records</Badge>
                  </div>
                  <div className="divide-y divide-border/70">
                    {answer.evidence.slice(0, 4).map((match, index) => (
                      <div key={`${match.reference.resource_id}:${match.reference.revision}`} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                        <span className="font-mono text-[10px] text-brand">[{index + 1}]</span>
                        <div className="min-w-0">
                          <div className="text-xs font-medium leading-snug">{match.title}</div>
                          <div className="mt-1.5 font-mono text-[9px] text-muted-foreground">
                            {kindLabel(match.reference.resource_kind)} · r{match.reference.revision} · {match.provenance.length} links
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  {answer.whenItChanged !== null && (
                    <div className="mt-3 flex items-start gap-2 border-t border-border/70 pt-3 text-[10px] leading-4 text-muted-foreground">
                      <Clock3 className="mt-0.5 size-3 shrink-0" />
                      <span>{answer.whenItChanged}</span>
                    </div>
                  )}
                </aside>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
