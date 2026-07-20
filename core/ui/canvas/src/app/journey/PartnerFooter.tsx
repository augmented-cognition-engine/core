// app/journey/PartnerFooter.tsx
//
// Sticky "write next" affordance at the bottom of the canvas. Always
// present — communicates that the partnership is the surface, not a
// session/page. The partner is always ready; you can always speak.
//
// The ACE mark to the left of the input represents the partner as an
// orchestra of intelligences continuously composing — not a static
// branded avatar. See ACEMark.tsx.
import { PaperPlaneTilt } from '@phosphor-icons/react'
import { useState } from 'react'

import { Button } from '@/design/shadcn/ui/button'
import { Textarea } from '@/design/shadcn/ui/textarea'

import { ACEMark } from './ACEMark'

interface PartnerFooterProps {
  hint?: string
  placeholder?: string
  onAsk?: (text: string) => void
}

export function PartnerFooter({
  hint,
  placeholder = 'write next — or say "continue" to wave the partner through',
  onAsk,
}: PartnerFooterProps) {
  const [text, setText] = useState('')

  const submit = () => {
    if (text.trim().length === 0) return
    onAsk?.(text.trim())
    setText('')
  }

  return (
    <footer className="flex flex-col gap-2 px-8 py-3 bg-background border-t border-border">
      {hint !== undefined && (
        <span className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
          {hint}
        </span>
      )}
      <div className="flex items-end gap-3 max-w-[760px] mx-auto w-full">
        {/* Partner presence — animated ACEMark. The mark's own motion
            carries the "partner is alive" signal; no separate status dot.
            Bottom-aligned with the input (no upward nudge) so it sits
            level with the field, not floating above it. */}
        <div className="shrink-0">
          <ACEMark size={36} variant="iris" />
        </div>

        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
          rows={1}
          className="resize-none min-h-10 max-h-32"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              submit()
            }
          }}
        />
        <Button
          variant="default"
          size="sm"
          className="cursor-pointer shrink-0"
          aria-label="Send to partner"
          onClick={submit}
        >
          <PaperPlaneTilt size={14} weight="fill" />
          send
        </Button>
      </div>
    </footer>
  )
}
