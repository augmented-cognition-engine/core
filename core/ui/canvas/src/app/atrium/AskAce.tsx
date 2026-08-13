import { useMemo, useState } from 'react'
import { ArrowRight, Search, ShieldCheck } from 'lucide-react'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import { Input } from '@/design/shadcn/ui/input'

import { kindLabel, rankResourcesForQuestion } from './intelligenceModel'

const SUGGESTIONS = [
  'What changed most recently?',
  'Which opportunities need attention?',
  'What evidence supports the latest brief?',
]

export function AskAce({ items }: { readonly items: readonly IntelligenceResourceRecord[] }) {
  const [draft, setDraft] = useState('')
  const [question, setQuestion] = useState('')
  const matches = useMemo(
    () => rankResourcesForQuestion(question, items),
    [items, question],
  )

  function ask(nextQuestion = draft) {
    const normalized = nextQuestion.trim()
    if (normalized.length === 0) return
    setDraft(normalized)
    setQuestion(normalized)
  }

  return (
    <Card className="overflow-hidden border-foreground/10 bg-anchor text-anchor-foreground shadow-sm">
      <CardContent className="p-5 md:p-6">
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-lg bg-brand text-brand-foreground">
            <Search className="size-4" />
          </div>
          <div>
            <div className="text-sm font-semibold">Ask ACE</div>
            <div className="text-[11px] opacity-65">Answers from your governed intelligence</div>
          </div>
          <Badge variant="outline" className="ml-auto border-current/15 bg-background/50 text-foreground">
            <ShieldCheck className="mr-1 size-3" />
            cited
          </Badge>
        </div>

        <div className="mt-4 flex gap-2">
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') ask()
            }}
            placeholder="Ask about competitors, shifts, evidence, or decisions"
            aria-label="Ask ACE about current intelligence"
            className="h-11 border-foreground/15 bg-background text-foreground placeholder:text-muted-foreground"
          />
          <Button
            type="button"
            size="icon"
            className="size-11 shrink-0"
            onClick={() => ask()}
            disabled={draft.trim().length === 0}
            aria-label="Ask ACE"
          >
            <ArrowRight className="size-4" />
          </Button>
        </div>

        {question.length === 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <Button
                key={suggestion}
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 bg-background/45 px-2.5 text-[11px] text-foreground hover:bg-background"
                onClick={() => ask(suggestion)}
              >
                {suggestion}
              </Button>
            ))}
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-foreground/10 bg-background/70 p-4 text-foreground">
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Intelligence answer · {matches.length} cited record{matches.length === 1 ? '' : 's'}
            </div>
            {matches.length === 0 ? (
              <p className="mt-2 text-sm leading-relaxed">
                I do not have enough governed evidence to answer that yet. Add a source or broaden a monitor; ACE will not fill the gap with an unsupported claim.
              </p>
            ) : (
              <div className="mt-3 space-y-3">
                {matches.slice(0, 3).map((match, index) => (
                  <div key={`${match.reference.resource_id}:${match.reference.revision}`} className="flex gap-3">
                    <span className="font-mono text-[10px] text-muted-foreground">0{index + 1}</span>
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
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
