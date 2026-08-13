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
    <Card className="overflow-hidden border-brand/20 bg-anchor text-anchor-foreground">
      <CardContent className="p-4 md:p-5">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-md border border-brand/30 bg-brand/10 text-brand">
            <Sparkles className="size-3.5" />
          </div>
          <div>
            <div className="text-sm font-semibold">Ask ACE</div>
            <div className="text-[11px] text-muted-foreground">A sourced answer from the intelligence currently in view</div>
          </div>
          <Badge variant="outline" className="ml-auto hidden border-brand/25 bg-brand/5 text-brand sm:inline-flex">
            <ShieldCheck className="mr-1 size-3" />
            governed sources
          </Badge>
        </div>

        <div className="mt-3 flex gap-2">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
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
            <ArrowRight className="size-4" />
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
          <div className="mt-4 rounded-lg border border-brand/20 bg-background/75 p-4 text-foreground">
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Intelligence answer · {answer?.evidence.length ?? 0} cited record{answer?.evidence.length === 1 ? '' : 's'}
            </div>
            {answer === null ? (
              <p className="mt-2 text-sm leading-relaxed">
                I do not have enough governed evidence to answer that yet. Add a source or broaden a monitor; ACE will not fill the gap with an unsupported claim.
              </p>
            ) : (
              <div className="mt-3 space-y-4">
                <p className="border-l-2 border-brand pl-3 text-[15px] font-medium leading-6 text-foreground">
                  {answer.conclusion}
                </p>

                {(answer.whyItMatters !== null || answer.whenItChanged !== null) && (
                  <div className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2">
                    {answer.whyItMatters !== null && (
                      <div className="bg-card p-3">
                        <div className="font-mono text-[8px] font-semibold uppercase tracking-[0.15em] text-brand">Why it matters</div>
                        <p className="mt-1.5 text-xs leading-5 text-foreground/85">{answer.whyItMatters}</p>
                      </div>
                    )}
                    {answer.whenItChanged !== null && (
                      <div className="bg-card p-3">
                        <div className="flex items-center gap-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.15em] text-brand">
                          <Clock3 className="size-3" /> When
                        </div>
                        <p className="mt-1.5 text-xs leading-5 text-foreground/85">{answer.whenItChanged}</p>
                      </div>
                    )}
                  </div>
                )}

                <div>
                  <div className="mb-2 flex items-center gap-1.5 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
                    <GitBranch className="size-3" /> Evidence trail
                  </div>
                  <div className="space-y-2">
                  {answer.evidence.slice(0, 3).map((match, index) => (
                  <div key={`${match.reference.resource_id}:${match.reference.revision}`} className="flex gap-3">
                    <span className="font-mono text-[10px] text-brand">[{index + 1}]</span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium leading-snug">{match.title}</div>
                      {match.summary !== null && (
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                          {match.summary}
                        </p>
                      )}
                      <div className="mt-1.5 font-mono text-[10px] text-muted-foreground">
                        {kindLabel(match.reference.resource_kind)} · revision {match.reference.revision} · {match.provenance.length} evidence links
                      </div>
                    </div>
                  </div>
                ))}
                  </div>
                </div>

                <div className="flex items-start gap-2 border-t border-border/70 pt-3 text-[11px] leading-5 text-muted-foreground">
                  <CircleAlert className="mt-0.5 size-3.5 shrink-0" />
                  <span>{answer.limitation}</span>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
